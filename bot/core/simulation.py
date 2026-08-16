from core.rotation_engine import next_turn
from db.repositories import get_task_users, get_cursor, get_credit


def simulate_next(task_name: str, steps: int):
    """Read-only: who takes the next ``steps`` turns, changing nothing.

    Runs the exact same next_turn() the live engine runs, against a throwaway
    copy of the credit balances.
    """
    users = get_task_users(task_name)
    if not users:
        return []

    credits = {
        u["user_id"]: get_credit(task_name, u["user_id"])
        for u in users
    }

    cursor = get_cursor(task_name)
    result = []

    for _ in range(max(0, steps)):
        index, _skipped = next_turn(users, cursor, credits)
        result.append(users[index]["user_id"])
        cursor = users[(index + 1) % len(users)]["position"]

    return result
