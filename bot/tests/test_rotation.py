"""Regression tests for the duty rotation.

Run from the bot/ directory:  python3 -m tests.test_rotation
Every test here corresponds to a defect that was live in production.
"""
import json
import os
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# config.py holds the secrets and is gitignored, so stub it for tests.
if "config" not in sys.modules:
    cfg = types.ModuleType("config")
    cfg.BOT_TOKEN = "0:test"
    cfg.OWNER_TELEGRAM_ID = 1
    sys.modules["config"] = cfg

import db.connection as connection

_tmp = tempfile.mkdtemp(prefix="apartmentmate-tests-")
connection.DB_PATH = Path(_tmp) / "test.db"

from db.connection import init_db, get_db          # noqa: E402
from db import repositories as R                   # noqa: E402
from core.rotation_engine import get_next_responsible, start_index  # noqa: E402
from core.simulation import simulate_next          # noqa: E402

A, B, C, D = 101, 102, 103, 104
FAILURES = []


def fresh(task="cook", users=(A, B, C)):
    if connection.DB_PATH.exists():
        connection.DB_PATH.unlink()
    for suffix in ("-wal", "-shm"):
        extra = Path(str(connection.DB_PATH) + suffix)
        if extra.exists():
            extra.unlink()
    init_db()
    R.create_task(task)
    for u in users:
        R.add_user_to_task(task, u)
    return task


def check(name, actual, expected):
    if actual == expected:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}\n          expected {expected!r}\n          actual   {actual!r}")
        FAILURES.append(name)


print("removing a user does not move anybody else's turn")
t = fresh()
check("A, B, C in order", simulate_next(t, 3), [A, B, C])
get_next_responsible(t)                                   # A does it
check("B is next", simulate_next(t, 1), [B])
R.deactivate_user(t, A)
check("B is still next after A is removed", simulate_next(t, 1), [B])
get_next_responsible(t)                                   # B does it
check("C follows B", simulate_next(t, 1), [C])
get_next_responsible(t)                                   # C does it
check("wraps back to B, not to the removed A", simulate_next(t, 1), [B])

print()
print("removing the user whose turn it is passes the turn forward")
t = fresh()
check("A is up", simulate_next(t, 1), [A])
R.deactivate_user(t, A)
check("turn passes to B", simulate_next(t, 1), [B])

print()
print("a reactivated user returns to their original slot")
t = fresh()
R.deactivate_user(t, B)
check("B is gone", simulate_next(t, 3), [A, C, A])
R.add_user_to_task(t, B)
check("B is back between A and C", simulate_next(t, 3), [A, B, C])

print()
print("skip credits")
t = fresh()
R.add_credit(t, A)
check("A's credit skips A once", simulate_next(t, 3), [B, C, A])
who, prev, consumed = get_next_responsible(t)
check("B took the turn", who, B)
check("A's credit was spent", R.get_credit(t, A), 0)
check("the spend was recorded for undo", consumed, [A])

print()
print("a credit is never spent when everybody holds one")
t = fresh()
for u in (A, B, C):
    R.add_credit(t, u)
who, prev, consumed = get_next_responsible(t)
check("A still takes the turn", who, A)
check("no credits burned", consumed, [])
check("A keeps their credit", R.get_credit(t, A), 1)

print()
print("the simulation and the live engine never disagree")
t = fresh(users=(A, B, C, D))
R.add_credit(t, B)
R.add_credit(t, D)
R.add_credit(t, D)
predicted = simulate_next(t, 6)
actual = [get_next_responsible(t)[0] for _ in range(6)]
check("six turns predicted == six turns taken", actual, predicted)

print()
print("cancelling a completion puts back the credits it spent")
t = fresh()
R.add_credit(t, A)
R.add_credit(t, B)
who, prev, consumed = get_next_responsible(t)
check("C took the turn", who, C)
check("A and B paid a credit each", (R.get_credit(t, A), R.get_credit(t, B)), (0, 0))
R.set_cursor(t, prev)
R.refund_credits(t, consumed)
check("credits refunded", (R.get_credit(t, A), R.get_credit(t, B)), (1, 1))
check("C is responsible again", simulate_next(t, 1), [C])

print()
print("a non-member cannot earn a skip credit")
t = fresh()
check("add_credit reports failure for a stranger", R.add_credit(t, 999), False)
check("is_task_member is False for a stranger", R.is_task_member(t, 999), False)
check("is_task_member is True for A", R.is_task_member(t, A), True)
R.deactivate_user(t, A)
check("is_task_member is False once removed", R.is_task_member(t, A), False)

print()
print("the 30-day sweep prunes every rolling table")
t = fresh()
R.add_history(t, A)
R.add_volunteer_log(t, B)
R.log_action(t, A, "DONE", -100, 5, prev_cursor=0, consumed_credits=[B])
R.cleanup_history(0)
with get_db() as conn:
    counts = tuple(
        conn.execute(f"SELECT COUNT(*) c FROM {tbl}").fetchone()["c"]
        for tbl in ("task_history", "task_volunteer_log", "task_actions")
    )
