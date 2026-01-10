
import aiosqlite
from datetime import date

DB_NAME = "bot.db"


async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            task_name TEXT PRIMARY KEY
        )
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS task_users (
            task_name TEXT,
            user_id INTEGER,
            position INTEGER
        )
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS daily_done (
            task_name TEXT,
            user_id INTEGER,
            done_date TEXT
        )
        """)
        await db.commit()


# ---------- TASK USERS ----------
async def add_user_to_task(task, user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        cur = await db.execute(
            "SELECT MAX(position) FROM task_users WHERE task_name=?",
            (task,)
        )
        max_pos = (await cur.fetchone())[0]
        pos = 1 if max_pos is None else max_pos + 1

        await db.execute(
            "INSERT INTO task_users VALUES (?,?,?)",
            (task, user_id, pos)
        )
        await db.commit()


async def get_task_queue(task):
    async with aiosqlite.connect(DB_NAME) as db:
        cur = await db.execute(
            "SELECT user_id FROM task_users WHERE task_name=? ORDER BY position",
            (task,)
        )
        return [row[0] for row in await cur.fetchall()]


async def rotate_queue(task, user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "UPDATE task_users SET position = position - 1 WHERE task_name=?",
            (task,)
        )
        cur = await db.execute(
            "SELECT MAX(position) FROM task_users WHERE task_name=?",
            (task,)
        )
        max_pos = (await cur.fetchone())[0]
        await db.execute(
            "UPDATE task_users SET position=? WHERE task_name=? AND user_id=?",
            (max_pos + 1, task, user_id)
        )
        await db.commit()


# ---------- DAILY DONE ----------
async def mark_done(task, user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO daily_done VALUES (?,?,?)",
            (task, user_id, str(date.today()))
        )
        await db.commit()


async def unmark_done(task, user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "DELETE FROM daily_done WHERE task_name=? AND user_id=? AND done_date=?",
            (task, user_id, str(date.today()))
        )
        await db.commit()


async def done_today(task):
    async with aiosqlite.connect(DB_NAME) as db:
        cur = await db.execute(
            "SELECT user_id FROM daily_done WHERE task_name=? AND done_date=?",
            (task, str(date.today()))
        )
        return {row[0] for row in await cur.fetchall()}


async def clear_daily_done():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM daily_done")
        await db.commit()
