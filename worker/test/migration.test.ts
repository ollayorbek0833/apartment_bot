/**
 * The cutover: whoever the Python bot said was next must still be next in D1.
 *
 * The rows below are the literal output of
 * `worker/scripts/export_sqlite_to_d1.py` run against a database where user 102
 * had been removed — so positions read 0, 2, 3 with a hole at 1, and the old
 * index-based cursor of 1 meant "the second ACTIVE member", user 103.
 */
import { env as rawEnv } from 'cloudflare:workers';
import { beforeEach, describe, expect, it } from 'vitest';

import { DutyService } from '../src/core/service';
import { Repo } from '../src/db/repo';

const env = rawEnv as unknown as { DB: D1Database };

const SCHEMA = [
  'CREATE TABLE IF NOT EXISTS task_users (task_name TEXT NOT NULL, user_id INTEGER NOT NULL, position INTEGER NOT NULL, active INTEGER NOT NULL DEFAULT 1, PRIMARY KEY (task_name, user_id))',
  'CREATE TABLE IF NOT EXISTS task_credits (task_name TEXT NOT NULL, user_id INTEGER NOT NULL, credits INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (task_name, user_id))',
  'CREATE TABLE IF NOT EXISTS task_state (task_name TEXT PRIMARY KEY, cursor_position INTEGER NOT NULL DEFAULT 0)',
];

const EXPORTED = [
  "INSERT INTO task_users(task_name, user_id, position, active) VALUES ('oshxona', 101, 0, 1)",
  "INSERT INTO task_users(task_name, user_id, position, active) VALUES ('oshxona', 102, 1, 0)",
  "INSERT INTO task_users(task_name, user_id, position, active) VALUES ('oshxona', 103, 2, 1)",
  "INSERT INTO task_users(task_name, user_id, position, active) VALUES ('oshxona', 104, 3, 1)",
  "INSERT INTO task_state(task_name, cursor_position) VALUES ('oshxona', 2)",
];

beforeEach(async () => {
  for (const stmt of SCHEMA) await env.DB.prepare(stmt).run();
  for (const t of ['task_users', 'task_credits', 'task_state']) {
    await env.DB.prepare(`DELETE FROM ${t}`).run();
  }
  for (const stmt of EXPORTED) await env.DB.prepare(stmt).run();
});

describe('SQLite to D1 cutover', () => {
  it('keeps the same person next as the Python bot had', async () => {
    const duty = new DutyService(new Repo(env.DB));
    expect(await duty.preview('oshxona', 1)).toEqual([103]);
  });

  it('keeps the whole upcoming order, skipping the removed member', async () => {
    const duty = new DutyService(new Repo(env.DB));
    expect(await duty.preview('oshxona', 4)).toEqual([103, 104, 101, 103]);
  });

  it('leaves the hole in the position sequence harmless', async () => {
    // Positions 0, 2, 3 with 1 missing. An index-based cursor would have walked
    // off the end of a three-element list; a position-based one cannot.
    const repo = new Repo(env.DB);
    const roster = await repo.roster('oshxona');
    expect(roster.map((m) => m.position)).toEqual([0, 2, 3]);
    expect(await repo.cursor('oshxona')).toBe(2);
  });
});
