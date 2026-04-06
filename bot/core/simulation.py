from copy import deepcopy
from db.repositories import get_task_users, get_cursor, get_credit

def simulate_next(task_name: str, steps: int):
    users = get_task_users(task_name)
    if not users:
        return []

    credits = {
        u["user_id"]: get_credit(task_name, u["user_id"])
        for u in users
    }

    cursor = get_cursor(task_name)
    size = len(users)
    result = []

    index = cursor
    safety = 0

    while len(result) < steps and safety < size * steps * 2:
        user = users[index % size]
        uid = user["user_id"]

        if credits[uid] > 0:
            credits[uid] -= 1
        else:
            result.append(uid)

        index += 1
        safety += 1

    return result
