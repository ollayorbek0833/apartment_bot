from telegram import Update
from telegram.ext import ContextTypes
from tg.permissions import is_allowed


USER_HELP_TEXT = """
🤖 ApartmentMate – Help

━━━━━━━━━━━━
👤 USER COMMANDS
━━━━━━━━━━━━

/now
• Shows who is responsible RIGHT NOW
• Read-only (does not rotate)

/task_name
• Example: /cook, /oshxona
• If it is your turn → task is completed
• If not your turn → you volunteer (+1 skip credit)
• Same task command is ignored for 2 hours

/show task_name
• Shows next 5 turns for a task
• Read-only

/history
• Shows your last 10 completed duties

/history task_name
• Shows last 3 completions of that task
• Format: DD.MM – @username

/my_tasks
• Shows tasks you belong to

━━━━━━━━━━━━
📌 NOTES
━━━━━━━━━━━━

• No daily reset
• Rotation is automatic and fair
• Skip credits are consumed automatically
"""


ADMIN_HELP_TEXT = """
🤖 ApartmentMate – Admin Help

━━━━━━━━━━━━
🛠 ADMIN COMMANDS
━━━━━━━━━━━━

/add_task task_name
• Create a new task

/add_user task_name  (reply to a user)
• Add user to task rotation

/remove_user task_name  (reply to a user)
• Remove user without breaking rotation

/show task_name
• Shows next 5 turns (simulation)
• Does NOT change anything

━━━━━━━━━━━━
🧠 ROTATION RULES
━━━━━━━━━━━━

• Each task has a fixed order
• Volunteering gives skip credits
• Credits skip future turns
• Rotation happens ONLY on task execution
• No daily reset

━━━━━━━━━━━━
⚠️ ADMIN NOTES
━━━━━━━━━━━━

• Be careful when adding/removing users
• Rotation order is preserved
"""


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(USER_HELP_TEXT)


async def help_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_allowed(update, context):
        await update.message.reply_text("❌ This command is for admins only.")
        return

    await update.message.reply_text(ADMIN_HELP_TEXT)
