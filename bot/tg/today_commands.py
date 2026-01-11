from core.rotation_engine import get_next_responsible
from db.connection import get_connection
from db.repositories import add_history


def build_today_text():
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

        add_history(task, user_id)
        lines.append(f"🔹 {task}: {user_id}")

    return "\n".join(lines)


async def today(update, context):
    text = build_today_text()
    await update.message.reply_text(text)


async def run_today_for_all_groups(app):
    for chat_id in app.bot_data.get("groups", []):
        await app.bot.send_message(chat_id, build_today_text())
