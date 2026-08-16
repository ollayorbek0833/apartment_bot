import json
import re

from core.simulation import simulate_next
from telegram import Update
from telegram.ext import ContextTypes

from tg.permissions import is_allowed
from db.repositories import (
    create_task, task_exists, add_user_to_task, deactivate_user, remove_credit,
    remove_volunteer_log, remove_last_history, get_action_by_message, delete_action,
    refund_credits, clear_cooldown, set_cursor, get_task_users
)
from tg.utils import format_user

# A duty is typed as a Telegram command, so its name has to be a legal command:
# lowercase latin letters, digits and underscore, 1-32 characters.
TASK_NAME_RE = re.compile(r"^[a-z0-9_]{1,32}$")

# Names the bot already owns. A duty called "history" would be created happily
# and then never be executable, because CommandHandler("history") always wins.
RESERVED_TASK_NAMES = {
    "add_task", "add_user", "remove_user", "data",
    "now", "history", "my_tasks", "help", "help_admin",
    "show", "start", "cancel", "tasks", "credits",
}


async def add_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_allowed(update, context):
        return

    if not context.args:
        await update.message.reply_text("Usage: /add_task task_name")
        return

    task_name = context.args[0].lower()

    if not TASK_NAME_RE.match(task_name):
        await update.message.reply_text(
            "❌ A task name must be 1-32 characters of a-z, 0-9 or _ , because it "
            "becomes a command you type. Example: /add_task oshxona"
        )
        return

    if task_name in RESERVED_TASK_NAMES:
        await update.message.reply_text(
            f"❌ '{task_name}' is one of the bot's own commands. "
            f"Pick another name, otherwise /{task_name} would never reach the task."
        )
        return

    if task_exists(task_name):
        await update.message.reply_text("⚠️ Task already exists.")
        return

    create_task(task_name)
    await update.message.reply_text(f"✅ Task '{task_name}' created. Run it with /{task_name}")


async def add_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_allowed(update, context):
        return

    if not context.args:
        await update.message.reply_text("Usage: /add_user task_name (reply to user)")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("❌ You must reply to a user.")
        return

    target = update.message.reply_to_message.from_user
    if not target or target.is_bot:
        await update.message.reply_text("❌ Reply to a real user's message, not a bot.")
        return

    task_name = context.args[0].lower()
    user_id = target.id

    if not task_exists(task_name):
        await update.message.reply_text("❌ Task does not exist.")
        return

    result = add_user_to_task(task_name, user_id)

    if result == "added":
        await update.message.reply_text(f"✅ {format_user(target)} added to {task_name}.")
    elif result == "reactivated":
        await update.message.reply_text(f"♻️ {format_user(target)} reactivated in {task_name}.")
    else:
        await update.message.reply_text(f"ℹ️ {format_user(target)} is already in {task_name}.")


async def show_team(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    if not context.args:
        await update.message.reply_text("Usage: /show task_name")
        return

    task_name = context.args[0].lower()
    chat = update.effective_chat

    if not task_exists(task_name):
        await update.message.reply_text(
            f"❌ There is no task called '{task_name}'. /tasks lists them all."
        )
        return

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

    task = context.args[0].lower()

    if not task_exists(task):
        await update.message.reply_text("❌ Task does not exist.")
        return

    target = update.message.reply_to_message.from_user
    if not target:
        await update.message.reply_text("❌ Reply to a real user's message.")
        return

    if not deactivate_user(task, target.id):
        await update.message.reply_text(f"ℹ️ {format_user(target)} is not in {task}.")
        return

    remaining = get_task_users(task)
    if not remaining:
        await update.message.reply_text(
            f"✅ {format_user(target)} removed. {task} now has nobody in its rotation."
        )
        return

    upcoming = simulate_next(task, 1)
    next_up = ""
    if upcoming:
        try:
            member = await context.bot.get_chat_member(update.effective_chat.id, upcoming[0])
            next_up = f" Next up for {task}: {format_user(member.user)}."
        except Exception:
            next_up = f" Next up for {task}: User({upcoming[0]})."

    await update.message.reply_text(
        f"✅ {format_user(target)} removed from {task}.{next_up}"
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # admin + owner check
    if not await is_allowed(update, context):
        return

    message = update.message
    if not message:
        return
    if not message.reply_to_message:
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

    # Undo the row this message actually created, not merely the newest one —
    # replying /cancel to an old confirmation used to delete the wrong entry.
    target_rowid = action["target_rowid"]

    if action_type == "VOLUNTEER":
        remove_credit(task_name, user_id)
        remove_volunteer_log(task_name, user_id, rowid=target_rowid)
        clear_cooldown(task_name, user_id)
        delete_action(action["id"])

        await message.reply_text(
            "↩️ Volunteer action cancelled.\n"
            "❌ Credit removed"
        )
        return

    if action_type == "DONE":
        remove_last_history(task_name, user_id, rowid=target_rowid)

        # Put back exactly what the completion changed: the cursor it moved and
        # every skip credit it burned on the way. Rewinding the cursor by one and
        # leaving the credits spent is what used to make people lose a credit for
        # a turn that never happened.
        prev_cursor = action["prev_cursor"]
        if prev_cursor is not None:
            set_cursor(task_name, prev_cursor)

        try:
            consumed = json.loads(action["consumed_credits"] or "[]")
        except (TypeError, ValueError):
            consumed = []
        refund_credits(task_name, consumed)

        clear_cooldown(task_name, user_id)
        delete_action(action["id"])

        refunded = f"\n🎫 {len(consumed)} skip credit(s) refunded." if consumed else ""
        # No parse_mode: a task name may contain '_', which Markdown eats.
        await message.reply_text(
            f"↩️ Task completion cancelled.\n"
            f"🔁 User is responsible again for {task_name}.{refunded}"
        )
