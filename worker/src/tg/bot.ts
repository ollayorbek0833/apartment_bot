import { Bot, Context, type Api } from 'grammy';

import { DutyService } from '../core/service';
import { Repo } from '../db/repo';
import { ownerId, type Env } from '../env';
import {
  RESERVED_NAMES,
  TASK_NAME_RE,
  buildCsv,
  buildDigest,
  closestTask,
} from './format';
import { NameResolver, formatUser } from './names';
import { daysAgoIso, localDate } from './time';

export interface Deps {
  repo: Repo;
  duty: DutyService;
  env: Env;
}

type Ctx = Context & { deps: Deps; names: NameResolver };

const USER_HELP = `🤖 ApartmentMate

👤 USER COMMANDS

/now — who is responsible right now (read-only)

/task_name — e.g. /oshxona
• Only works if you are in that rotation
• Your turn → the duty is completed
• Not your turn → you cover it for whoever was up: the duty is
  done, the rotation moves on, and you get +1 skip credit to sit
  out a future turn
• The same command is ignored for 2 hours

/show task_name — the next 5 turns (read-only)
/history — your last 10 duties
/history task_name — the last 3 for that duty
/credits — who is holding unused skip credits
/my_tasks — the duties you are in
/tasks — every duty

📌 NOTES
• No daily reset. Rotation is automatic and fair.
• A skip credit always costs somebody a real turn, so it cannot be farmed.`;

const ADMIN_HELP = `🛠 ADMIN COMMANDS

/add_task task_name — create a duty (a-z, 0-9, _ )
/add_user task_name — reply to a user, adds them to the rotation
/remove_user task_name — reply to a user, takes them out
/show task_name — the next 5 turns
/data — the last 30 days as a CSV
/cancel — reply to a bot confirmation to undo it, restoring the
  rotation, the skip credits it spent, and the cooldown
/claim — make THIS group the apartment the bot serves

🧠 RULES
• Each duty has a fixed order that removals never disturb
• Covering somebody's turn completes it and earns a credit
• Credits skip future turns, and are spent automatically`;

/**
 * The bot serves exactly one group.
 *
 * No table carries a chat id, so a second group would share this flat's
 * rotation, credits, history and CSV export, and would receive its morning
 * announcement. The first group the OWNER uses claims the bot; everything else
 * is refused.
 */
async function inApartment(ctx: Ctx, quiet = false): Promise<boolean> {
  const chat = ctx.chat;
  const from = ctx.from;
  if (!chat || !from) return false;

  if (chat.type !== 'group' && chat.type !== 'supergroup') {
    if (!quiet) await ctx.reply('❌ This bot works only in groups.');
    return false;
  }

  const apartment = await ctx.deps.repo.getApartmentChatId();

  if (apartment === null) {
    // Never let a stranger's group claim the bot.
    if (from.id !== ownerId(ctx.deps.env)) return false;
    await ctx.deps.repo.setApartmentChatId(chat.id);
    return true;
  }

  if (chat.id !== apartment) {
    if (!quiet) {
      await ctx.reply('❌ This bot belongs to another apartment. Run your own copy.');
    }
    return false;
  }

  return true;
}

/** Owner-only, and only in the apartment. Replies with the reason itself. */
async function ownerOnly(ctx: Ctx): Promise<boolean> {
  if (!(await inApartment(ctx))) return false;
  if (ctx.from?.id !== ownerId(ctx.deps.env)) {
    await ctx.reply('❌ Bot owner authorization required.');
    return false;
  }
  return true;
}

function replyToUser(ctx: Ctx) {
  return ctx.message?.reply_to_message?.from ?? null;
}

