from db.repositories import (
    get_task_users,
    get_credit,
    consume_credit,
    get_cursor,
    set_cursor
)

def get_next_responsible(task_name: str):
    users = get_task_users(task_name)
    if not users:
        return None

    cursor = get_cursor(task_name)
    size = len(users)
    if size == 0:
        return None

    checked = 0
    index = cursor

    while checked < size * 2:  # safety
        user = users[index % size]
        user_id = user["user_id"]

        credits = get_credit(task_name, user_id)
        if credits > 0:
            consume_credit(task_name, user_id)
            index += 1
            checked += 1
            continue

        # FOUND responsible
        next_cursor = (index + 1) % size
        set_cursor(task_name, next_cursor)
        return user_id

    return None
