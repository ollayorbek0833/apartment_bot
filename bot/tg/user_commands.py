from telegram import Update
from telegram.ext import ContextTypes
from db.repositories import (
    add_credit,
    add_history,
    get_task_users
)


async def volunteer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    command = update.message.text.split()[0]
    task_name = command[1:]  # remove /

    user = update.effective_user
    if not user:
        return

    users = get_task_users(task_name)
    user_ids = [u["user_id"] for u in users]

    if user.id not in user_ids:
        await update.message.reply_text("❌ You are not part of this task.")
        return

    add_history(task_name, user.id)
    add_credit(task_name, user.id)

    await update.message.reply_text(
        f"✅ You volunteered for '{task_name}'. (+1 skip credit)"
    )


async def my_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return

    tasks = []
    from bot.db.connection import get_connection
    conn = get_connection()

    cur = conn.execute(
        "SELECT task_name FROM task_users WHERE user_id = ? AND active = 1",
        (user.id,)
    )

    for row in cur.fetchall():
        tasks.append(row["task_name"])

    if not tasks:
        await update.message.reply_text("You are not assigned to any tasks.")
        return

    text = "🧾 Your tasks:\n" + "\n".join(f"- {t}" for t in tasks)
    await update.message.reply_text(text)
