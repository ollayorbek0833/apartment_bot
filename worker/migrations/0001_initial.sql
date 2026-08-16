-- ApartmentMate schema on D1.
--
-- Carried over from the SQLite schema the Python bot uses, with the fixes that
-- audit produced already folded in:
--   * cursor_position holds a task_users.position VALUE, not a list index, so
--     removing somebody never shifts anyone else's turn;
--   * task_actions records what a turn changed (previous cursor, credits spent,
--     the exact row written) so /cancel can put all of it back;
--   * every timestamp is an ISO-8601 UTC string written by one helper, so the
--     two tables the activity export unions can actually be sorted together.

CREATE TABLE IF NOT EXISTS tasks (
    task_name TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS task_users (
    task_name TEXT NOT NULL,
    user_id   INTEGER NOT NULL,
    position  INTEGER NOT NULL,
    active    INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (task_name, user_id)
);

CREATE TABLE IF NOT EXISTS task_credits (
    task_name TEXT NOT NULL,
    user_id   INTEGER NOT NULL,
    credits   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (task_name, user_id)
);

CREATE TABLE IF NOT EXISTS task_state (
    task_name       TEXT PRIMARY KEY,
    cursor_position INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS task_history (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    task_name TEXT NOT NULL,
    user_id   INTEGER NOT NULL,
    done_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS task_volunteer_log (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    task_name      TEXT NOT NULL,
    user_id        INTEGER NOT NULL,
    volunteered_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS task_cooldowns (
    task_name    TEXT NOT NULL,
    user_id      INTEGER NOT NULL,
    last_used_at TEXT NOT NULL,
    PRIMARY KEY (task_name, user_id)
);

CREATE TABLE IF NOT EXISTS task_actions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    task_name        TEXT NOT NULL,
    user_id          INTEGER NOT NULL,
    action_type      TEXT NOT NULL CHECK (action_type IN ('DONE', 'VOLUNTEER')),
    chat_id          INTEGER NOT NULL,
    message_id       INTEGER NOT NULL,
    created_at       TEXT NOT NULL,
    prev_cursor      INTEGER,
    consumed_credits TEXT,
    target_rowid     INTEGER
);

-- The one group this bot serves, plus anything else that is a single value.
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Cached display names, so the daily announcement does not call getChatMember
-- once per duty per morning.
CREATE TABLE IF NOT EXISTS user_names (
    user_id    INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_task_history_task_done
    ON task_history(task_name, done_at DESC);
CREATE INDEX IF NOT EXISTS idx_task_history_user_done
    ON task_history(user_id, done_at DESC);
CREATE INDEX IF NOT EXISTS idx_task_volunteer_task_user
    ON task_volunteer_log(task_name, user_id, volunteered_at DESC);
CREATE INDEX IF NOT EXISTS idx_task_actions_message
    ON task_actions(chat_id, message_id);
