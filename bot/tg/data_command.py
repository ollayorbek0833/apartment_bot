import csv
import io
from telegram import Update
from telegram.ext import ContextTypes

from db.repositories import get_activity_last_30_days, parse_ts
from tg.permissions import is_allowed
from tg.utils import format_user

# Excel treats a leading =, +, - or @ in a cell as a formula. Telegram display
# names are user-controlled, so they get a leading apostrophe.
FORMULA_PREFIXES = ("=", "+", "-", "@")


def _safe(value: str) -> str:
    text = str(value)
    return "'" + text if text.startswith(FORMULA_PREFIXES) else text


async def data_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # is_allowed already replies with the reason; do not answer a second time.
    if not await is_allowed(update, context):
        return

    chat = update.effective_chat
    bot = context.bot

    rows = get_activity_last_30_days()

    if not rows:
        await update.message.reply_text("No history data for the last 30 days.")
        return

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["date", "time", "task", "user", "type"])

    names = {}
    for row in rows:
        user_id = row["user_id"]
        if user_id not in names:
            try:
                member = await bot.get_chat_member(chat.id, user_id)
                names[user_id] = format_user(member.user)
            except Exception:
                names[user_id] = f"User({user_id})"

        ts = parse_ts(row["ts"])
        # Every row now carries its type, so a completion is distinguishable
        # from a volunteer shift. The header used to promise four columns while
        # each row wrote three, which silently shifted every field in Excel.
        writer.writerow([
            ts.strftime("%d.%m.%Y"),
            ts.strftime("%H:%M"),
            _safe(row["task_name"]),
            _safe(names[user_id]),
            row["type"],
        ])

    filename = "history_last_30_days.csv"

    await update.message.reply_document(
        # utf-8-sig: without the BOM, Excel on Windows mangles non-ASCII names.
        document=output.getvalue().encode("utf-8-sig"),
        filename=filename,
        caption="📊 Duty history (last 30 days)"
    )
