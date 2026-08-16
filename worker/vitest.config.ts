import { defineConfig } from 'vitest/config';
import { cloudflarePool } from '@cloudflare/vitest-pool-workers';

export default defineConfig({
  test: {
    pool: cloudflarePool({
      miniflare: {
        compatibilityDate: '2025-01-15',
        compatibilityFlags: ['nodejs_compat'],
        d1Databases: ['DB'],
        bindings: {
          BOT_TOKEN: '123456:TEST',
          OWNER_TELEGRAM_ID: '1',
          WEBHOOK_SECRET: 'test-secret',
          BOT_TIMEZONE: 'Asia/Tashkent',
          ANNOUNCE_HOUR: '9',
        },
      },
    }),
  },
});
