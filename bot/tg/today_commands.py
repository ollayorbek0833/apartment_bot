from db.connection import get_connection
from core.simulation import simulate_next
from tg.utils import format_user


async def build_today_text(bot, chat_id):
    """
    READ-ONLY.
    Shows who is responsible right now WITHOUT rotating
    and WITHOUT exposing skipped users.
    """
    conn = get_connection()
    cur = conn.execute("SELECT task_name FROM tasks")
    tasks = [row["task_name"] for row in cur.fetchall()]

    if not tasks:
        return "No tasks configured."

    lines = ["📍 Current Responsibilities"]

    for task in tasks:
        # simulate enough turns to find first non-skipped user
        simulation = simulate_next(task, 10)

        responsible_user_id = None

        for user_id, skipped in simulation:
            if not skipped:
                responsible_user_id = user_id
                break

        if responsible_user_id is None:
            lines.append(f"🔹 {task}: no users")
            continue

        try:
            member = await bot.get_chat_member(chat_id, responsible_user_id)
            display_name = format_user(member.user)
        except Exception:
            display_name = f"User({responsible_user_id})"

        lines.append(f"🔹 {task}: {display_name}")

    return "\n".join(lines)


async def now(update, context):
    chat = update.effective_chat
    if not chat:
        return

    text = await build_today_text(context.bot, chat.id)
    await update.message.reply_text(text)


async def run_today_for_all_groups(app):
    """
    Daily automatic /today — STILL READ-ONLY
    """
    for chat_id in app.bot_data.get("groups", []):
        text = await build_today_text(app.bot, chat_id)
        await app.bot.send_message(chat_id, text)
