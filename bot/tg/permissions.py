import logging

from telegram import Update
from telegram.ext import ContextTypes

from config import OWNER_TELEGRAM_ID
from tg.apartment import in_apartment

log = logging.getLogger(__name__)


async def is_allowed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Owner-only, group-only gate.

    Always replies with the reason itself, so callers must NOT add a second
    "admins only" message on top — that is why /data and /help_admin used to
    answer twice.
    """
    chat = update.effective_chat
    user = update.effective_user
    message = update.effective_message

    if not chat or not user or not message:
        return False

    if not await in_apartment(update):
        return False

    if user.id != OWNER_TELEGRAM_ID:
        await message.reply_text("❌ Bot owner authorization required.")
        return False

    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
    except Exception as exc:
        log.warning("get_chat_member failed in chat %s: %s", chat.id, exc)
        await message.reply_text(
            "❌ I could not check your permissions here. Make sure I am an admin in this group."
        )
        return False

    if member.status not in ("administrator", "creator"):
        await message.reply_text("❌ Admin permission required.")
        return False

    return True
