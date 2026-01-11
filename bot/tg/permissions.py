from telegram import Update
from telegram.ext import ContextTypes

from config import OWNER_TELEGRAM_ID


async def is_allowed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    chat = update.effective_chat
    user = update.effective_user

    if not chat or not user:
        return False

    if chat.type not in ("group", "supergroup"):
        await update.message.reply_text("❌ This bot works only in groups.")
        return False

    member = await context.bot.get_chat_member(chat.id, user.id)

    if member.status not in ("administrator", "creator"):
        await update.message.reply_text("❌ Admin permission required.")
        return False

    if user.id != OWNER_TELEGRAM_ID:
        await update.message.reply_text("❌ Bot owner authorization required.")
        return False

    return True
