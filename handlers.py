from aiogram import Router, types
from aiogram.filters import Command
from database import mark_done, unmark_done

router = Router()

TASK_COMMANDS = {
    "cook": "cook",
    "bathroom": "bathroom",
    "room1": "room1",
    "room2": "room2",
}


@router.message(Command(*TASK_COMMANDS.keys()))
async def volunteer(message: types.Message):
    task = TASK_COMMANDS[message.text[1:]]
    await mark_done(task, message.from_user.id)
    await message.reply(
        f"✅ {message.from_user.full_name} did **{task}** today",
        parse_mode="Markdown"
    )


@router.message(Command("cancel"))
async def cancel_task(message: types.Message):
    if not message.reply_to_message:
        return

    member = await message.bot.get_chat_member(
        message.chat.id, message.from_user.id
    )
    if member.status not in ["administrator", "creator"]:
        await message.reply("❌ Only admins can cancel")
        return

    replied = message.reply_to_message
    if not replied.text or not replied.text.startswith("/"):
        return

    task = replied.text[1:]
    await unmark_done(task, replied.from_user.id)

    await message.reply(
        f"❌ {replied.from_user.full_name}'s **{task}** was cancelled",
        parse_mode="Markdown"
    )
