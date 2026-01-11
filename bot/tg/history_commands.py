from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes

from db.connection import get_connection
from tg.utils import format_user


async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return

    conn = get_connection()

    # -------- /history task_name --------
    if context.args:
        task_name = context.args[0]

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
            done_at = datetime.fromisoformat(row["done_at"])

            date_str = done_at.strftime("%d.%m")

            try:
                member = await context.bot.get_chat_member(chat.id, user_id)
                name = format_user(member.user)
            except Exception:
                name = f"User({user_id})"

            lines.append(f"{date_str} – {name}")

        await update.message.reply_text("\n".join(lines))
        return

    # -------- /history (personal history) --------
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
        task = row["task_name"]
        done_at = datetime.fromisoformat(row["done_at"])
        date_str = done_at.strftime("%d.%m")

        lines.append(f"{date_str} – {task}")

    await update.message.reply_text("\n".join(lines))
