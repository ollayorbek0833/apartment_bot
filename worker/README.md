# ApartmentMate on Cloudflare Workers

The same bot, with no server. TypeScript and grammY on a webhook, D1 instead of
a SQLite file, Cron Triggers instead of APScheduler. Nothing runs between
requests, so there is nothing to keep alive, restart, patch or pay for.

The Python bot in `../bot/` still works and is untouched. Cut over when you are
ready; keep it as the fallback until then.

## Cost

Five people, maybe 300 requests a day. The free tier is 100,000 requests a day,
5 GB of D1 and 5 Cron Triggers. This uses two crons and a few hundred KB.
$0/month, with about 300× headroom.

## What runs when

| trigger | when | what |
|---|---|---|
| `POST /webhook` | every Telegram update | commands and duty actions |
| cron `0 4 * * *` | 09:00 Asia/Tashkent | the daily "who is responsible" post |
| cron `0 22 * * *` | 03:00 Asia/Tashkent | prune the rolling 30 days |

Cron expressions are **UTC**. Tashkent is UTC+5 with no daylight saving, so a
local hour is written five hours earlier. To move the morning post, change the
cron in `wrangler.toml` — `ANNOUNCE_HOUR` only labels it.

## First deploy

Run these from the `worker/` directory. Steps 1 and 2 need a browser.

    npm install
    npx wrangler login

Create the database, then paste the id it prints into `database_id` in
`wrangler.toml`:

    npx wrangler d1 create apartmentmate

Create the tables:

    npx wrangler d1 migrations apply apartmentmate --remote

Set the three secrets. `WEBHOOK_SECRET` is any long random string — it is what
stops a stranger who finds the Worker URL from posting fake updates:

    npx wrangler secret put BOT_TOKEN
    npx wrangler secret put OWNER_TELEGRAM_ID
    npx wrangler secret put WEBHOOK_SECRET

Deploy, and note the `https://apartmentmate.<subdomain>.workers.dev` URL:

    npx wrangler deploy

## Bringing your data across

Copy `bot.db` off the EC2 box, then:

    python3 scripts/export_sqlite_to_d1.py /path/to/bot.db > seed.sql
    npx wrangler d1 execute apartmentmate --remote --file=seed.sql

The script only reads the source file. It converts the old index-based rotation
cursor to the position-based one and normalises both timestamp formats, so
whoever was next before the move is still next after it. It deliberately skips
`task_actions`: that table only exists so `/cancel` can undo the last few hours,
and Telegram message ids do not survive a change of bot anyway.

It prints the apartment chat id it found. If your database knows several groups
it will say so — pass `--apartment-chat-id <id>`, or run `/claim` in the right
group after cutover.

## Pointing Telegram at the Worker

One command, with your own three values:

    curl -X POST "https://api.telegram.org/bot<BOT_TOKEN>/setWebhook" \
      -d "url=https://apartmentmate.<subdomain>.workers.dev/webhook" \
      -d "secret_token=<WEBHOOK_SECRET>" \
      -d "allowed_updates=[\"message\",\"my_chat_member\"]"

**Stop the EC2 service first** — `sudo systemctl stop apartmentmate`. Long
polling and a webhook cannot both be active: Telegram refuses to set a webhook
while another process is polling, and if the old service restarts it will steal
the updates back.

To undo and return to EC2:

    curl -X POST "https://api.telegram.org/bot<BOT_TOKEN>/deleteWebhook"
    sudo systemctl start apartmentmate

## Checking it worked

    curl https://apartmentmate.<subdomain>.workers.dev/health        # -> ok
    curl "https://api.telegram.org/bot<BOT_TOKEN>/getWebhookInfo"    # url set, 0 pending
    npx wrangler tail                                                # live logs

Then in the group: `/now` should name the same person the Python bot named.
`/credits` should show the same balances.

The morning post is the one thing you cannot test by typing. Force it once:

    npx wrangler dev --test-scheduled
    curl "http://localhost:8787/cdn-cgi/handler/scheduled?cron=0+4+*+*+*"

## Working on it

    npm test          # 41 tests, no network and no token needed
    npm run typecheck
    npm run dev       # local, against a local D1
    npm run db:local  # create the tables in the local D1

`src/core/` is pure logic with no Telegram and no SQL, which is where the
rotation rules live and where most of the tests point. `src/db/repo.ts` owns
every statement. `src/tg/` is the Telegram layer.
