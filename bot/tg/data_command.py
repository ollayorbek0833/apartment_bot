import csv
import io
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes

from tg.permissions import is_allowed
from tg.utils import format_user
from db.repositories import get_activity_last_30_days


async def data_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # admin check
    if not await is_allowed(update, context):
        await update.message.reply_text("❌ This command is for admins only.")
        return

    chat = update.effective_chat
    bot = context.bot

    rows = get_activity_last_30_days()


    if not rows:
        await update.message.reply_text("No history data for the last 30 days.")
        return

    # create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["date", "task", "user", "type"])

    for row in rows:
        task = row["task_name"]
        user_id = row["user_id"]
        date = datetime.fromisoformat(row["ts"]).strftime("%d.%m.%Y")

        try:
            member = await bot.get_chat_member(chat.id, user_id)
            user_name = format_user(member.user)
        except Exception:
            user_name = f"User({user_id})"

        writer.writerow([date, task, user_name])

    output.seek(0)

    filename = "history_last_30_days.csv"

    await update.message.reply_document(
        document=output.getvalue().encode("utf-8"),
        filename=filename,
        caption="📊 Duty history (last 30 days)"
    )
