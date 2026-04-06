from datetime import datetime, timedelta, timezone
from db.connection import get_db

# ---------- TASKS ----------

def create_task(task_name: str):
    with get_db() as conn:
        conn.execute("INSERT INTO tasks(task_name) VALUES (?)", (task_name,))
        conn.execute(
            "INSERT INTO task_state(task_name, cursor_position) VALUES (?, 0)",
            (task_name,)
        )

def get_all_tasks():
    with get_db() as conn:
        cur = conn.execute("SELECT task_name FROM tasks ORDER BY task_name")
        return [row["task_name"] for row in cur.fetchall()]

def task_exists(task_name: str) -> bool:
    with get_db() as conn:
        cur = conn.execute(
            "SELECT 1 FROM tasks WHERE task_name = ?", (task_name,)
        )
        return cur.fetchone() is not None

# ---------- USERS ----------

def add_user_to_task(task_name: str, user_id: int):
    with get_db() as conn:
        cur = conn.execute(
            """
            SELECT active FROM task_users
            WHERE task_name = ? AND user_id = ?
            """,
            (task_name, user_id)
        )
        row = cur.fetchone()

        if row is None:
            cur = conn.execute(
                """
                SELECT COALESCE(MAX(position), -1) + 1
                FROM task_users
                WHERE task_name = ?
                """,
                (task_name,)
            )
            position = cur.fetchone()[0]

            conn.execute(
                """
                INSERT INTO task_users(task_name, user_id, position, active)
                VALUES (?, ?, ?, 1)
                """,
                (task_name, user_id, position)
            )

            conn.execute(
                """
                INSERT OR IGNORE INTO task_credits(task_name, user_id, credits)
                VALUES (?, ?, 0)
                """,
                (task_name, user_id)
            )

            return "added"

        if row["active"] == 0:
            conn.execute(
                """
                UPDATE task_users
                SET active = 1
                WHERE task_name = ? AND user_id = ?
                """,
                (task_name, user_id)
            )
            return "reactivated"

        return "exists"

def get_task_users(task_name: str):
    with get_db() as conn:
        cur = conn.execute(
            """
            SELECT user_id, position
            FROM task_users
            WHERE task_name = ? AND active = 1
            ORDER BY position
            """,
            (task_name,)
        )
        return cur.fetchall()

def is_in_cooldown(task_name: str, user_id: int, hours: int = 2) -> bool:
    with get_db() as conn:
        cur = conn.execute(
            """
            SELECT last_used_at
            FROM task_cooldowns
            WHERE task_name = ? AND user_id = ?
            """,
            (task_name, user_id)
        )
        row = cur.fetchone()
        if not row:
            return False

        last_used = datetime.fromisoformat(row["last_used_at"])
        if last_used.tzinfo is None:
            last_used = last_used.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - last_used < timedelta(hours=hours)

