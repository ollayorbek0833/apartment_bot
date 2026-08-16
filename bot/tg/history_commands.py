from telegram import Update
from telegram.ext import ContextTypes

from db.connection import get_db
from db.repositories import parse_ts, task_exists
from tg.apartment import in_apartment
from tg.utils import format_user


async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat or not update.message:
        return
    if not await in_apartment(update):
        return

    # -------- /history task_name --------
    if context.args:
        task_name = context.args[0].lower()

        if not task_exists(task_name):
            await update.message.reply_text(
                f"❌ There is no task called '{task_name}'. /tasks lists them all."
            )
            return

        with get_db() as conn:
            cur = conn.execute(
                """
                SELECT user_id, done_at
                FROM task_history
                WHERE task_name = ?
                ORDER BY done_at DESC
                LIMIT 3
                """,
                (task_name,)
            )
            rows = cur.fetchall()

        if not rows:
            await update.message.reply_text("No history for this task.")
            return

        lines = [f"🕒 Last {task_name} duties:"]

        for row in rows:
            user_id = row["user_id"]
            date_str = parse_ts(row["done_at"]).strftime("%d.%m")

            try:
                member = await context.bot.get_chat_member(chat.id, user_id)
                name = format_user(member.user)
            except Exception:
                name = f"User({user_id})"

            lines.append(f"{date_str} – {name}")

        await update.message.reply_text("\n".join(lines))
        return

    # -------- /history (personal history) --------
    with get_db() as conn:
        cur = conn.execute(
            """
            SELECT task_name, done_at
            FROM task_history
            WHERE user_id = ?
            ORDER BY done_at DESC
            LIMIT 10
            """,
            (user.id,)
        )
        rows = cur.fetchall()

    if not rows:
        await update.message.reply_text("No history found.")
        return

    lines = ["🕒 Your last duties:"]

    for row in rows:
        date_str = parse_ts(row["done_at"]).strftime("%d.%m")
        lines.append(f"{date_str} – {row['task_name']}")

    await update.message.reply_text("\n".join(lines))
