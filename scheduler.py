from database import (
    get_task_queue,
    done_today,
    rotate_queue,
    clear_daily_done,
)
from aiogram import Bot

TASKS = ["cook", "bathroom", "room1", "room2"]


async def send_daily_turns(bot: Bot, group_id: int):
    text = "🏠 *Today's Apartment Duties*\n\n"

    for task in TASKS:
        queue = await get_task_queue(task)
        done = await done_today(task)

        chosen = None
        for user_id in queue:
            if user_id in done:
                await rotate_queue(task, user_id)
            else:
                chosen = user_id
                break

        if chosen:
            user = await bot.get_chat_member(group_id, chosen)
            text += f"• **{task}**: {user.user.full_name}\n"

    await bot.send_message(group_id, text, parse_mode="Markdown")
    await clear_daily_done()
