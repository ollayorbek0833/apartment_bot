from datetime import datetime, timedelta
from db.connection import get_connection

# ---------- TASKS ----------

def create_task(task_name: str):
    conn = get_connection()
    with conn:
        conn.execute("INSERT INTO tasks(task_name) VALUES (?)", (task_name,))
        conn.execute(
            "INSERT INTO task_state(task_name, cursor_position) VALUES (?, 0)",
            (task_name,)
        )

def task_exists(task_name: str) -> bool:
    conn = get_connection()
    cur = conn.execute(
        "SELECT 1 FROM tasks WHERE task_name = ?", (task_name,)
    )
    return cur.fetchone() is not None

# ---------- USERS ----------

def add_user_to_task(task_name: str, user_id: int):
    conn = get_connection()

    # check if user already exists in task
    cur = conn.execute(
        """
        SELECT active FROM task_users
        WHERE task_name = ? AND user_id = ?
        """,
        (task_name, user_id)
    )
    row = cur.fetchone()

    with conn:
        if row is None:
            # user not present at all → insert new
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
            # user exists but inactive → reactivate
            conn.execute(
                """
                UPDATE task_users
                SET active = 1
                WHERE task_name = ? AND user_id = ?
                """,
                (task_name, user_id)
            )
            return "reactivated"

        # user already active
        return "exists"


def get_task_users(task_name: str):
    conn = get_connection()
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
    conn = get_connection()
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
    return datetime.utcnow() - last_used < timedelta(hours=hours)

def update_cooldown(task_name: str, user_id: int):
    conn = get_connection()
    with conn:
        conn.execute(
            """
            INSERT INTO task_cooldowns(task_name, user_id, last_used_at)
            VALUES (?, ?, ?)
            ON CONFLICT(task_name, user_id)
            DO UPDATE SET last_used_at = excluded.last_used_at
            """,
            (task_name, user_id, datetime.utcnow().isoformat())
        )

# ---------- CREDITS ----------

def get_credit(task_name: str, user_id: int) -> int:
    conn = get_connection()
    cur = conn.execute(
        "SELECT credits FROM task_credits WHERE task_name = ? AND user_id = ?",
        (task_name, user_id)
    )
    row = cur.fetchone()
    return row["credits"] if row else 0

def consume_credit(task_name: str, user_id: int):
    conn = get_connection()
    with conn:
        conn.execute(
            """
            UPDATE task_credits
            SET credits = credits - 1
            WHERE task_name = ? AND user_id = ? AND credits > 0
            """,
            (task_name, user_id)
        )

def add_credit(task_name: str, user_id: int):
    conn = get_connection()
    with conn:
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
    conn = get_connection()
    cur = conn.execute(
        "SELECT cursor_position FROM task_state WHERE task_name = ?",
        (task_name,)
    )
    return cur.fetchone()["cursor_position"]

def set_cursor(task_name: str, position: int):
    conn = get_connection()
    with conn:
        conn.execute(
            "UPDATE task_state SET cursor_position = ? WHERE task_name = ?",
            (position, task_name)
        )

# ---------- HISTORY ----------

def add_history(task_name: str, user_id: int):
    conn = get_connection()
    with conn:
        conn.execute(
            "INSERT INTO task_history(task_name, user_id, done_at) VALUES (?, ?, ?)",
            (task_name, user_id, datetime.utcnow())
        )

def cleanup_history(days: int = 30):
    conn = get_connection()
    cutoff = datetime.utcnow() - timedelta(days=days)
    with conn:
        conn.execute(
            "DELETE FROM task_history WHERE done_at < ?",
            (cutoff,)
        )
