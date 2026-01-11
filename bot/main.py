from telegram.ext import Application, CommandHandler, MessageHandler, filters

from config import BOT_TOKEN
from tg.admin_commands import add_task, add_user, show_team, remove_user
from tg.help_command import help_command
from tg.user_commands import volunteer, my_tasks
from tg.today_commands import today
from tg.history_commands import history
from scheduler.daily_jobs import setup_scheduler, scheduler

TOKEN = BOT_TOKEN


async def post_init(app: Application):
    setup_scheduler(app)
    scheduler.start()   # ✅ event loop is now running


async def remember_group(update, context):
    chat = update.effective_chat
    if not chat:
        return

    groups = context.application.bot_data.setdefault("groups", set())
    groups.add(chat.id)


def main():
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
    app.add_handler(CommandHandler("show_team", show_team))

    # user
    app.add_handler(CommandHandler("today", today))
    app.add_handler(CommandHandler("history", history))
    app.add_handler(CommandHandler("my_tasks", my_tasks))
    app.add_handler(CommandHandler("help", help_command))

    # dynamic volunteer
    app.add_handler(MessageHandler(filters.COMMAND, volunteer))

    # remember groups
    app.add_handler(MessageHandler(filters.ALL, remember_group))

    print("🤖 Bot started")
    app.run_polling()


if __name__ == "__main__":
    main()
