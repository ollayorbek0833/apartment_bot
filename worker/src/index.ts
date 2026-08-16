/**
 * ApartmentMate on Cloudflare Workers.
 *
 * Two entry points:
 *   fetch     — Telegram posts updates to /webhook; everything else is a health
 *               check or the one-time setup route.
 *   scheduled — the Cron Triggers in wrangler.toml, which run in UTC.
 *
 * There is no long-running process, so nothing to keep alive and nothing to
 * restart. Free tier: 100,000 requests a day against maybe 300 used.
 */
import { webhookCallback } from 'grammy';

import { DutyService } from './core/service';
import { Repo } from './db/repo';
import type { Env } from './env';
import { buildDigest, createBot } from './tg/bot';
import { NameResolver } from './tg/names';
import { daysAgoIso } from './tg/time';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/health') {
      return new Response('ok');
    }

    if (url.pathname === '/webhook' && request.method === 'POST') {
      // Telegram echoes the secret back on every update. Without this check
      // anyone who learns the Worker URL can post forged updates and drive the
      // rotation. grammY verifies it when the token is supplied.
      const bot = createBot(env, env.DB);
      const handle = webhookCallback(bot, 'cloudflare-mod', {
        secretToken: env.WEBHOOK_SECRET,
      });
      return handle(request);
    }

    return new Response('ApartmentMate', { status: 200 });
  },

  async scheduled(event: ScheduledController, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(runCron(event.cron, env));
  },
};

export async function runCron(cron: string, env: Env): Promise<void> {
  const repo = new Repo(env.DB);

  // 03:00 Asia/Tashkent — prune everything presented as a rolling 30 days.
  // The Python bot pruned only completions and let the volunteer log grow
  // forever while /data claimed to show "the last 30 days".
  if (cron === '0 22 * * *') {
    await repo.prune(daysAgoIso(30));
    return;
  }

  // 09:00 Asia/Tashkent — the daily announcement, to the apartment only.
  const chatId = await repo.getApartmentChatId();
  if (chatId === null) {
    console.warn('no apartment claimed yet, skipping the daily announcement');
    return;
  }

  const bot = createBot(env, env.DB);
  await bot.init();
  const duty = new DutyService(repo);
  const names = new NameResolver(bot.api, repo, chatId);

  try {
    await bot.api.sendMessage(chatId, await buildDigest(repo, duty, names));
  } catch (err) {
    // A chat that has kicked the bot must not be retried silently every
    // morning forever, and a real failure must not vanish into a bare pass.
    console.error(`daily announcement failed for ${chatId}`, err);
  }
}
