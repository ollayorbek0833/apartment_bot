export interface Env {
  DB: D1Database;

  /** Secret: from @BotFather. `wrangler secret put BOT_TOKEN` */
  BOT_TOKEN: string;
  /** Secret: your numeric Telegram user id. `wrangler secret put OWNER_TELEGRAM_ID` */
  OWNER_TELEGRAM_ID: string;
  /**
   * Secret: any long random string. Telegram sends it back in the
   * X-Telegram-Bot-Api-Secret-Token header on every update, which is the only
   * thing stopping a stranger who guesses the Worker URL from posting fake
   * updates. `wrangler secret put WEBHOOK_SECRET`
   */
  WEBHOOK_SECRET: string;

  /** Plain vars, in wrangler.toml. */
  BOT_TIMEZONE: string;
  ANNOUNCE_HOUR: string;
}

export function ownerId(env: Env): number {
  return Number(env.OWNER_TELEGRAM_ID);
}
