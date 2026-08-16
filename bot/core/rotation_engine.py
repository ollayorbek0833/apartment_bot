from db.repositories import (
    get_task_users,
    get_credit,
    consume_credit,
    get_cursor,
    set_cursor
)


def start_index(users, cursor_position: int) -> int:
    """Where in the active list does the rotation resume?

    cursor_position is a task_users.position VALUE, not an index into this list,
    so it survives a user being removed. If the user it pointed at is gone, the
    turn passes to the next active user after them, wrapping to the front.
    """
    for i, user in enumerate(users):
        if user["position"] >= cursor_position:
            return i
    return 0


def next_turn(users, cursor_position: int, credits: dict):
    """The single definition of whose turn it is.

    Both the live engine and the read-only simulation call this, so the two can
    never disagree. Returns (index_in_users, user_ids_whose_credit_was_skipped)
    and decrements those credits in the ``credits`` dict it was handed.
    """
    size = len(users)
    index = start_index(users, cursor_position)

    if all(credits.get(u["user_id"], 0) > 0 for u in users):
        # Nobody can be skipped onto anybody else. Burning a credit from every
        # single person and then still making one of them do it is not a skip,
        # it is a tax — so the turn simply stands and no credit is spent.
        return index, []

    skipped = []
    for _ in range(size):
        user_id = users[index % size]["user_id"]
        if credits.get(user_id, 0) > 0:
            credits[user_id] -= 1
            skipped.append(user_id)
            index += 1
            continue
        break

    return index % size, skipped


def get_next_responsible(task_name: str):
    """Advance the rotation for real: consume skip credits, move the cursor.

    Returns (user_id, prev_cursor, consumed_credit_user_ids) so that /cancel can
    put every one of those changes back.
    """
    users = get_task_users(task_name)
    if not users:
        return None, None, []

    prev_cursor = get_cursor(task_name)
    credits = {u["user_id"]: get_credit(task_name, u["user_id"]) for u in users}

    index, skipped = next_turn(users, prev_cursor, credits)

    for user_id in skipped:
        consume_credit(task_name, user_id)

    next_index = (index + 1) % len(users)
    set_cursor(task_name, users[next_index]["position"])

    return users[index]["user_id"], prev_cursor, skipped
