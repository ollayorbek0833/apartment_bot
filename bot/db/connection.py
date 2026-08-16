import logging
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

log = logging.getLogger(__name__)

# "bot.db" is resolved against the process working directory. Started from the
# wrong directory, the bot used to create a brand new empty database and report
# that nobody has any history — set BOT_DB_PATH in the systemd unit to pin it.
DB_PATH = Path(os.getenv("BOT_DB_PATH", "bot.db")).expanduser().resolve()
MIGRATIONS_PATH = Path(__file__).parent / "migrations.sql"

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _column_exists(conn, table: str, column: str) -> bool:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(row["name"] == column for row in cur.fetchall())


def _migrate_cursor_to_position(conn):
    """cursor_position used to be an INDEX into the list of active users.

    That made it wrong the moment anybody was removed from a rotation: the list
    shrinks, every index after the removed user shifts by one, and the cursor
    silently points at the wrong person. It now stores the POSITION VALUE of the
    next responsible user, which is stable per user, so removals no longer move
    anyone else's turn. Existing databases are converted once.
    """
    cur = conn.execute("SELECT task_name, cursor_position FROM task_state")
    for state in cur.fetchall():
        task_name = state["task_name"]
        users = conn.execute(
            """
            SELECT position FROM task_users
            WHERE task_name = ? AND active = 1
            ORDER BY position
            """,
            (task_name,),
        ).fetchall()
        if not users:
            continue
        index = state["cursor_position"] % len(users)
        conn.execute(
            "UPDATE task_state SET cursor_position = ? WHERE task_name = ?",
            (users[index]["position"], task_name),
        )


def init_db():
    existed = DB_PATH.exists()
    log.info("using database %s (%s)", DB_PATH, "existing" if existed else "NEW, empty")
    with get_db() as conn:
        sql = MIGRATIONS_PATH.read_text()
        conn.executescript(sql)

        # ALTER TABLE ... ADD COLUMN has no IF NOT EXISTS in SQLite, so these
        # live here rather than in migrations.sql.
        if not _column_exists(conn, "task_actions", "prev_cursor"):
            conn.execute("ALTER TABLE task_actions ADD COLUMN prev_cursor INTEGER")
        if not _column_exists(conn, "task_actions", "consumed_credits"):
            conn.execute("ALTER TABLE task_actions ADD COLUMN consumed_credits TEXT")
        if not _column_exists(conn, "task_actions", "target_rowid"):
            conn.execute("ALTER TABLE task_actions ADD COLUMN target_rowid INTEGER")

        applied = conn.execute(
            "SELECT 1 FROM schema_migrations WHERE name = 'cursor_stores_position'"
        ).fetchone()
        if not applied:
            _migrate_cursor_to_position(conn)
            conn.execute(
                "INSERT INTO schema_migrations(name) VALUES ('cursor_stores_position')"
            )
