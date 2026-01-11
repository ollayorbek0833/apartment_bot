from core.simulation import simulate_next
from telegram import Update
from telegram.ext import ContextTypes

from db.connection import get_connection
from tg.permissions import is_allowed
from db.repositories import create_task, task_exists, add_user_to_task
from tg.utils import format_user


async def add_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_allowed(update, context):
        return

    if not context.args:
        await update.message.reply_text("Usage: /add_task task_name")
        return

    task_name = context.args[0]

    if task_exists(task_name):
        await update.message.reply_text("⚠️ Task already exists.")
        return

    create_task(task_name)
    await update.message.reply_text(f"✅ Task '{task_name}' created.")


async def add_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_allowed(update, context):
        return

    if not context.args:
        await update.message.reply_text("Usage: /add_user task_name (reply to user)")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("❌ You must reply to a user.")
        return

    task_name = context.args[0]
    user_id = update.message.reply_to_message.from_user.id

    if not task_exists(task_name):
        await update.message.reply_text("❌ Task does not exist.")
        return

    result = add_user_to_task(task_name, user_id)

    if result == "added":
        await update.message.reply_text("✅ User added to task.")
    elif result == "reactivated":
        await update.message.reply_text("♻️ User reactivated in task.")
    else:
        await update.message.reply_text("ℹ️ User is already in this task.")


async def show_team(update, context):
    if not await is_allowed(update, context):
        return

    task = context.args[0]
    simulation = simulate_next(task, 5)

    lines = ["🔮 Next 5 turns:"]

    for user_id, skipped in simulation:
        tg_user = await context.bot.get_chat_member(
            update.effective_chat.id,
            user_id
        )

        name = format_user(tg_user.user)

        if skipped:
            lines.append(f"{name} (skipped)")
        else:
            lines.append(name)

    await update.message.reply_text("\n".join(lines))


async def remove_user(update, context):
    if not await is_allowed(update, context):
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a user.")
        return

    task = context.args[0]
    user_id = update.message.reply_to_message.from_user.id

    conn = get_connection()
    with conn:
        conn.execute(
            """
            UPDATE task_users
            SET active = 0
            WHERE task_name = ? AND user_id = ?
            """,
            (task, user_id)
        )

    await update.message.reply_text("User removed (rotation preserved).")