from core.rotation_engine import get_next_responsible
from db.connection import get_connection
from db.repositories import add_history
from tg.utils import format_user


async def build_today_text(bot, chat_id):
    """
    Builds today's duties text with proper user display names.
    This function:
    - Executes real rotation
    - Consumes credits
    - Saves history
    """
    conn = get_connection()
    cur = conn.execute("SELECT task_name FROM tasks")
    tasks = [row["task_name"] for row in cur.fetchall()]

    if not tasks:
        return "No tasks configured."

    lines = ["📅 Today’s Duties"]

    for task in tasks:
        user_id = get_next_responsible(task)
        if user_id is None:
            lines.append(f"🔹 {task}: no users")
            continue

        # save history (real execution)
        add_history(task, user_id)

        try:
            member = await bot.get_chat_member(chat_id, user_id)
            display_name = format_user(member.user)
        except Exception:
            # fallback if user left group or cannot be fetched
            display_name = f"User({user_id})"

        lines.append(f"🔹 {task}: {display_name}")

    return "\n".join(lines)


async def today(update, context):
    chat = update.effective_chat
    if not chat:
        return

    text = await build_today_text(context.bot, chat.id)
    await update.effective_message.reply_text(text)


async def run_today_for_all_groups(app):
    """
    Used by scheduler to send daily /today automatically
    """
    for chat_id in app.bot_data.get("groups", []):
        text = await build_today_text(app.bot, chat_id)
        await app.bot.send_message(chat_id, text)
