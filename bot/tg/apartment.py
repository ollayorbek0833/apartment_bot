"""The bot serves exactly one apartment group.

Nothing in the schema carries a chat id, so a second group would share the first
one's rotation, credits and history, and would receive its 09:00 announcement.
Rather than migrating seven tables, the bot belongs to one chat and politely
ignores every other one.
"""
import logging

from config import OWNER_TELEGRAM_ID
from db.repositories import claim_apartment_chat_id, get_apartment_chat_id

log = logging.getLogger(__name__)


def is_group(chat) -> bool:
    return bool(chat) and chat.type in ("group", "supergroup")


async def in_apartment(update, quiet: bool = False) -> bool:
    """True when this update belongs to the apartment this bot serves.

    The first group the OWNER uses the bot in is claimed automatically, so an
    existing installation needs no configuration. Any other chat is refused.
    """
    chat = update.effective_chat
    user = update.effective_user
    message = update.effective_message

    if not is_group(chat) or not user:
        if message and not quiet:
            await message.reply_text("❌ This bot works only in groups.")
        return False

    apartment = get_apartment_chat_id()

    if apartment is None:
        if user.id != OWNER_TELEGRAM_ID:
            # Do not let a stranger's group claim the bot.
            return False
        claim_apartment_chat_id(chat.id)
        log.info("claimed chat %s as the apartment", chat.id)
        return True

    if chat.id != apartment:
        if message and not quiet:
            await message.reply_text(
                "❌ This bot belongs to another apartment. Ask its owner to run their own copy."
            )
        return False

    return True
