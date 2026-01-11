from telegram import User


def format_user(user: User) -> str:
    """
    Priority:
    1. @username
    2. FirstName LastName
    3. FirstName
    """
    if user.username:
        return f"@{user.username}"

    if user.first_name and user.last_name:
        return f"{user.first_name} {user.last_name}"

    return user.first_name or "Unknown user"
