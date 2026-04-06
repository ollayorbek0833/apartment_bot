from core.simulation import simulate_next
from telegram import Update
from telegram.ext import ContextTypes

from db.connection import get_db
from tg.permissions import is_allowed
from db.repositories import (
    create_task, task_exists, add_user_to_task, remove_credit,
    remove_volunteer_log, remove_last_history, get_action_by_message, delete_action,
    get_cursor, set_cursor, get_task_users
)
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


async def show_team(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /show task_name")
        return

    task_name = context.args[0]
    chat = update.effective_chat

    simulation = simulate_next(task_name, 5)

    if not simulation:
        await update.message.reply_text("No users assigned to this task.")
        return

    lines = ["🔮 Next 5 turns:"]

    for user_id in simulation:
        try:
            member = await context.bot.get_chat_member(chat.id, user_id)
            name = format_user(member.user)
        except Exception:
            name = f"User({user_id})"

        lines.append(name)

    await update.message.reply_text("\n".join(lines))


async def remove_user(update, context):
    if not await is_allowed(update, context):
        return

    if not context.args:
        await update.message.reply_text("Usage: /remove_user task_name (reply to user)")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("❌ You must reply to a user.")
        return

    task = context.args[0]

    if not task_exists(task):
        await update.message.reply_text("❌ Task does not exist.")
        return
    user_id = update.message.reply_to_message.from_user.id

    with get_db() as conn:
        conn.execute(
            """
            UPDATE task_users
            SET active = 0
            WHERE task_name = ? AND user_id = ?
            """,
            (task, user_id)
        )

    await update.message.reply_text("User removed (rotation preserved).")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # admin + owner check
    if not await is_allowed(update, context):
        return

    message = update.message
    if not message or not message.reply_to_message:
        await message.reply_text("❌ Reply to a task action message to cancel it.")
        return

    replied = message.reply_to_message
    chat = update.effective_chat
    if not chat:
        return

    action = get_action_by_message(chat.id, replied.message_id)
    if not action:
        await message.reply_text("❌ Cannot find a task action for this message.")
        return

    task_name = action["task_name"]
    user_id = action["user_id"]
    action_type = action["action_type"]

    if action_type == "VOLUNTEER":
        remove_credit(task_name, user_id)
        remove_volunteer_log(task_name, user_id)
        delete_action(action["id"])

        await message.reply_text(
            f"↩️ Volunteer action cancelled.\n"
            f"❌ Credit removed"
        )

    elif action_type == "DONE":
        remove_last_history(task_name, user_id)
        # Revert cursor back by 1
        users = get_task_users(task_name)
        if users:
            current_cursor = get_cursor(task_name)
            reverted_cursor = (current_cursor - 1) % len(users)
            set_cursor(task_name, reverted_cursor)
        delete_action(action["id"])

        await message.reply_text(
            f"↩️ Task completion cancelled.\n"
            f"🔁 User is responsible again for *{task_name}*.",
            parse_mode="Markdown"
        )
