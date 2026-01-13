from telegram import Update
from telegram.ext import ContextTypes

from core.rotation_engine import get_next_responsible
from core.simulation import simulate_next
from db.repositories import (
    add_credit,
    add_history, is_in_cooldown, update_cooldown, add_volunteer_log
)
from tg.utils import format_user


async def task_command(update, context):
    message = update.message
    user = update.effective_user
    chat = update.effective_chat

    if not message or not user or not chat:
        return

    task_name = message.text[1:]  # /cook -> cook

    # 1️⃣ Cooldown check
    if is_in_cooldown(task_name, user.id):
        await message.reply_text(
            "⏳ You already used this task recently. Try again later."
        )
        return

    # 2️⃣ Simulate today's responsible (READ-ONLY)
    simulation = simulate_next(task_name, 1)
    if not simulation:
        await message.reply_text("❌ No users assigned to this task.")
        return

    responsible_id, skipped = simulation[0]

    # 3️⃣ If user IS responsible → EXECUTE task
    if user.id == responsible_id:
        executed_user_id = get_next_responsible(task_name)

        # Save execution
        add_history(task_name, executed_user_id)
        update_cooldown(task_name, user.id)

        await message.reply_text(
            f"✅ {task_name} completed by {format_user(user)}. Thanks!"
        )
        return

    # 4️⃣ Otherwise → VOLUNTEER
    add_credit(task_name, user.id)
    add_volunteer_log(task_name, user.id)
    update_cooldown(task_name, user.id)

    await message.reply_text(
        f"🙌 Thanks for volunteering for {task_name}! +1 skip credit"
    )

async def my_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return

    tasks = []
    from db.connection import get_connection
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
