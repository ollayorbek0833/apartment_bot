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


TASK_NAME_TABLES = (
    "tasks", "task_users", "task_credits", "task_state",
    "task_cooldowns", "task_history", "task_volunteer_log", "task_actions",
)


def _migrate_lowercase_task_names(conn):
    """Duty names are matched lowercase, because that is how a command arrives.

    A duty created as 'Kitchen' before names were validated could never be run:
    /Kitchen normalises to 'kitchen' and finds nothing. Fold the old names down,
    unless doing so would collide with a duty that already owns the lower name.
    """
    rows = conn.execute("SELECT task_name FROM tasks").fetchall()
    existing = {row["task_name"] for row in rows}
    for name in sorted(existing):
        lower = name.lower()
        if lower == name:
            continue
        if lower in existing:
            log.warning(
                "task %r cannot be folded to %r: both exist, leaving it alone", name, lower
            )
            continue
        for table in TASK_NAME_TABLES:
            conn.execute(
                f"UPDATE {table} SET task_name = ? WHERE task_name = ?", (lower, name)
            )
        existing.discard(name)
        existing.add(lower)
        log.info("renamed task %r to %r so /%s reaches it", name, lower, lower)


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

        for name, fn in (
            ("lowercase_task_names", _migrate_lowercase_task_names),
            ("cursor_stores_position", _migrate_cursor_to_position),
        ):
            applied = conn.execute(
                "SELECT 1 FROM schema_migrations WHERE name = ?", (name,)
            ).fetchone()
            if not applied:
                fn(conn)
                conn.execute("INSERT INTO schema_migrations(name) VALUES (?)", (name,))
