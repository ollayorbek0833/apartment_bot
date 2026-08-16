import logging

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, TypeHandler, filters
)

from config import BOT_TOKEN
from db.connection import init_db
from db.repositories import save_group, remove_group
from tg.admin_commands import add_task, add_user, show_team, remove_user, cancel
from tg.data_command import data_command
from tg.help_command import help_command, help_admin_command
from tg.user_commands import credits_command, my_tasks, task_command, tasks_command
from tg.today_commands import now
from tg.history_commands import history
from scheduler.daily_jobs import setup_scheduler, scheduler

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("apartmentmate")

TOKEN = BOT_TOKEN

# Every command the bot itself owns. A duty may not be named after one of these,
# because a CommandHandler always wins over the dynamic duty handler and the duty
# would be created but permanently unusable.
RESERVED_COMMANDS = (
    "add_task", "add_user", "remove_user", "data",
    "now", "history", "my_tasks", "help", "help_admin",
    "show", "start", "cancel", "tasks", "credits",
)


async def on_error(update, context):
    """Nothing used to log a handler crash, so the bot just went quiet."""
    log.exception("handler failed for update %s", getattr(update, "update_id", "?"),
                  exc_info=context.error)


async def post_init(app: Application):
    setup_scheduler(app)
    scheduler.start()
    log.info("scheduler started with jobs: %s", [j.id for j in scheduler.get_jobs()])


async def post_shutdown(app: Application):
    if scheduler.running:
        scheduler.shutdown(wait=False)


async def remember_group(update, context):
    """Registered in its own handler group so it runs for EVERY update.

    In group 0 it only ever fired for plain chat messages, because the command
    handlers ahead of it already matched and stopped the group — so an apartment
    that only ever types commands was never registered and never received the
    daily announcement.
    """
    chat = update.effective_chat
    if not chat or chat.type not in ("group", "supergroup"):
        return

    member = update.my_chat_member
    if member and member.new_chat_member.status in ("left", "kicked"):
        remove_group(chat.id)
        log.info("removed from chat %s, dropped from the announcement list", chat.id)
        return

    save_group(chat.id)


def main():
    init_db()
    app = (
        Application.builder()
        .token(TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # admin
    app.add_handler(CommandHandler("add_task", add_task))
    app.add_handler(CommandHandler("add_user", add_user))
    app.add_handler(CommandHandler("remove_user", remove_user))
    app.add_handler(CommandHandler("data", data_command))

    # user
    app.add_handler(CommandHandler("now", now))
    app.add_handler(CommandHandler("history", history))
    app.add_handler(CommandHandler("my_tasks", my_tasks))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("help_admin", help_admin_command))
    app.add_handler(CommandHandler("show", show_team))
    app.add_handler(CommandHandler("start", help_command))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("tasks", tasks_command))
    app.add_handler(CommandHandler("credits", credits_command))

    # dynamic duty commands (/oshxona, /cook, ...)
    app.add_handler(MessageHandler(filters.COMMAND, task_command))

    # remember groups — own handler group, so it sees commands and membership
    # changes too, not just plain chat messages
    app.add_handler(TypeHandler(Update, remember_group), group=1)

    app.add_error_handler(on_error)

    log.info("bot started")
    app.run_polling(allowed_updates=["message", "edited_message", "my_chat_member"])


if __name__ == "__main__":
    main()
