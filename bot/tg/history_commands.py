from telegram import Update
from telegram.ext import ContextTypes
from db.connection import get_connection


async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return

    conn = get_connection()

    if context.args:
        task = context.args[0]
        cur = conn.execute(
            """
            SELECT done_at
            FROM task_history
            WHERE user_id = ? AND task_name = ?
            ORDER BY done_at DESC
            LIMIT 3
            """,
            (user.id, task)
        )

        rows = cur.fetchall()
        if not rows:
            await update.message.reply_text("No history for this task.")
            return

        text = f"🕒 Last {task} duties:\n"
        text += "\n".join(f"- {r['done_at']}" for r in rows)
        await update.message.reply_text(text)
        return

    # global history
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

    text = "🕒 Your last duties:\n"
    text += "\n".join(f"- {r['task_name']} @ {r['done_at']}" for r in rows)
    await update.message.reply_text(text)
