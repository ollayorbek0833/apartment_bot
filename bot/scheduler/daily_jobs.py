from apscheduler.schedulers.asyncio import AsyncIOScheduler
from db.repositories import cleanup_history
from telegram.ext import Application
from tg.today_commands import run_today_for_all_groups

scheduler = AsyncIOScheduler()


def setup_scheduler(app: Application):
    # daily /today at 09:00 local time
    scheduler.add_job(
        run_today_for_all_groups,
        trigger="cron",
        hour=9,
        minute=0,
        args=[app]
    )

    # daily history cleanup
    scheduler.add_job(
        cleanup_history,
        trigger="cron",
        hour=3,
        minute=0
    )
