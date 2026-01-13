from core.simulation import simulate_next
from telegram import Update
from telegram.ext import ContextTypes

from db.connection import get_connection
from tg.permissions import is_allowed
from db.repositories import create_task, task_exists, add_user_to_task, remove_credit, remove_volunteer_log, \
    remove_last_history
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

    for user_id, skipped in simulation:
        try:
            member = await context.bot.get_chat_member(chat.id, user_id)
            name = format_user(member.user)
        except Exception:
            name = f"User({user_id})"

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


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # admin + owner check
    if not await is_allowed(update, context):
        return

    message = update.message
    if not message or not message.reply_to_message:
        await message.reply_text("❌ Reply to a task action message to cancel it.")
        return

    replied = message.reply_to_message
    text = replied.text or ""

    chat = update.effective_chat
    if not chat:
        return

    # Try to detect task name from message
    # Expected formats:
    # ✅ cook completed by ...
    # 🙌 Thanks for volunteering for cook! +1 skip credit
    task_name = None

    if "completed by" in text:
        task_name = text.split(" ")[1]
        action_type = "responsible"
    elif "volunteering for" in text:
        task_name = text.split("volunteering for ")[1].split("!")[0]
        action_type = "volunteer"
    else:
        await message.reply_text("❌ Cannot detect task action from this message.")
        return

    user = replied.from_user
    if not user:
        return

    # 🧹 CANCEL LOGIC
    if action_type == "volunteer":
        remove_credit(task_name, user.id)
        remove_volunteer_log(task_name, user.id)

        await message.reply_text(
            f"↩️ Volunteer action cancelled.\n"
            f"❌ Credit removed"
        )

    elif action_type == "responsible":
        remove_last_history(task_name, user.id)

        await message.reply_text(
            f"↩️ Task completion cancelled.\n"
            f"🔁 User is responsible again for *{task_name}*.",
            parse_mode="Markdown"
        )
