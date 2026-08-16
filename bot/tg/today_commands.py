import logging

from telegram.error import Forbidden, BadRequest

from db.connection import get_db
from core.simulation import simulate_next
from tg.utils import format_user

log = logging.getLogger(__name__)


async def build_today_text(bot, chat_id):
    """
    READ-ONLY.
    Shows who is responsible right now WITHOUT rotating
    and WITHOUT exposing skipped users.
    """
    with get_db() as conn:
        cur = conn.execute("SELECT task_name FROM tasks ORDER BY task_name")
        tasks = [row["task_name"] for row in cur.fetchall()]

    if not tasks:
        return "No tasks configured."

    lines = ["📍 Current Responsibilities"]

    for task in tasks:
        simulation = simulate_next(task, 1)

        if not simulation:
            lines.append(f"🔹 /{task}: no users")
            continue

        responsible_user_id = simulation[0]

        try:
            member = await bot.get_chat_member(chat_id, responsible_user_id)
            display_name = format_user(member.user)
        except Exception:
            display_name = f"User({responsible_user_id})"

        # Leading slash so the duty is tappable straight from the digest.
        lines.append(f"🔹 /{task}: {display_name}")

    return "\n".join(lines)


async def now(update, context):
    chat = update.effective_chat
    if not chat or not update.message:
        return

    text = await build_today_text(context.bot, chat.id)
    await update.message.reply_text(text)


async def run_today_for_all_groups(app):
    """
    Daily automatic announcement — STILL READ-ONLY.

    A group the bot has been thrown out of is dropped from the list instead of
    being retried every morning forever, and anything else is logged rather than
    swallowed by a bare `pass`.
    """
    from db.repositories import get_all_groups, remove_group

    for chat_id in get_all_groups():
        try:
            text = await build_today_text(app.bot, chat_id)
            await app.bot.send_message(chat_id, text)
        except Forbidden:
            log.info("no longer allowed to post in %s, dropping it", chat_id)
            remove_group(chat_id)
        except BadRequest as exc:
            if "chat not found" in str(exc).lower():
                log.info("chat %s is gone, dropping it", chat_id)
                remove_group(chat_id)
            else:
                log.warning("daily announcement failed for %s: %s", chat_id, exc)
        except Exception as exc:
            log.warning("daily announcement failed for %s: %s", chat_id, exc)
