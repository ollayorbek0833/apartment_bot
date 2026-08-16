"""Boot + handler-dispatch tests. No network, no Telegram token needed.

Run from the bot/ directory:  python3 -m tests.test_wiring
"""
import asyncio
import datetime
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if "config" not in sys.modules:
    cfg = types.ModuleType("config")
    cfg.BOT_TOKEN = "123456:AAtest"
    cfg.OWNER_TELEGRAM_ID = 1
    sys.modules["config"] = cfg

import db.connection as connection

_tmp = tempfile.mkdtemp(prefix="apartmentmate-wiring-")
connection.DB_PATH = Path(_tmp) / "test.db"

from telegram import Chat, Message, MessageEntity, Update, User   # noqa: E402
from telegram.ext import Application, CommandHandler, MessageHandler, TypeHandler  # noqa: E402

import main                                                        # noqa: E402
from db.connection import init_db                                  # noqa: E402
from db.repositories import (                                     # noqa: E402
    get_all_groups, create_task, add_user_to_task, set_apartment_chat_id,
    get_apartment_chat_id,
)
from tg.admin_commands import RESERVED_TASK_NAMES, TASK_NAME_RE    # noqa: E402
from scheduler.daily_jobs import scheduler, setup_scheduler        # noqa: E402

FAILURES = []


def check(name, actual, expected):
    if actual == expected:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}\n          expected {expected!r}\n          actual   {actual!r}")
        FAILURES.append(name)


def build_app():
    """The real handler set from main.main(), without run_polling()."""
    app = Application.builder().token("123456:AAtest").build()
    app._initialized = True
    app.bot._bot_user = User(id=1, first_name="ApartmentMate", is_bot=True,
                             username="apartment_mate_bot")

    for name, handler in (
        ("add_task", main.add_task), ("add_user", main.add_user),
        ("remove_user", main.remove_user), ("data", main.data_command),
        ("now", main.now), ("history", main.history), ("my_tasks", main.my_tasks),
        ("help", main.help_command), ("help_admin", main.help_admin_command),
        ("show", main.show_team), ("start", main.help_command),
        ("cancel", main.cancel), ("tasks", main.tasks_command),
        ("credits", main.credits_command), ("claim", main.claim),
    ):
        app.add_handler(CommandHandler(name, handler))
    app.add_handler(MessageHandler(main.filters.COMMAND, main.task_command))
    app.add_handler(TypeHandler(Update, main.remember_group), group=1)
    return app


def message(app, chat, user, text):
    entities = []
    if text.startswith("/"):
        entities = [MessageEntity(type="bot_command", offset=0, length=len(text.split()[0]))]
    msg = Message(message_id=1, date=datetime.datetime.now(datetime.timezone.utc),
                  chat=chat, from_user=user, text=text, entities=entities)
    msg.set_bot(app.bot)
    return Update(update_id=1, message=msg)


async def dispatch_tests():
    init_db()
    app = build_app()
    chat = Chat(id=-1001234, type="supergroup")
    user = User(id=555, first_name="Ali", is_bot=False)
    set_apartment_chat_id(chat.id)

    create_task("oshxona")
    add_user_to_task("oshxona", user.id)

    fired = []
    for name in ("now", "task_command", "remember_group"):
        original = getattr(main, name)

        async def spy(update, context, _n=name, _o=original):
            fired.append(_n)
            if _n == "remember_group":
                await _o(update, context)

        setattr(main, name, spy)

    app = build_app()

    for text in ("/now", "/oshxona", "hello"):
        fired.clear()
        await app.process_update(message(app, chat, user, text))
        check(f"{text!r} also reaches remember_group", "remember_group" in fired, True)

    check("a command-only group is registered for the daily announcement",
          get_all_groups(), [-1001234])


print("every update reaches the group registrar, not just plain chat messages")
asyncio.run(dispatch_tests())

print()
print("no duty may be named after a command the bot already owns")
registered = set(main.RESERVED_COMMANDS)
check("main.py and admin_commands.py agree on the reserved list",
      registered, RESERVED_TASK_NAMES)
for bad in ("history", "Now", "my task", "oshxona!", "", "x" * 33):
    ok = bool(TASK_NAME_RE.match(bad)) and bad not in RESERVED_TASK_NAMES
    check(f"{bad!r} rejected", ok, False)
for good in ("oshxona", "cook", "hammom_2"):
    ok = bool(TASK_NAME_RE.match(good)) and good not in RESERVED_TASK_NAMES
    check(f"{good!r} accepted", ok, True)

print()
print("the daily jobs fire in apartment local time, not the server's")


async def scheduler_tests():
    scheduler.start(paused=True)
    setup_scheduler(app=None)
    jobs = {j.id: j for j in scheduler.get_jobs()}
    check("both jobs registered", sorted(jobs), ["cleanup_history", "daily_announcement"])
    check("announcement timezone is Tashkent",
          str(jobs["daily_announcement"].trigger.timezone), "Asia/Tashkent")
    check("announcement hour is 9 local",
          str(jobs["daily_announcement"].trigger.fields[5]), "9")
    check("cleanup timezone is Tashkent too",
          str(jobs["cleanup_history"].trigger.timezone), "Asia/Tashkent")
    # A restart re-runs post_init; without stable ids that used to stack up a
    # second copy of every job.
    setup_scheduler(app=None)
    check("a restart does not duplicate the jobs", len(scheduler.get_jobs()), 2)
    scheduler.shutdown(wait=False)


asyncio.run(scheduler_tests())

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("all wiring tests passed")
