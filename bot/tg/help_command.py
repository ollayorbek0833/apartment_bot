from telegram import Update
from telegram.ext import ContextTypes
from tg.apartment import in_apartment
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
• Only works if you are in that task's rotation
• If it is your turn → task is completed
• If not your turn → you cover it for whoever was up:
  the task is done, the rotation moves on, and you get
  +1 skip credit to sit out a future turn
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

/tasks
• Shows all available tasks

/credits
• Shows who is holding unused skip credits
• /credits task_name for one task

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

/data
• Exports the last 30 days of activity as a CSV
• Columns: date, time, task, user, type

/cancel  (reply to a bot confirmation message)
• Undoes that completion or cover
• Restores the rotation, the skip credits it spent, and the cooldown

/claim
• Makes THIS group the apartment the bot serves
• Only needed if the bot knew several groups before

━━━━━━━━━━━━
🧠 ROTATION RULES
━━━━━━━━━━━━

• Each task has a fixed order
• Covering somebody's turn completes it and gives you a credit
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
    if not update.message:
        return
    if not await in_apartment(update, quiet=True):
        return
    await update.message.reply_text(USER_HELP_TEXT)


async def help_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # is_allowed already replies with the reason; do not answer a second time.
    if not await is_allowed(update, context):
        return

    await update.message.reply_text(ADMIN_HELP_TEXT)
