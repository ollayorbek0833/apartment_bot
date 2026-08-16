/**
 * The rules against a real D1 database, in Miniflare.
 */
import { env as rawEnv } from 'cloudflare:workers';
import { beforeEach, describe, expect, it } from 'vitest';

import { DutyService } from '../src/core/service';
import { Repo } from '../src/db/repo';
import { buildCsv } from '../src/tg/format';
import { daysAgoIso, localDate } from '../src/tg/time';

// The generated Cloudflare.Env type is not available without `wrangler types`,
// and the bindings here come from vitest.config.ts.
const env = rawEnv as unknown as { DB: D1Database };

const A = 101, B = 102, C = 103;
const SCHEMA = `
CREATE TABLE IF NOT EXISTS tasks (task_name TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS task_users (task_name TEXT NOT NULL, user_id INTEGER NOT NULL, position INTEGER NOT NULL, active INTEGER NOT NULL DEFAULT 1, PRIMARY KEY (task_name, user_id));
CREATE TABLE IF NOT EXISTS task_credits (task_name TEXT NOT NULL, user_id INTEGER NOT NULL, credits INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (task_name, user_id));
CREATE TABLE IF NOT EXISTS task_state (task_name TEXT PRIMARY KEY, cursor_position INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS task_history (id INTEGER PRIMARY KEY AUTOINCREMENT, task_name TEXT NOT NULL, user_id INTEGER NOT NULL, done_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS task_volunteer_log (id INTEGER PRIMARY KEY AUTOINCREMENT, task_name TEXT NOT NULL, user_id INTEGER NOT NULL, volunteered_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS task_cooldowns (task_name TEXT NOT NULL, user_id INTEGER NOT NULL, last_used_at TEXT NOT NULL, PRIMARY KEY (task_name, user_id));
CREATE TABLE IF NOT EXISTS task_actions (id INTEGER PRIMARY KEY AUTOINCREMENT, task_name TEXT NOT NULL, user_id INTEGER NOT NULL, action_type TEXT NOT NULL, chat_id INTEGER NOT NULL, message_id INTEGER NOT NULL, created_at TEXT NOT NULL, prev_cursor INTEGER, consumed_credits TEXT, target_rowid INTEGER);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS user_names (user_id INTEGER PRIMARY KEY, name TEXT NOT NULL, updated_at TEXT NOT NULL);
`;

let repo: Repo;
let duty: DutyService;

async function reset() {
  for (const table of [
    'tasks', 'task_users', 'task_credits', 'task_state', 'task_history',
    'task_volunteer_log', 'task_cooldowns', 'task_actions', 'settings', 'user_names',
  ]) {
    await env.DB.prepare(`DELETE FROM ${table}`).run();
  }
}

beforeEach(async () => {
  for (const stmt of SCHEMA.split(';').map((s) => s.trim()).filter(Boolean)) {
    await env.DB.prepare(stmt).run();
  }
  await reset();
  repo = new Repo(env.DB);
  duty = new DutyService(repo);
  await repo.createTask('oshxona');
  for (const u of [A, B, C]) await repo.addUser('oshxona', u);
});

describe('taking a turn', () => {
  it('advances the rotation and reports what it changed', async () => {
    const taken = await duty.takeTurn('oshxona');
    expect(taken).toEqual({ turnOwner: A, prevCursor: 0, consumed: [] });
    expect(await repo.cursor('oshxona')).toBe(1);
    expect(await duty.preview('oshxona', 1)).toEqual([B]);
  });

  it('spends the skip credits it passed over, in the database', async () => {
    await repo.addCredit('oshxona', A);
    const taken = await duty.takeTurn('oshxona');
    expect(taken!.turnOwner).toBe(B);
    expect(taken!.consumed).toEqual([A]);
    expect(await repo.credit('oshxona', A)).toBe(0);
  });

  it('returns null rather than throwing on an empty roster', async () => {
    await repo.createTask('empty');
    expect(await duty.takeTurn('empty')).toBeNull();
    expect(await duty.preview('empty', 3)).toEqual([]);
  });
});

describe('undo puts back everything a turn changed', () => {
  it('restores the cursor and refunds every spent credit', async () => {
    await repo.addCredit('oshxona', A);
    await repo.addCredit('oshxona', B);
    const taken = (await duty.takeTurn('oshxona'))!;
    expect(taken.turnOwner).toBe(C);
    expect(await repo.credit('oshxona', A)).toBe(0);

    await duty.undoTurn('oshxona', taken.prevCursor, taken.consumed);

    expect(await repo.credit('oshxona', A)).toBe(1);
    expect(await repo.credit('oshxona', B)).toBe(1);
    expect(await duty.preview('oshxona', 1)).toEqual([C]);
  });

  it('deletes the exact history row, not merely the newest', async () => {
    const first = await repo.addHistory('oshxona', A);
    const second = await repo.addHistory('oshxona', A);
    await repo.deleteHistory(first);
    const { results } = await env.DB.prepare('SELECT id FROM task_history').all<{ id: number }>();
    expect(results.map((r: { id: number }) => r.id)).toEqual([second]);
  });
});

