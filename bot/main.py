from telegram.ext import Application, CommandHandler, MessageHandler, filters

from config import BOT_TOKEN
from db.connection import init_db
from db.repositories import save_group
from tg.admin_commands import add_task, add_user, show_team, remove_user, cancel
from tg.data_command import data_command
from tg.help_command import help_command, help_admin_command
from tg.user_commands import my_tasks, task_command, tasks_command
from tg.today_commands import now
from tg.history_commands import history
from scheduler.daily_jobs import setup_scheduler, scheduler

TOKEN = BOT_TOKEN


async def post_init(app: Application):
    setup_scheduler(app)
    scheduler.start()   # ✅ event loop is now running


async def remember_group(update, context):
    chat = update.effective_chat
    if not chat or chat.type not in ("group", "supergroup"):
        return
    save_group(chat.id)


def main():
    init_db()
    app = (
        Application.builder()
        .token(TOKEN)
        .post_init(post_init)   # 🔥 THIS IS THE KEY
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

    # dynamic volunteer
    app.add_handler(MessageHandler(filters.COMMAND, task_command))

    # remember groups
    app.add_handler(MessageHandler(filters.ALL, remember_group))

    print("🤖 Bot started")
    app.run_polling()


if __name__ == "__main__":
    main()