check("history, volunteer log and actions all pruned", counts, (0, 0, 0))

print()
print("timestamps are one format, so the activity feed sorts correctly")
t = fresh()
R.add_history(t, A)
R.add_volunteer_log(t, B)
R.add_history(t, C)
rows = R.get_activity_last_30_days()
seps = {row["ts"][10] for row in rows}
check("every timestamp uses the same separator", seps, {"T"})
check("newest first", [r["ts"] for r in rows], sorted((r["ts"] for r in rows), reverse=True))
check("both kinds of activity are present",
      sorted({r["type"] for r in rows}), ["COMPLETED", "VOLUNTEER"])

print()
print("an undo record round-trips through the database")
t = fresh()
R.add_credit(t, A)
who, prev, consumed = get_next_responsible(t)
R.log_action(t, who, "DONE", -100, 7, prev_cursor=prev, consumed_credits=consumed)
action = R.get_action_by_message(-100, 7)
check("prev_cursor stored", action["prev_cursor"], prev)
check("consumed credits stored", json.loads(action["consumed_credits"]), [A])

print()
print("state reads never crash on a half-created task")
t = fresh()
with get_db() as conn:
    conn.execute("INSERT INTO tasks(task_name) VALUES ('orphan')")
    conn.execute("INSERT INTO task_users(task_name,user_id,position,active) VALUES ('orphan',?,0,1)", (A,))
check("get_cursor defaults instead of raising", R.get_cursor("orphan"), 0)
check("simulate_next works on it", simulate_next("orphan", 2), [A, A])

print()
print("start_index resolves a cursor pointing at a departed user")
users = [{"user_id": B, "position": 1}, {"user_id": C, "position": 2}]
check("cursor 0 with position 0 gone -> first active", start_index(users, 0), 0)
check("cursor 2 -> C", start_index(users, 2), 1)
check("cursor past the end wraps to the front", start_index(users, 99), 0)

print()
print("the old index-based cursor is migrated to a position value")
if connection.DB_PATH.exists():
    connection.DB_PATH.unlink()
init_db()
R.create_task("legacy")
for u in (A, B, C):
    R.add_user_to_task("legacy", u)
with get_db() as conn:
    # simulate a pre-migration database: cursor 2 meant "index 2", i.e. C
    conn.execute("DELETE FROM schema_migrations WHERE name = 'cursor_stores_position'")
    conn.execute("UPDATE task_state SET cursor_position = 2 WHERE task_name = 'legacy'")
    conn.execute("UPDATE task_users SET position = position * 10 WHERE task_name = 'legacy'")
init_db()
check("index 2 became C's position value", R.get_cursor("legacy"), 20)
check("C is responsible, as they were before the migration", simulate_next("legacy", 1), [C])

print()
print("cancelling an OLD confirmation undoes that entry, not the newest one")
t = fresh()
first = R.add_history(t, A)
R.log_action(t, A, "DONE", -100, 11, prev_cursor=0, consumed_credits=[], target_rowid=first)
second = R.add_history(t, A)
R.log_action(t, A, "DONE", -100, 12, prev_cursor=0, consumed_credits=[], target_rowid=second)
old_action = R.get_action_by_message(-100, 11)
R.remove_last_history(t, A, rowid=old_action["target_rowid"])
with get_db() as conn:
    left = [r["rowid"] for r in conn.execute("SELECT rowid FROM task_history").fetchall()]
check("the older entry is gone and the newer one survives", left, [second])

print()
print("the same rule applies to a volunteer entry")
t = fresh()
v1 = R.add_volunteer_log(t, B)
v2 = R.add_volunteer_log(t, B)
R.remove_volunteer_log(t, B, rowid=v1)
with get_db() as conn:
    left = [r["rowid"] for r in conn.execute("SELECT rowid FROM task_volunteer_log").fetchall()]
check("the pointed-at volunteer entry is gone", left, [v2])

print()
print("times are shown in the apartment's timezone, not UTC")
utc_late = "2026-08-16T21:30:00+00:00"        # 02:30 the next day in Tashkent
local = R.parse_ts(utc_late)
check("date rolls over to the 17th", local.strftime("%d.%m"), "17.08")
check("hour is local", local.strftime("%H:%M"), "02:30")
check("cooldown still measures real elapsed time",
      R.parse_ts("2026-08-16T21:30:00+00:00").timestamp(),
      R.parse_ts("2026-08-17T02:30:00+05:00").timestamp())