describe('covering a turn cannot be farmed', () => {
  it('costs a real turn for every credit granted', async () => {
    // B covers for A: the duty is done, the rotation moves on, B earns one
    // credit. Repeating it always consumes another turn, so N credits cost N
    // turns — the old rule minted one every two hours against a standing turn.
    const before = await repo.cursor('oshxona');
    const taken = (await duty.takeTurn('oshxona'))!;
    await repo.addCredit('oshxona', B);
    await repo.addHistory('oshxona', B);

    expect(taken.turnOwner).toBe(A);
    expect(await repo.credit('oshxona', B)).toBe(1);
    expect(await repo.cursor('oshxona')).not.toBe(before);
    // B is next but holds the credit they just earned, so it spends itself.
    expect(await duty.preview('oshxona', 2)).toEqual([C, A]);
  });
});

describe('membership', () => {
  it('refuses a credit to somebody who is not in the rotation', async () => {
    expect(await repo.addCredit('oshxona', 999)).toBe(false);
    expect(await repo.isMember('oshxona', 999)).toBe(false);
    expect(await repo.isMember('oshxona', A)).toBe(true);
  });

  it('stops counting a member once they are removed', async () => {
    expect(await repo.deactivateUser('oshxona', A)).toBe(true);
    expect(await repo.isMember('oshxona', A)).toBe(false);
    expect(await repo.deactivateUser('oshxona', A)).toBe(false);
  });
});

describe('the apartment', () => {
  it('has no owner until one is set', async () => {
    expect(await repo.getApartmentChatId()).toBeNull();
  });

  it('remembers exactly one chat', async () => {
    await repo.setApartmentChatId(-100);
    expect(await repo.getApartmentChatId()).toBe(-100);
    await repo.setApartmentChatId(-200);
    expect(await repo.getApartmentChatId()).toBe(-200);
  });
});

describe('the rolling 30 days', () => {
  it('prunes every table that feeds the export, not just completions', async () => {
    const old = new Date(Date.now() - 45 * 86_400_000).toISOString();
    await env.DB.prepare(
      "INSERT INTO task_history(task_name,user_id,done_at) VALUES ('oshxona',?,?)",
    ).bind(A, old).run();
    await env.DB.prepare(
      "INSERT INTO task_volunteer_log(task_name,user_id,volunteered_at) VALUES ('oshxona',?,?)",
    ).bind(B, old).run();
    await env.DB.prepare(
      `INSERT INTO task_actions(task_name,user_id,action_type,chat_id,message_id,created_at)
       VALUES ('oshxona',?,'DONE',-1,1,?)`,
    ).bind(A, old).run();

    await repo.prune(daysAgoIso(30));

    for (const table of ['task_history', 'task_volunteer_log', 'task_actions']) {
      const row = await env.DB.prepare(`SELECT COUNT(*) AS c FROM ${table}`).first<{ c: number }>();
      expect(row!.c, table).toBe(0);
    }
  });

  it('keeps recent rows', async () => {
    await repo.addHistory('oshxona', A);
    await repo.prune(daysAgoIso(30));
    const row = await env.DB.prepare('SELECT COUNT(*) AS c FROM task_history').first<{ c: number }>();
    expect(row!.c).toBe(1);
  });
});

describe('the activity export', () => {
  it('sorts completions and covers together, newest first', async () => {
    await repo.addHistory('oshxona', A);
    await repo.addVolunteerLog('oshxona', B);
    await repo.addHistory('oshxona', C);

    const rows = await repo.activitySince(daysAgoIso(30));
    expect(rows).toHaveLength(3);
    expect(rows.map((r) => r.ts)).toEqual([...rows.map((r) => r.ts)].sort().reverse());
    expect(new Set(rows.map((r) => r.type))).toEqual(new Set(['COMPLETED', 'VOLUNTEER']));
  });

  it('writes one value per heading, including the type column', () => {
    const csv = buildCsv(
      [{ task_name: 'oshxona', user_id: A, ts: '2026-08-16T21:30:00.000Z', type: 'COMPLETED' }],
      new Map([[A, '@ali']]),
      'Asia/Tashkent',
    );
    const [header, row] = csv.split('\n');
    expect(header.split(',')).toHaveLength(5);
    expect(row.split(',')).toHaveLength(5);
    expect(row).toContain('COMPLETED');
    // 21:30 UTC is 02:30 the next morning in Tashkent.
    expect(row.startsWith('17.08.2026,02:30')).toBe(true);
  });

  it('defuses a display name Excel would run as a formula', () => {
    const csv = buildCsv(
      [{ task_name: 'oshxona', user_id: A, ts: '2026-08-16T09:00:00.000Z', type: 'COMPLETED' }],
      new Map([[A, '=1+1']]),
      'Asia/Tashkent',
    );
    expect(csv.split('\n')[1]).toContain("'=1+1");
  });
});

describe('display times', () => {
  it('shows the apartment day, not the UTC day', () => {
    expect(localDate('2026-08-16T21:30:00.000Z', 'Asia/Tashkent')).toBe('17.08');
    expect(localDate('2026-08-16T21:30:00.000Z', 'UTC')).toBe('16.08');
  });
});
