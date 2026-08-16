-- TASKS
CREATE TABLE IF NOT EXISTS tasks (
    task_name TEXT PRIMARY KEY
);

-- TASK USERS (rotation order)
CREATE TABLE IF NOT EXISTS task_users (
    task_name TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    position INTEGER NOT NULL,
    active INTEGER DEFAULT 1,
    PRIMARY KEY (task_name, user_id)
);

-- TASK CREDITS
CREATE TABLE IF NOT EXISTS task_credits (
    task_name TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    credits INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (task_name, user_id)
);

-- TASK HISTORY
CREATE TABLE IF NOT EXISTS task_history (
    task_name TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    done_at TIMESTAMP NOT NULL
);

-- INTERNAL STATE (cursor)
CREATE TABLE IF NOT EXISTS task_state (
    task_name TEXT PRIMARY KEY,
    cursor_position INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS task_cooldowns (
    task_name TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    last_used_at TIMESTAMP NOT NULL,
    PRIMARY KEY (task_name, user_id)
);

CREATE TABLE IF NOT EXISTS task_volunteer_log (
    task_name TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    volunteered_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS task_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_name TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    action_type TEXT CHECK(action_type IN ('DONE', 'VOLUNTEER')) NOT NULL,
    message_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS groups (
    chat_id INTEGER PRIMARY KEY
);

-- One row per one-off data migration that cannot be expressed as CREATE IF NOT EXISTS.
CREATE TABLE IF NOT EXISTS schema_migrations (
    name TEXT PRIMARY KEY
);

-- Single-row key/value store. Holds the one chat this bot belongs to: every
-- duty, roster and history row is global, so serving a second group would mean
-- two apartments sharing one rotation and one /data export.
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_task_history_task_done
    ON task_history(task_name, done_at DESC);
CREATE INDEX IF NOT EXISTS idx_task_history_user_done
    ON task_history(user_id, done_at DESC);
CREATE INDEX IF NOT EXISTS idx_task_volunteer_log_task_user
    ON task_volunteer_log(task_name, user_id, volunteered_at DESC);
CREATE INDEX IF NOT EXISTS idx_task_actions_message
    ON task_actions(chat_id, message_id);
