#!/usr/bin/env python3
"""Turn the live SQLite database into SQL that D1 can swallow.

    python3 worker/scripts/export_sqlite_to_d1.py /path/to/bot.db > seed.sql
    cd worker && npx wrangler d1 execute apartmentmate --remote --file=../seed.sql

Safe to run against a running bot: it only reads. Copy the file off the EC2 box
first if you would rather not touch it at all.

Two conversions happen here so that the export works whether or not the fixed
Python bot has been deployed yet:

  * cursor_position. It used to be an INDEX into the list of active members, so
    removing anyone shifted everybody after them onto the wrong turn. D1 stores
    a task_users.position VALUE. If the source database has not been through
    that migration, the index is resolved to the member it currently points at.

  * timestamps. task_history was written with the sqlite3 datetime adapter
    ('2026-08-16 09:00:00+00:00') while task_volunteer_log used .isoformat()
    ('2026-08-16T09:00:00+00:00'), so the two could not be sorted against each
    other. Everything comes out as one ISO-8601 UTC format.
"""
import argparse
import sqlite3
import sys
from datetime import datetime, timezone


def quote(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def to_iso(raw) -> str:
    """One timestamp format, whichever of the two the row was written in."""
    if raw is None:
        return datetime.now(timezone.utc).isoformat()
    text = str(raw)
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        # Very old rows, or something hand-edited. Keep the day, lose the time.
        try:
            dt = datetime.strptime(text[:10], "%Y-%m-%d")
        except ValueError:
            return datetime.now(timezone.utc).isoformat()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def table_exists(conn, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def cursor_already_positions(conn) -> bool:
    if not table_exists(conn, "schema_migrations"):
        return False
    return conn.execute(
        "SELECT 1 FROM schema_migrations WHERE name='cursor_stores_position'"
    ).fetchone() is not None


def emit(line: str) -> None:
    print(line)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("db", help="path to the live bot.db")
    ap.add_argument("--apartment-chat-id", type=int, default=None,
                    help="chat id of the apartment group; taken from the source "
                         "database when it knows exactly one")
    args = ap.parse_args()

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    positions_done = cursor_already_positions(conn)
    print(f"-- exported from {args.db}", file=sys.stderr)
    print(f"-- cursor already stores positions: {positions_done}", file=sys.stderr)

    emit("-- ApartmentMate: SQLite -> D1")
    emit("-- Apply after `wrangler d1 migrations apply apartmentmate --remote`.")
    emit("")

    for table in ("tasks", "task_users", "task_credits", "task_state", "task_history",
                  "task_volunteer_log", "task_cooldowns", "settings", "user_names"):
        emit(f"DELETE FROM {table};")
    emit("")

    tasks = [r["task_name"] for r in conn.execute("SELECT task_name FROM tasks")]
    for name in tasks:
        emit(f"INSERT INTO tasks(task_name) VALUES ({quote(name.lower())});")
    emit("")

    for row in conn.execute("SELECT task_name, user_id, position, active FROM task_users"):
        emit(
            "INSERT INTO task_users(task_name, user_id, position, active) VALUES ("
            f"{quote(row['task_name'].lower())}, {row['user_id']}, {row['position']}, "
            f"{1 if row['active'] else 0});"
        )
    emit("")

    for row in conn.execute("SELECT task_name, user_id, credits FROM task_credits"):
        emit(
            "INSERT INTO task_credits(task_name, user_id, credits) VALUES ("
            f"{quote(row['task_name'].lower())}, {row['user_id']}, {row['credits']});"
        )
    emit("")

    for row in conn.execute("SELECT task_name, cursor_position FROM task_state"):
        task = row["task_name"]
        cursor = row["cursor_position"]
        if not positions_done:
            active = conn.execute(
                "SELECT position FROM task_users WHERE task_name = ? AND active = 1 "
                "ORDER BY position",
                (task,),
            ).fetchall()
            if active:
                cursor = active[cursor % len(active)]["position"]
            else:
                cursor = 0
        emit(
            "INSERT INTO task_state(task_name, cursor_position) VALUES ("
            f"{quote(task.lower())}, {cursor});"
        )
    emit("")

    for row in conn.execute("SELECT task_name, user_id, done_at FROM task_history "
                            "ORDER BY done_at"):
        emit(
            "INSERT INTO task_history(task_name, user_id, done_at) VALUES ("
            f"{quote(row['task_name'].lower())}, {row['user_id']}, "
            f"{quote(to_iso(row['done_at']))});"
        )
    emit("")

    if table_exists(conn, "task_volunteer_log"):
        for row in conn.execute("SELECT task_name, user_id, volunteered_at "
                                "FROM task_volunteer_log ORDER BY volunteered_at"):
            emit(
                "INSERT INTO task_volunteer_log(task_name, user_id, volunteered_at) VALUES ("
                f"{quote(row['task_name'].lower())}, {row['user_id']}, "
                f"{quote(to_iso(row['volunteered_at']))});"
            )
        emit("")

    if table_exists(conn, "task_cooldowns"):
        for row in conn.execute("SELECT task_name, user_id, last_used_at FROM task_cooldowns"):
            emit(
                "INSERT INTO task_cooldowns(task_name, user_id, last_used_at) VALUES ("
                f"{quote(row['task_name'].lower())}, {row['user_id']}, "
                f"{quote(to_iso(row['last_used_at']))});"
            )
        emit("")

    chat_id = args.apartment_chat_id
    if chat_id is None and table_exists(conn, "settings"):
        row = conn.execute(
            "SELECT value FROM settings WHERE key = 'apartment_chat_id'"
        ).fetchone()
        if row:
            chat_id = int(row["value"])
    if chat_id is None and table_exists(conn, "groups"):
        groups = conn.execute("SELECT chat_id FROM groups").fetchall()
        if len(groups) == 1:
            chat_id = groups[0]["chat_id"]
        elif len(groups) > 1:
            print(
                f"-- WARNING: {len(groups)} groups on record and no apartment set. "
                "Pass --apartment-chat-id, or run /claim after cutover.",
                file=sys.stderr,
            )

    if chat_id is not None:
        emit(
            "INSERT INTO settings(key, value) VALUES ('apartment_chat_id', "
            f"{quote(str(chat_id))});"
        )
        print(f"-- apartment chat id: {chat_id}", file=sys.stderr)
    else:
        emit("-- No apartment chat id found. Run /claim in the group after cutover.")

    # task_actions is deliberately not exported: it only exists so /cancel can
    # undo an action from the last few hours, and message ids do not survive a
    # change of bot anyway.

    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
