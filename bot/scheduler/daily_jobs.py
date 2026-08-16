import os
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from db.repositories import cleanup_history
from telegram.ext import Application
from tg.today_commands import run_today_for_all_groups

# The server runs in UTC; the apartment does not. Without an explicit timezone
# APScheduler uses the machine's, so "hour=9" fired at 14:00 in Tashkent.
TIMEZONE = ZoneInfo(os.getenv("BOT_TIMEZONE", "Asia/Tashkent"))
ANNOUNCE_HOUR = int(os.getenv("ANNOUNCE_HOUR", "9"))

scheduler = AsyncIOScheduler(timezone=TIMEZONE)


def setup_scheduler(app: Application):
    # daily announcement of who is responsible, in apartment local time
    scheduler.add_job(
        run_today_for_all_groups,
        trigger="cron",
        hour=ANNOUNCE_HOUR,
        minute=0,
        args=[app],
        id="daily_announcement",
        replace_existing=True,
        coalesce=True,
        misfire_grace_time=3600,
    )

    # daily history cleanup
    scheduler.add_job(
        cleanup_history,
        trigger="cron",
        hour=3,
        minute=0,
        id="cleanup_history",
        replace_existing=True,
        coalesce=True,
        misfire_grace_time=3600,
    )
