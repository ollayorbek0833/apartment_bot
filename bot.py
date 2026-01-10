import asyncio
from aiogram import Bot, Dispatcher
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import BOT_TOKEN, ANNOUNCE_HOUR, ANNOUNCE_MINUTE, TIMEZONE, GROUP_ID
from database import init_db
from handlers import router
from scheduler import send_daily_turns






async def main():
    await init_db()

    bot = Bot(BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)


    scheduler = AsyncIOScheduler(timezone=TIMEZONE)
    scheduler.add_job(
        send_daily_turns,
        "cron",
        hour=ANNOUNCE_HOUR,
        minute=ANNOUNCE_MINUTE,
        args=[bot, GROUP_ID]
    )
    scheduler.start()

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
