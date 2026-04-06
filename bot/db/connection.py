import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path("bot.db")
MIGRATIONS_PATH = Path(__file__).parent / "migrations.sql"

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    with get_db() as conn:
        sql = MIGRATIONS_PATH.read_text()
        conn.executescript(sql)
