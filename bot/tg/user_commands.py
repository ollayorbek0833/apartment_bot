from telegram import Update
from telegram.ext import ContextTypes

from core.rotation_engine import get_next_responsible
from core.simulation import simulate_next
from db.repositories import (
    add_credit,
    add_history, is_in_cooldown, update_cooldown, add_volunteer_log,
    log_action, task_exists, get_all_tasks
)
from tg.utils import format_user


async def task_command(update, context):
    message = update.message
    user = update.effective_user
    chat = update.effective_chat

    if not message or not user or not chat:
        return

    task_name = message.text.split()[0][1:].split("@")[0]

    if not task_exists(task_name):
        return

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

    responsible_id = simulation[0]

    # 3️⃣ If user IS responsible → EXECUTE task
    if user.id == responsible_id:
        executed_user_id = get_next_responsible(task_name)

        # Save execution
        add_history(task_name, executed_user_id)
        update_cooldown(task_name, user.id)

        reply = await message.reply_text(
            f"✅ {task_name} completed by {format_user(user)}. Thanks!"
        )
        log_action(task_name, user.id, "DONE", chat.id, reply.message_id)
        return

    # 4️⃣ Otherwise → VOLUNTEER
    add_credit(task_name, user.id)
    add_volunteer_log(task_name, user.id)
    update_cooldown(task_name, user.id)

    reply = await message.reply_text(
        f"🙌 Thanks for volunteering for {task_name}! +1 skip credit"
    )
    log_action(task_name, user.id, "VOLUNTEER", chat.id, reply.message_id)

async def my_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return

    from db.connection import get_db
    with get_db() as conn:
        cur = conn.execute(
            "SELECT task_name FROM task_users WHERE user_id = ? AND active = 1",
            (user.id,)
        )
        tasks = [row["task_name"] for row in cur.fetchall()]

    if not tasks:
        await update.message.reply_text("You are not assigned to any tasks.")
        return

    text = "🧾 Your tasks:\n" + "\n".join(f"- {t}" for t in tasks)
    await update.message.reply_text(text)

async def tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tasks = get_all_tasks()

    if not tasks:
        await update.message.reply_text("No tasks configured yet.")
        return

    text = "📋 All tasks:\n" + "\n".join(f"• /{t}" for t in tasks)
    await update.message.reply_text(text)
