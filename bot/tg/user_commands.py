from difflib import get_close_matches

from telegram import Update
from telegram.ext import ContextTypes

from core.rotation_engine import get_next_responsible
from core.simulation import simulate_next
from db.connection import get_db
from db.repositories import (
    add_credit,
    add_history, get_credit, get_task_users, is_in_cooldown, update_cooldown,
    add_volunteer_log, is_task_member, log_action, task_exists, get_all_tasks
)
from tg.utils import format_user


async def task_command(update, context):
    message = update.message
    user = update.effective_user
    chat = update.effective_chat

    if not message or not message.text or not user or not chat:
        return

    if chat.type not in ("group", "supergroup"):
        return

    task_name = message.text.split()[0][1:].split("@")[0].lower()

    if not task_exists(task_name):
        # Staying silent for every unknown command is right — other bots live in
        # this group. But a near-miss is almost always a typo for a real duty,
        # and silence used to get the typist blamed for skipping their turn.
        close = get_close_matches(task_name, get_all_tasks(), n=1, cutoff=0.7)
        if close:
            await message.reply_text(
                f"❓ No task called /{task_name}. Did you mean /{close[0]}? /tasks lists them all."
            )
        return

    # 1. Only people in this duty's rotation can act on it. Without this the bot
    #    told a bystander "+1 skip credit" while storing nothing, because the
    #    UPDATE had no row to hit.
    if not is_task_member(task_name, user.id):
        await message.reply_text(
            f"❌ You are not in the {task_name} rotation, so this does not count. "
            f"Ask an admin to add you."
        )
        return

    # 2. Cooldown check
    if is_in_cooldown(task_name, user.id):
        await message.reply_text(
            "⏳ You already used this task recently. Try again later."
        )
        return

    # 3. Who is responsible right now (read-only)
    simulation = simulate_next(task_name, 1)
    if not simulation:
        await message.reply_text("❌ No users assigned to this task.")
        return

    responsible_id = simulation[0]

    # 4. If user IS responsible -> EXECUTE task
    if user.id == responsible_id:
        executed_user_id, prev_cursor, consumed = get_next_responsible(task_name)
        if executed_user_id is None:
            await message.reply_text("❌ No users assigned to this task.")
            return

        history_rowid = add_history(task_name, executed_user_id)
        update_cooldown(task_name, user.id)

        reply = await message.reply_text(
            f"✅ {task_name} completed by {format_user(user)}. Thanks!"
        )
        log_action(task_name, user.id, "DONE", chat.id, reply.message_id,
                   prev_cursor=prev_cursor, consumed_credits=consumed,
                   target_rowid=history_rowid)
        return

    # 5. Otherwise -> VOLUNTEER
    if not add_credit(task_name, user.id):
        await message.reply_text(
            f"❌ Could not record a credit for {task_name}. Ask an admin to re-add you."
        )
        return

    volunteer_rowid = add_volunteer_log(task_name, user.id)
    update_cooldown(task_name, user.id)

    reply = await message.reply_text(
        f"🙌 Thanks for volunteering for {task_name}! +1 skip credit"
    )
    log_action(task_name, user.id, "VOLUNTEER", chat.id, reply.message_id,
               target_rowid=volunteer_rowid)

async def my_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not update.message:
        return

    with get_db() as conn:
        cur = conn.execute(
            "SELECT task_name FROM task_users WHERE user_id = ? AND active = 1 ORDER BY task_name",
            (user.id,)
        )
        tasks = [row["task_name"] for row in cur.fetchall()]

    if not tasks:
        await update.message.reply_text("You are not assigned to any tasks.")
        return

    text = "🧾 Your tasks:\n" + "\n".join(f"- /{t}" for t in tasks)
    await update.message.reply_text(text)

async def tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    tasks = get_all_tasks()

    if not tasks:
        await update.message.reply_text("No tasks configured yet.")
        return

    text = "📋 All tasks:\n" + "\n".join(f"• /{t}" for t in tasks)
    await update.message.reply_text(text)


async def credits_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the skip-credit ledger.

    Credits decide who gets skipped, and nothing in the bot ever displayed them,
    so a wrong balance was invisible to everyone until somebody felt cheated.
    """
    chat = update.effective_chat
    if not update.message or not chat:
        return

    tasks = [context.args[0].lower()] if context.args else get_all_tasks()
    tasks = [t for t in tasks if task_exists(t)]

    if not tasks:
        await update.message.reply_text("No such task. /tasks lists them all.")
        return

    lines = ["🎫 Skip credits"]
    for task in tasks:
        holders = []
        for row in get_task_users(task):
            balance = get_credit(task, row["user_id"])
            if balance <= 0:
                continue
            try:
                member = await context.bot.get_chat_member(chat.id, row["user_id"])
                name = format_user(member.user)
            except Exception:
                name = f"User({row['user_id']})"
            holders.append(f"{name} × {balance}")
        lines.append(f"🔹 {task}: " + (", ".join(holders) if holders else "nobody"))

    await update.message.reply_text("\n".join(lines))