export function createBot(env: Env, db: D1Database): Bot<Ctx> {
  const repo = new Repo(db);
  const duty = new DutyService(repo);
  const bot = new Bot<Ctx>(env.BOT_TOKEN);

  bot.use(async (ctx, next) => {
    ctx.deps = { repo, duty, env };
    ctx.names = new NameResolver(bot.api as Pick<Api, 'getChatMember'>, repo, ctx.chat?.id ?? 0);
    if (ctx.from && !ctx.from.is_bot) await ctx.names.remember(ctx.from);
    await next();
  });

  // ---------- help ----------

  bot.command(['help', 'start'], async (ctx) => {
    if (!(await inApartment(ctx, true))) return;
    await ctx.reply(USER_HELP);
  });

  bot.command('help_admin', async (ctx) => {
    if (!(await ownerOnly(ctx))) return;
    await ctx.reply(ADMIN_HELP);
  });

  // ---------- apartment ----------

  bot.command('claim', async (ctx) => {
    const chat = ctx.chat;
    if (!chat || ctx.from?.id !== ownerId(env)) {
      if (ctx.from?.id !== ownerId(env)) await ctx.reply('❌ Bot owner authorization required.');
      return;
    }
    if (chat.type !== 'group' && chat.type !== 'supergroup') {
      await ctx.reply('❌ Run this in the apartment group.');
      return;
    }
    const previous = await repo.getApartmentChatId();
    await repo.setApartmentChatId(chat.id);
    if (previous === null) {
      await ctx.reply('✅ This group is now the apartment. Other chats are ignored.');
    } else if (previous === chat.id) {
      await ctx.reply('ℹ️ This group already is the apartment.');
    } else {
      await ctx.reply(
        `✅ Moved. The apartment is now this group; ${previous} no longer gets the daily ` +
          'announcement. The rotation and history came along unchanged.',
      );
    }
  });

  // ---------- admin ----------

  bot.command('add_task', async (ctx) => {
    if (!(await ownerOnly(ctx))) return;
    const name = (ctx.match ?? '').trim().split(/\s+/)[0]?.toLowerCase();
    if (!name) {
      await ctx.reply('Usage: /add_task task_name');
      return;
    }
    if (!TASK_NAME_RE.test(name)) {
      await ctx.reply(
        '❌ A task name must be 1-32 characters of a-z, 0-9 or _ , because it becomes a ' +
          'command you type. Example: /add_task oshxona',
      );
      return;
    }
    if (RESERVED_NAMES.has(name)) {
      await ctx.reply(
        `❌ '${name}' is one of the bot's own commands. Pick another name, otherwise ` +
          `/${name} would never reach the task.`,
      );
      return;
    }
    if (await repo.taskExists(name)) {
      await ctx.reply('⚠️ Task already exists.');
      return;
    }
    await repo.createTask(name);
    await ctx.reply(`✅ Task '${name}' created. Run it with /${name}`);
  });

  bot.command('add_user', async (ctx) => {
    if (!(await ownerOnly(ctx))) return;
    const task = (ctx.match ?? '').trim().split(/\s+/)[0]?.toLowerCase();
    if (!task) {
      await ctx.reply('Usage: /add_user task_name (reply to a user)');
      return;
    }
    const target = replyToUser(ctx);
    if (!target || target.is_bot) {
      await ctx.reply("❌ Reply to a real user's message, not a bot.");
      return;
    }
    if (!(await repo.taskExists(task))) {
      await ctx.reply('❌ Task does not exist.');
      return;
    }
    const name = await ctx.names.remember(target);
    const result = await repo.addUser(task, target.id);
    const line = {
      added: `✅ ${name} added to ${task}.`,
      reactivated: `♻️ ${name} reactivated in ${task}.`,
      exists: `ℹ️ ${name} is already in ${task}.`,
    }[result];
    await ctx.reply(line);
  });

  bot.command('remove_user', async (ctx) => {
    if (!(await ownerOnly(ctx))) return;
    const task = (ctx.match ?? '').trim().split(/\s+/)[0]?.toLowerCase();
    if (!task) {
      await ctx.reply('Usage: /remove_user task_name (reply to a user)');
      return;
    }
    const target = replyToUser(ctx);
    if (!target) {
      await ctx.reply("❌ Reply to a real user's message.");
      return;
    }
    if (!(await repo.taskExists(task))) {
      await ctx.reply('❌ Task does not exist.');
      return;
    }
    const name = await ctx.names.remember(target);
    if (!(await repo.deactivateUser(task, target.id))) {
      await ctx.reply(`ℹ️ ${name} is not in ${task}.`);
      return;
    }
    // Removing somebody must not move anybody else's turn — say who is up now,
    // rather than the old "rotation preserved" that was not true.
    const upcoming = await duty.preview(task, 1);
    if (upcoming.length === 0) {
      await ctx.reply(`✅ ${name} removed. ${task} now has nobody in its rotation.`);
      return;
    }
    await ctx.reply(
      `✅ ${name} removed from ${task}. Next up: ${await ctx.names.resolve(upcoming[0])}.`,
    );
  });

  bot.command('cancel', async (ctx) => {
    if (!(await ownerOnly(ctx))) return;
    const replied = ctx.message?.reply_to_message;
    if (!replied) {
      await ctx.reply('❌ Reply to a task action message to cancel it.');
      return;
    }
    const action = await repo.actionByMessage(ctx.chat!.id, replied.message_id);
    if (!action) {
      await ctx.reply('❌ Cannot find a task action for this message.');
      return;
    }

    let consumed: number[] = [];
    try {
      consumed = JSON.parse(action.consumed_credits ?? '[]');
    } catch {
      consumed = [];
    }

    // Undo the exact row this message created. Replying to an older
    // confirmation used to delete the user's most recent entry instead.
    if (action.target_rowid !== null) await repo.deleteHistory(action.target_rowid);
    await duty.undoTurn(action.task_name, action.prev_cursor, consumed);
    await repo.clearCooldown(action.task_name, action.user_id);
    await repo.deleteAction(action.id);

    if (action.action_type === 'VOLUNTEER') {
      await repo.removeCredit(action.task_name, action.user_id);
      await repo.deleteLatestVolunteerLog(action.task_name, action.user_id);
      await ctx.reply(
        `↩️ Cover cancelled for ${action.task_name}.\n` +
          '❌ Credit removed, and the turn goes back to whoever had it.',
      );
      return;
    }

    const refunded = consumed.length ? `\n🎫 ${consumed.length} skip credit(s) refunded.` : '';
    await ctx.reply(
      `↩️ Task completion cancelled.\n🔁 User is responsible again for ${action.task_name}.${refunded}`,
    );
  });

  bot.command('data', async (ctx) => {
    if (!(await ownerOnly(ctx))) return;
    const rows = await repo.activitySince(daysAgoIso(30));
    if (rows.length === 0) {
      await ctx.reply('No history data for the last 30 days.');
      return;
    }
    const names = await ctx.names.resolveAll(rows.map((r) => r.user_id));
    const csv = buildCsv(rows, names, env.BOT_TIMEZONE);
    await ctx.replyWithDocument(
      new (globalThis as any).InputFile(
        // utf-8 BOM: without it Excel mangles non-English names.
        new TextEncoder().encode('﻿' + csv),
        'history_last_30_days.csv',
      ),
      { caption: '📊 Duty history (last 30 days)' },
    );
  });

  // ---------- read-only ----------

  bot.command('now', async (ctx) => {
    if (!(await inApartment(ctx))) return;
    await ctx.reply(await buildDigest(repo, duty, ctx.names));
  });

  bot.command('show', async (ctx) => {
    if (!(await inApartment(ctx))) return;
    const task = (ctx.match ?? '').trim().split(/\s+/)[0]?.toLowerCase();
    if (!task) {
      await ctx.reply('Usage: /show task_name');
      return;
    }
    if (!(await repo.taskExists(task))) {
      await ctx.reply(`❌ There is no task called '${task}'. /tasks lists them all.`);
      return;
    }
    const upcoming = await duty.preview(task, 5);
    if (upcoming.length === 0) {
      await ctx.reply('No users assigned to this task.');
      return;
    }
    const names = await ctx.names.resolveAll(upcoming);
    await ctx.reply(
      ['🔮 Next 5 turns:', ...upcoming.map((id) => names.get(id) ?? `User(${id})`)].join('\n'),
    );
  });

  bot.command('tasks', async (ctx) => {
    if (!(await inApartment(ctx))) return;
    const tasks = await repo.allTasks();
    if (tasks.length === 0) {
      await ctx.reply('No tasks configured yet.');
      return;
    }
    await ctx.reply('📋 All tasks:\n' + tasks.map((t) => `• /${t}`).join('\n'));
  });

  bot.command('my_tasks', async (ctx) => {
    if (!(await inApartment(ctx))) return;
    const tasks = await repo.userTasks(ctx.from!.id);
    if (tasks.length === 0) {
      await ctx.reply('You are not assigned to any tasks.');
      return;
    }
    await ctx.reply('🧾 Your tasks:\n' + tasks.map((t) => `- /${t}`).join('\n'));
  });

  bot.command('credits', async (ctx) => {
    if (!(await inApartment(ctx))) return;
    const arg = (ctx.match ?? '').trim().split(/\s+/)[0]?.toLowerCase();
    const all = await repo.allTasks();
    const tasks = arg ? all.filter((t) => t === arg) : all;
    if (tasks.length === 0) {
      await ctx.reply('No such task. /tasks lists them all.');
      return;
    }
    const lines = ['🎫 Skip credits'];
    for (const task of tasks) {
      const roster = await repo.roster(task);
      const credits = await repo.credits(task);
      const holders: string[] = [];
      for (const member of roster) {
        const balance = credits.get(member.user_id) ?? 0;
        if (balance > 0) holders.push(`${await ctx.names.resolve(member.user_id)} × ${balance}`);
      }
      lines.push(`🔹 ${task}: ${holders.length ? holders.join(', ') : 'nobody'}`);
    }
    await ctx.reply(lines.join('\n'));
  });

  bot.command('history', async (ctx) => {
    if (!(await inApartment(ctx))) return;
    const task = (ctx.match ?? '').trim().split(/\s+/)[0]?.toLowerCase();
    const tz = env.BOT_TIMEZONE;

    if (task) {
      if (!(await repo.taskExists(task))) {
        await ctx.reply(`❌ There is no task called '${task}'. /tasks lists them all.`);
        return;
      }
      const rows = await repo.taskHistory(task, 3);
      if (rows.length === 0) {
        await ctx.reply('No history for this task.');
        return;
      }
      const names = await ctx.names.resolveAll(rows.map((r) => r.user_id));
      await ctx.reply(
        [
          `🕒 Last ${task} duties:`,
          ...rows.map(
            (r) => `${localDate(r.done_at, tz)} – ${names.get(r.user_id) ?? `User(${r.user_id})`}`,
          ),
        ].join('\n'),
      );
      return;
    }

    const rows = await repo.userHistory(ctx.from!.id, 10);
    if (rows.length === 0) {
      await ctx.reply('No history found.');
      return;
    }
    await ctx.reply(
      [
        '🕒 Your last duties:',
        ...rows.map((r) => `${localDate(r.done_at, tz)} – ${r.task_name}`),
      ].join('\n'),
    );
  });

  // ---------- the duty commands themselves ----------
  //
  // Registered last and as a catch-all, so it only sees commands none of the
  // above claimed. grammY runs middleware in order, and each handler above
  // ends the chain, so there is no equivalent of the handler-group trap that
  // silently disabled group registration in the Python bot.

  bot.on('message:text', async (ctx, next) => {
    const text = ctx.message.text;
    if (!text.startsWith('/')) return next();

    // Quiet: an unrecognised group should not be scolded for every command its
    // own other bots receive.
    if (!(await inApartment(ctx, true))) return;

    const task = text.split(/\s+/)[0].slice(1).split('@')[0].toLowerCase();
    const user = ctx.from!;

    if (!(await repo.taskExists(task))) {
      // Silence for every unknown command is right — other bots live here. But
      // a near-miss is almost always a typo, and silence used to get the typist
      // blamed for skipping their turn.
      const suggestion = closestTask(task, await repo.allTasks());
      if (suggestion) {
        await ctx.reply(
          `❓ No task called /${task}. Did you mean /${suggestion}? /tasks lists them all.`,
        );
      }
      return;
    }

    if (!(await repo.isMember(task, user.id))) {
      await ctx.reply(
        `❌ You are not in the ${task} rotation, so this does not count. Ask an admin to add you.`,
      );
      return;
    }

    if (await repo.inCooldown(task, user.id)) {
      await ctx.reply('⏳ You already used this task recently. Try again later.');
      return;
    }

    const upcoming = await duty.preview(task, 1);
    if (upcoming.length === 0) {
      await ctx.reply('❌ No users assigned to this task.');
      return;
    }
    const responsible = upcoming[0];
    const isMyTurn = responsible === user.id;

    const taken = await duty.takeTurn(task);
    if (!taken) {
      await ctx.reply('❌ No users assigned to this task.');
      return;
    }

    const me = formatUser(user);

    if (isMyTurn) {
      const rowid = await repo.addHistory(task, user.id);
      await repo.touchCooldown(task, user.id);
      const sent = await ctx.reply(`✅ ${task} completed by ${me}. Thanks!`);
      await repo.logAction({
        task_name: task,
        user_id: user.id,
        action_type: 'DONE',
        chat_id: ctx.chat!.id,
        message_id: sent.message_id,
        prev_cursor: taken.prevCursor,
        consumed_credits: JSON.stringify(taken.consumed),
        target_rowid: rowid,
      });
      return;
    }

    // Covering somebody else's turn completes it. The rotation moves on, the
    // person who was up gets this one free, and the volunteer earns the credit
    // that lets them sit out a future turn. Because a credit now costs a real
    // turn, there is nothing to farm — the old rule handed out one every two
    // hours for typing a word.
    if (!(await repo.addCredit(task, user.id))) {
      await duty.undoTurn(task, taken.prevCursor, taken.consumed);
      await ctx.reply(`❌ Could not record a credit for ${task}. Ask an admin to re-add you.`);
      return;
    }

    const rowid = await repo.addHistory(task, user.id);
    await repo.addVolunteerLog(task, user.id);
    await repo.touchCooldown(task, user.id);

    const coveredName = await ctx.names.resolve(taken.turnOwner);
    const sent = await ctx.reply(
      `🙌 ${me} covered ${task} for ${coveredName}. +1 skip credit, and ${task} moves on.`,
    );
    await repo.logAction({
      task_name: task,
      user_id: user.id,
      action_type: 'VOLUNTEER',
      chat_id: ctx.chat!.id,
      message_id: sent.message_id,
      prev_cursor: taken.prevCursor,
      consumed_credits: JSON.stringify(taken.consumed),
      target_rowid: rowid,
    });
  });

  bot.catch((err) => {
    // Nothing logged a handler crash in the Python bot, so it just went quiet.
    console.error('handler failed', err.error);
  });

  return bot;
}

export { RESERVED_NAMES, TASK_NAME_RE, buildCsv, buildDigest, closestTask } from './format';