print()
print("a duty cannot go permanently dead when everyone holds credits")
# The audit's worst case: the only zero-credit member is removed while everyone
# left holds two credits. The old scan budget ran out and simulate_next returned
# [], so /now said "no users" and every duty command said "no users assigned"
# forever, with the roster fully intact.
t = fresh(users=(A, B, C, D))
for u in (B, C, D):
    R.add_credit(t, u)
    R.add_credit(t, u)
R.deactivate_user(t, A)
check("the duty still names somebody", simulate_next(t, 1), [B])
check("five turns still resolve", len(simulate_next(t, 5)), 5)
who, _, _ = get_next_responsible(t)
check("and the live engine agrees", who, B)

print()
print("uppercase duty names are folded down so their command works")
if connection.DB_PATH.exists():
    connection.DB_PATH.unlink()
init_db()
with get_db() as conn:
    conn.execute("INSERT INTO tasks(task_name) VALUES ('Kitchen')")
    conn.execute("INSERT INTO task_state(task_name, cursor_position) VALUES ('Kitchen', 0)")
    conn.execute("INSERT INTO task_users(task_name,user_id,position,active) VALUES ('Kitchen',?,0,1)", (A,))
    conn.execute("INSERT INTO task_credits(task_name,user_id,credits) VALUES ('Kitchen',?,0)", (A,))
    conn.execute("DELETE FROM schema_migrations WHERE name = 'lowercase_task_names'")
init_db()
check("/kitchen now finds the task", R.task_exists("kitchen"), True)
check("the old name is gone", R.task_exists("Kitchen"), False)
check("its roster came along", [r["user_id"] for r in R.get_task_users("kitchen")], [A])

print()
print("D1: covering somebody's turn completes it, and cannot be farmed")
# Old rule: typing the duty command when it was not your turn banked a credit,
# left the duty undone and left the rotation where it was — so one roommate
# could mint a credit every two hours and never work again.
t = fresh()
check("A is up", simulate_next(t, 1), [A])
covered, prev, consumed = get_next_responsible(t)      # B covers for A
R.add_credit(t, B)
R.add_history(t, B)
check("the turn that was covered belonged to A", covered, A)
check("B earned exactly one credit", R.get_credit(t, B), 1)
check("the rotation moved past A, onto B's slot", R.get_cursor(t), 1)
# B is next in line but is holding the credit they just earned, so the credit
# does its job immediately: B sits out and C takes the turn, then it is A again.
check("B's own credit spends itself on B's next turn", simulate_next(t, 2), [C, A])
# Farming check: every credit costs a real turn, so N covers advance the
# rotation N times instead of minting N free credits against a standing turn.
before = R.get_cursor(t)
for _ in range(3):
    get_next_responsible(t)
check("three more turns actually moved the cursor", R.get_cursor(t) != before, True)

print()
print("D1: cancelling a cover puts the turn back where it was")
t = fresh()
covered, prev, consumed = get_next_responsible(t)
R.add_credit(t, B)
rowid = R.add_history(t, B)
R.log_action(t, B, "VOLUNTEER", -100, 21, prev_cursor=prev,
             consumed_credits=consumed, target_rowid=rowid)
action = R.get_action_by_message(-100, 21)
R.remove_credit(t, B)
R.remove_last_history(t, B, rowid=action["target_rowid"])
R.set_cursor(t, action["prev_cursor"])
check("B's credit is gone again", R.get_credit(t, B), 0)
check("A is up again", simulate_next(t, 1), [A])
with get_db() as conn:
    check("the history entry went with it",
          conn.execute("SELECT COUNT(*) c FROM task_history").fetchone()["c"], 0)

print()
print("D2: the bot belongs to exactly one group")
t = fresh()
check("no apartment before anything happens", R.get_apartment_chat_id(), None)
check("the first chat claims it", R.claim_apartment_chat_id(-100), True)
check("the same chat is still ours", R.claim_apartment_chat_id(-100), True)
check("a different chat is refused", R.claim_apartment_chat_id(-999), False)
check("and the apartment did not move", R.get_apartment_chat_id(), -100)
R.set_apartment_chat_id(-777)
check("/claim can move it deliberately", R.get_apartment_chat_id(), -777)

print()
print("D2: an existing install adopts its one known group without being asked")
if connection.DB_PATH.exists():
    connection.DB_PATH.unlink()
init_db()
R.save_group(-4242)
with get_db() as conn:
    conn.execute("DELETE FROM schema_migrations WHERE name = 'adopt_single_group'")
init_db()
check("the single known group became the apartment", R.get_apartment_chat_id(), -4242)

print()
print("D2: with several known groups the bot refuses to guess")
if connection.DB_PATH.exists():
    connection.DB_PATH.unlink()
init_db()
R.save_group(-1)
R.save_group(-2)
with get_db() as conn:
    conn.execute("DELETE FROM schema_migrations WHERE name = 'adopt_single_group'")
init_db()
check("no apartment was guessed", R.get_apartment_chat_id(), None)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("all rotation regression tests passed")
