from telegram import Update
from telegram.ext import ContextTypes


HELP_TEXT = """
🤖 Apartment Duty Bot – Help

This bot manages apartment duties fairly using a fixed rotation and skip credits.

━━━━━━━━━━━━
👤 USER COMMANDS
━━━━━━━━━━━━

/task_name
• Volunteer for a task (example: /cook, /bathroom)
• You get +1 skip credit for that task
• Skip credits are used automatically in future turns
• No daily limits

/today
• Shows who is responsible TODAY for each task
• Rotation + skip credits are applied
• Also shows the last person who did each task

/my_tasks
• Shows which tasks you are part of

/history
• Shows your last 10 completed duties (all tasks)

/history task_name
• Shows the last 3 times YOU did that task

━━━━━━━━━━━━
🧠 HOW ROTATION WORKS
━━━━━━━━━━━━

• Each task has its own fixed order
• Volunteering gives skip credits
• If you have 3 credits → you are skipped 3 future turns
• Skips are consumed one by one
• Rotation order is NEVER changed

━━━━━━━━━━━━
🛠 ADMIN COMMANDS
━━━━━━━━━━━━

/add_task task_name
• Create a new task

/add_user task_name  (reply to a user)
• Add a user to a task team

/remove_user task_name  (reply to a user)
• Remove user without breaking rotation

/show_team task_name
• Shows the NEXT 5 turns
• Includes skipped users
• Simulation only (does NOT change anything)

━━━━━━━━━━━━
📌 NOTES
━━━━━━━━━━━━

• No daily reset
• History is kept for 30 days
• Bot works only in groups
• Only admins can manage tasks
"""


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT)
