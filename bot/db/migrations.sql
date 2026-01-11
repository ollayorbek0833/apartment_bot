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