def update_cooldown(task_name: str, user_id: int):
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO task_cooldowns(task_name, user_id, last_used_at)
            VALUES (?, ?, ?)
            ON CONFLICT(task_name, user_id)
            DO UPDATE SET last_used_at = excluded.last_used_at
            """,
            (task_name, user_id, datetime.now(timezone.utc).isoformat())
        )

# ---------- CREDITS ----------

def get_credit(task_name: str, user_id: int) -> int:
    with get_db() as conn:
        cur = conn.execute(
            "SELECT credits FROM task_credits WHERE task_name = ? AND user_id = ?",
            (task_name, user_id)
        )
        row = cur.fetchone()
        return row["credits"] if row else 0

def consume_credit(task_name: str, user_id: int):
    with get_db() as conn:
        conn.execute(
            """
            UPDATE task_credits
            SET credits = credits - 1
            WHERE task_name = ? AND user_id = ? AND credits > 0
            """,
            (task_name, user_id)
        )

def add_credit(task_name: str, user_id: int):
    with get_db() as conn:
        conn.execute(
            """
            UPDATE task_credits
            SET credits = credits + 1
            WHERE task_name = ? AND user_id = ?
            """,
            (task_name, user_id)
        )

# ---------- CURSOR ----------

def get_cursor(task_name: str) -> int:
    with get_db() as conn:
        cur = conn.execute(
            "SELECT cursor_position FROM task_state WHERE task_name = ?",
            (task_name,)
        )
        return cur.fetchone()["cursor_position"]

def set_cursor(task_name: str, position: int):
    with get_db() as conn:
        conn.execute(
            "UPDATE task_state SET cursor_position = ? WHERE task_name = ?",
            (position, task_name)
        )

# ---------- HISTORY ----------

def add_history(task_name: str, user_id: int):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO task_history(task_name, user_id, done_at) VALUES (?, ?, ?)",
            (task_name, user_id, datetime.now(timezone.utc))
        )

def cleanup_history(days: int = 30):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    with get_db() as conn:
        conn.execute(
            "DELETE FROM task_history WHERE done_at < ?",
            (cutoff,)
        )

def add_volunteer_log(task_name: str, user_id: int):
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO task_volunteer_log(task_name, user_id, volunteered_at)
            VALUES (?, ?, ?)
            """,
            (task_name, user_id, datetime.now(timezone.utc).isoformat())
        )

def get_activity_last_30_days():
    with get_db() as conn:
        cur = conn.execute(
            """
            SELECT task_name, user_id, done_at AS ts, 'COMPLETED' AS type
            FROM task_history
            WHERE done_at >= datetime('now', '-30 days')

            UNION ALL

            SELECT task_name, user_id, volunteered_at AS ts, 'VOLUNTEER' AS type
            FROM task_volunteer_log
            WHERE volunteered_at >= datetime('now', '-30 days')

            ORDER BY ts DESC
            """
        )
        return cur.fetchall()

# ---------- ACTIONS ----------

def log_action(task_name, user_id, action_type, chat_id, message_id):
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO task_actions(task_name, user_id, action_type, chat_id, message_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (task_name, user_id, action_type, chat_id, message_id, datetime.now(timezone.utc).isoformat())
        )

def get_action_by_message(chat_id, message_id):
    with get_db() as conn:
        cur = conn.execute(
            """
            SELECT * FROM task_actions
            WHERE chat_id = ? AND message_id = ?
            """,
            (chat_id, message_id)
        )
        return cur.fetchone()

def delete_action(action_id):
    with get_db() as conn:
        conn.execute(
            "DELETE FROM task_actions WHERE id = ?",
            (action_id,)
        )

# ---------- UNDO HELPERS ----------

def remove_credit(task_name: str, user_id: int):
    with get_db() as conn:
        conn.execute(
            """
            UPDATE task_credits
            SET credits = CASE
                WHEN credits > 0 THEN credits - 1
                ELSE 0
            END
            WHERE task_name = ? AND user_id = ?
            """,
            (task_name, user_id)
        )

def remove_volunteer_log(task_name: str, user_id: int):
    with get_db() as conn:
        conn.execute(
            """
            DELETE FROM task_volunteer_log
            WHERE rowid = (
                SELECT rowid
                FROM task_volunteer_log
                WHERE task_name = ? AND user_id = ?
                ORDER BY volunteered_at DESC
                LIMIT 1
            )
            """,
            (task_name, user_id)
        )

def remove_last_history(task_name: str, user_id: int):
    with get_db() as conn:
        conn.execute(
            """
            DELETE FROM task_history
            WHERE rowid = (
                SELECT rowid
                FROM task_history
                WHERE task_name = ? AND user_id = ?
                ORDER BY done_at DESC
                LIMIT 1
            )
            """,
            (task_name, user_id)
        )

# ---------- GROUPS ----------

def save_group(chat_id: int):
    with get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO groups(chat_id) VALUES (?)",
            (chat_id,)
        )

def get_all_groups():
    with get_db() as conn:
        cur = conn.execute("SELECT chat_id FROM groups")
        return [row["chat_id"] for row in cur.fetchall()]
