import json
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from db.connection import get_db

# Timestamps are stored in UTC and displayed in the apartment's timezone.
LOCAL_TZ = ZoneInfo(os.getenv("BOT_TIMEZONE", "Asia/Tashkent"))

# Every timestamp in this database is written by this one function so that the
# two tables that used to disagree ('2026-08-16 12:00:00+00:00' from the
# deprecated sqlite3 datetime adapter, versus '2026-08-16T12:00:00+00:00' from
# .isoformat()) now sort and compare against each other correctly.
def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_ts(value: str) -> datetime:
    """Read a timestamp back, tolerating rows written before the formats agreed.

    Returned in the apartment's own timezone: everything is stored in UTC, and
    a duty done at 02:00 in Tashkent used to be displayed on the previous day.
    """
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(LOCAL_TZ)

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
            conn.execute(
                """
                INSERT OR IGNORE INTO task_credits(task_name, user_id, credits)
                VALUES (?, ?, 0)
                """,
                (task_name, user_id)
            )
            return "reactivated"

        return "exists"

def deactivate_user(task_name: str, user_id: int) -> bool:
    """Take a user out of the rotation. Returns False if they were not in it."""
    with get_db() as conn:
        cur = conn.execute(
            """
            UPDATE task_users
            SET active = 0
            WHERE task_name = ? AND user_id = ? AND active = 1
            """,
            (task_name, user_id)
        )
        return cur.rowcount > 0

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

def is_task_member(task_name: str, user_id: int) -> bool:
    with get_db() as conn:
        cur = conn.execute(
            """
            SELECT 1 FROM task_users
            WHERE task_name = ? AND user_id = ? AND active = 1
            """,
            (task_name, user_id)
        )
        return cur.fetchone() is not None

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

        return datetime.now(timezone.utc) - parse_ts(row["last_used_at"]) < timedelta(hours=hours)

def update_cooldown(task_name: str, user_id: int):
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO task_cooldowns(task_name, user_id, last_used_at)
            VALUES (?, ?, ?)
            ON CONFLICT(task_name, user_id)
            DO UPDATE SET last_used_at = excluded.last_used_at
            """,
            (task_name, user_id, utcnow_iso())
        )

def clear_cooldown(task_name: str, user_id: int):
    with get_db() as conn:
        conn.execute(
            "DELETE FROM task_cooldowns WHERE task_name = ? AND user_id = ?",
            (task_name, user_id)
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

def add_credit(task_name: str, user_id: int) -> bool:
    """Grant one skip credit.

    Returns False when the user has no credit row at all, which is what used to
    make the bot answer '+1 skip credit' to somebody who was not in the rotation.
    """
    with get_db() as conn:
        cur = conn.execute(
            """
            UPDATE task_credits
            SET credits = credits + 1
            WHERE task_name = ? AND user_id = ?
            """,
            (task_name, user_id)
        )
        return cur.rowcount > 0

# ---------- CURSOR ----------
# cursor_position holds the POSITION VALUE (task_users.position) of the next
# responsible user, not an index into the list of active users. Position values
# are stable per user, so deactivating somebody no longer shifts anyone's turn.

def get_cursor(task_name: str) -> int:
    with get_db() as conn:
        cur = conn.execute(
            "SELECT cursor_position FROM task_state WHERE task_name = ?",
            (task_name,)
        )
        row = cur.fetchone()
        return row["cursor_position"] if row else 0

def set_cursor(task_name: str, position: int):
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO task_state(task_name, cursor_position)
            VALUES (?, ?)
            ON CONFLICT(task_name) DO UPDATE SET cursor_position = excluded.cursor_position
            """,
            (task_name, position)
        )

# ---------- HISTORY ----------

def add_history(task_name: str, user_id: int) -> int:
    """Returns the rowid so /cancel can undo THIS entry rather than the newest one."""
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO task_history(task_name, user_id, done_at) VALUES (?, ?, ?)",
            (task_name, user_id, utcnow_iso())
        )
        return cur.lastrowid

def cleanup_history(days: int = 30):
    """Prune everything that is presented as a rolling 30-day window.

    task_volunteer_log and task_actions used to be pruned by nothing at all and
    grew forever, while /data claims to show 'the last 30 days'.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with get_db() as conn:
        conn.execute("DELETE FROM task_history WHERE done_at < ?", (cutoff,))
        conn.execute("DELETE FROM task_volunteer_log WHERE volunteered_at < ?", (cutoff,))
        conn.execute("DELETE FROM task_actions WHERE created_at < ?", (cutoff,))

def add_volunteer_log(task_name: str, user_id: int) -> int:
    """Returns the rowid so /cancel can undo THIS entry rather than the newest one."""
    with get_db() as conn:
        cur = conn.execute(
            """
            INSERT INTO task_volunteer_log(task_name, user_id, volunteered_at)
            VALUES (?, ?, ?)
            """,
            (task_name, user_id, utcnow_iso())
        )
        return cur.lastrowid

def get_activity_last_30_days():
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    with get_db() as conn:
        cur = conn.execute(
            """
            SELECT task_name, user_id, done_at AS ts, 'COMPLETED' AS type
            FROM task_history
            WHERE done_at >= ?

            UNION ALL

            SELECT task_name, user_id, volunteered_at AS ts, 'VOLUNTEER' AS type
            FROM task_volunteer_log
            WHERE volunteered_at >= ?

            ORDER BY ts DESC
            """,
            (cutoff, cutoff)
        )
        return cur.fetchall()

# ---------- ACTIONS ----------

def log_action(task_name, user_id, action_type, chat_id, message_id,
               prev_cursor=None, consumed_credits=None, target_rowid=None):
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO task_actions(
                task_name, user_id, action_type, chat_id, message_id, created_at,
                prev_cursor, consumed_credits, target_rowid
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (task_name, user_id, action_type, chat_id, message_id, utcnow_iso(),
             prev_cursor, json.dumps(consumed_credits or []), target_rowid)
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

def refund_credits(task_name: str, user_ids):
    """Give back the skip credits a cancelled turn consumed."""
    with get_db() as conn:
        for user_id in user_ids:
            conn.execute(
                """
                UPDATE task_credits
                SET credits = credits + 1
                WHERE task_name = ? AND user_id = ?
                """,
                (task_name, user_id)
            )

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

def remove_volunteer_log(task_name: str, user_id: int, rowid=None):
    """Undo one volunteer entry — the exact one when the action recorded its
    rowid, otherwise the most recent (for actions logged before that existed)."""
    with get_db() as conn:
        if rowid is not None:
            conn.execute("DELETE FROM task_volunteer_log WHERE rowid = ?", (rowid,))
            return
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

def remove_last_history(task_name: str, user_id: int, rowid=None):
    """Undo one completion — the exact one when the action recorded its rowid.

    Replying /cancel to an OLD confirmation message used to delete the user's
    most recent completion instead of the one they were pointing at.
    """
    with get_db() as conn:
        if rowid is not None:
            conn.execute("DELETE FROM task_history WHERE rowid = ?", (rowid,))
            return
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

def remove_group(chat_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM groups WHERE chat_id = ?", (chat_id,))

def get_all_groups():
    with get_db() as conn:
        cur = conn.execute("SELECT chat_id FROM groups")
        return [row["chat_id"] for row in cur.fetchall()]
