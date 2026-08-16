/**
 * Every D1 statement lives here. Handlers never write SQL.
 */
import type { RosterMember } from '../core/rotation';

/** One format for every timestamp, so the activity export can sort them. */
export function nowIso(): string {
  return new Date().toISOString();
}

export interface ActionRow {
  id: number;
  task_name: string;
  user_id: number;
  action_type: 'DONE' | 'VOLUNTEER';
  chat_id: number;
  message_id: number;
  created_at: string;
  prev_cursor: number | null;
  consumed_credits: string | null;
  target_rowid: number | null;
}

export interface ActivityRow {
  task_name: string;
  user_id: number;
  ts: string;
  type: 'COMPLETED' | 'VOLUNTEER';
}

export class Repo {
  constructor(private db: D1Database) {}

  // ---------- settings: the one group this bot serves ----------

  async getApartmentChatId(): Promise<number | null> {
    const row = await this.db
      .prepare("SELECT value FROM settings WHERE key = 'apartment_chat_id'")
      .first<{ value: string }>();
    return row ? Number(row.value) : null;
  }

  async setApartmentChatId(chatId: number): Promise<void> {
    await this.db
      .prepare(
        `INSERT INTO settings(key, value) VALUES ('apartment_chat_id', ?)
         ON CONFLICT(key) DO UPDATE SET value = excluded.value`,
      )
      .bind(String(chatId))
      .run();
  }

  // ---------- tasks ----------

  async taskExists(task: string): Promise<boolean> {
    const row = await this.db
      .prepare('SELECT 1 AS ok FROM tasks WHERE task_name = ?')
      .bind(task)
      .first();
    return row !== null;
  }

  async allTasks(): Promise<string[]> {
    const { results } = await this.db
      .prepare('SELECT task_name FROM tasks ORDER BY task_name')
      .all<{ task_name: string }>();
    return results.map((r) => r.task_name);
  }

  async createTask(task: string): Promise<void> {
    await this.db.batch([
      this.db.prepare('INSERT INTO tasks(task_name) VALUES (?)').bind(task),
      this.db
        .prepare('INSERT INTO task_state(task_name, cursor_position) VALUES (?, 0)')
        .bind(task),
    ]);
  }

  // ---------- roster ----------

  async roster(task: string): Promise<RosterMember[]> {
    const { results } = await this.db
      .prepare(
        `SELECT user_id, position FROM task_users
         WHERE task_name = ? AND active = 1
         ORDER BY position`,
      )
      .bind(task)
      .all<RosterMember>();
    return results;
  }

  async isMember(task: string, userId: number): Promise<boolean> {
    const row = await this.db
      .prepare(
        'SELECT 1 AS ok FROM task_users WHERE task_name = ? AND user_id = ? AND active = 1',
      )
      .bind(task, userId)
      .first();
    return row !== null;
  }

  async addUser(task: string, userId: number): Promise<'added' | 'reactivated' | 'exists'> {
    const existing = await this.db
      .prepare('SELECT active FROM task_users WHERE task_name = ? AND user_id = ?')
      .bind(task, userId)
      .first<{ active: number }>();

    if (existing === null) {
      const max = await this.db
        .prepare(
          'SELECT COALESCE(MAX(position), -1) + 1 AS next FROM task_users WHERE task_name = ?',
        )
        .bind(task)
        .first<{ next: number }>();
      await this.db.batch([
        this.db
          .prepare(
            'INSERT INTO task_users(task_name, user_id, position, active) VALUES (?, ?, ?, 1)',
          )
          .bind(task, userId, max?.next ?? 0),
        this.db
          .prepare(
            'INSERT OR IGNORE INTO task_credits(task_name, user_id, credits) VALUES (?, ?, 0)',
          )
          .bind(task, userId),
      ]);
      return 'added';
    }

    if (existing.active === 0) {
      await this.db.batch([
        this.db
          .prepare('UPDATE task_users SET active = 1 WHERE task_name = ? AND user_id = ?')
          .bind(task, userId),
        this.db
          .prepare(
            'INSERT OR IGNORE INTO task_credits(task_name, user_id, credits) VALUES (?, ?, 0)',
          )
          .bind(task, userId),
      ]);
      return 'reactivated';
    }

    return 'exists';
  }

  /** Returns false when the user was not in the rotation to begin with. */
  async deactivateUser(task: string, userId: number): Promise<boolean> {
    const res = await this.db
      .prepare(
        'UPDATE task_users SET active = 0 WHERE task_name = ? AND user_id = ? AND active = 1',
      )
      .bind(task, userId)
      .run();
    return (res.meta.changes ?? 0) > 0;
  }

  // ---------- credits ----------

  async credits(task: string): Promise<Map<number, number>> {
    const { results } = await this.db
      .prepare('SELECT user_id, credits FROM task_credits WHERE task_name = ?')
      .bind(task)
      .all<{ user_id: number; credits: number }>();
    return new Map(results.map((r) => [r.user_id, r.credits]));
  }

  async credit(task: string, userId: number): Promise<number> {
    const row = await this.db
      .prepare('SELECT credits FROM task_credits WHERE task_name = ? AND user_id = ?')
      .bind(task, userId)
      .first<{ credits: number }>();
    return row?.credits ?? 0;
  }

  /** False when there is no credit row, i.e. the user is not in this rotation. */
  async addCredit(task: string, userId: number): Promise<boolean> {
    const res = await this.db
      .prepare(
        'UPDATE task_credits SET credits = credits + 1 WHERE task_name = ? AND user_id = ?',
      )
      .bind(task, userId)
      .run();
    return (res.meta.changes ?? 0) > 0;
  }

  async removeCredit(task: string, userId: number): Promise<void> {
    await this.db
      .prepare(
        `UPDATE task_credits
         SET credits = CASE WHEN credits > 0 THEN credits - 1 ELSE 0 END
         WHERE task_name = ? AND user_id = ?`,
      )
      .bind(task, userId)
      .run();
  }

  async spendCredits(task: string, userIds: number[]): Promise<void> {
    if (userIds.length === 0) return;
    await this.db.batch(
      userIds.map((id) =>
        this.db
          .prepare(
            `UPDATE task_credits SET credits = credits - 1
             WHERE task_name = ? AND user_id = ? AND credits > 0`,
          )
          .bind(task, id),
      ),
    );
  }

  async refundCredits(task: string, userIds: number[]): Promise<void> {
    if (userIds.length === 0) return;
    await this.db.batch(
      userIds.map((id) =>
        this.db
          .prepare(
            'UPDATE task_credits SET credits = credits + 1 WHERE task_name = ? AND user_id = ?',
          )
          .bind(task, id),
      ),
    );
  }

  // ---------- cursor ----------

  async cursor(task: string): Promise<number> {
    const row = await this.db
      .prepare('SELECT cursor_position FROM task_state WHERE task_name = ?')
      .bind(task)
      .first<{ cursor_position: number }>();
    return row?.cursor_position ?? 0;
  }

  async setCursor(task: string, position: number): Promise<void> {
    await this.db
      .prepare(
        `INSERT INTO task_state(task_name, cursor_position) VALUES (?, ?)
         ON CONFLICT(task_name) DO UPDATE SET cursor_position = excluded.cursor_position`,
      )
      .bind(task, position)
      .run();
  }

  // ---------- cooldown ----------

  async inCooldown(task: string, userId: number, hours = 2): Promise<boolean> {
    const row = await this.db
      .prepare('SELECT last_used_at FROM task_cooldowns WHERE task_name = ? AND user_id = ?')
      .bind(task, userId)
      .first<{ last_used_at: string }>();
    if (!row) return false;
    const elapsed = Date.now() - Date.parse(row.last_used_at);
    return elapsed < hours * 3600_000;
  }

  async touchCooldown(task: string, userId: number): Promise<void> {
    await this.db
      .prepare(
        `INSERT INTO task_cooldowns(task_name, user_id, last_used_at) VALUES (?, ?, ?)
         ON CONFLICT(task_name, user_id) DO UPDATE SET last_used_at = excluded.last_used_at`,
      )
      .bind(task, userId, nowIso())
      .run();
  }

  async clearCooldown(task: string, userId: number): Promise<void> {
    await this.db
      .prepare('DELETE FROM task_cooldowns WHERE task_name = ? AND user_id = ?')
      .bind(task, userId)
      .run();
  }

  // ---------- history ----------

  async addHistory(task: string, userId: number): Promise<number> {
    const res = await this.db
      .prepare('INSERT INTO task_history(task_name, user_id, done_at) VALUES (?, ?, ?)')
      .bind(task, userId, nowIso())
      .run();
    return Number(res.meta.last_row_id);
  }

  async deleteHistory(id: number): Promise<void> {
    await this.db.prepare('DELETE FROM task_history WHERE id = ?').bind(id).run();
  }

  async addVolunteerLog(task: string, userId: number): Promise<number> {
    const res = await this.db
      .prepare(
        'INSERT INTO task_volunteer_log(task_name, user_id, volunteered_at) VALUES (?, ?, ?)',
      )
      .bind(task, userId, nowIso())
      .run();
    return Number(res.meta.last_row_id);
  }

  async deleteLatestVolunteerLog(task: string, userId: number): Promise<void> {
    await this.db
      .prepare(
        `DELETE FROM task_volunteer_log WHERE id = (
           SELECT id FROM task_volunteer_log
           WHERE task_name = ? AND user_id = ?
           ORDER BY volunteered_at DESC, id DESC LIMIT 1
         )`,
      )
      .bind(task, userId)
      .run();
  }

  async taskHistory(task: string, limit: number) {
    const { results } = await this.db
      .prepare(
        `SELECT user_id, done_at FROM task_history
         WHERE task_name = ? ORDER BY done_at DESC LIMIT ?`,
      )
      .bind(task, limit)
      .all<{ user_id: number; done_at: string }>();
    return results;
  }

  async userHistory(userId: number, limit: number) {
    const { results } = await this.db
      .prepare(
        `SELECT task_name, done_at FROM task_history
         WHERE user_id = ? ORDER BY done_at DESC LIMIT ?`,
      )
      .bind(userId, limit)
      .all<{ task_name: string; done_at: string }>();
    return results;
  }

  async userTasks(userId: number): Promise<string[]> {
    const { results } = await this.db
      .prepare(
        `SELECT task_name FROM task_users
         WHERE user_id = ? AND active = 1 ORDER BY task_name`,
      )
      .bind(userId)
      .all<{ task_name: string }>();
    return results.map((r) => r.task_name);
  }

  async activitySince(iso: string): Promise<ActivityRow[]> {
    const { results } = await this.db
      .prepare(
        `SELECT task_name, user_id, done_at AS ts, 'COMPLETED' AS type
           FROM task_history WHERE done_at >= ?1
         UNION ALL
         SELECT task_name, user_id, volunteered_at AS ts, 'VOLUNTEER' AS type
           FROM task_volunteer_log WHERE volunteered_at >= ?1
         ORDER BY ts DESC`,
      )
      .bind(iso)
      .all<ActivityRow>();
    return results;
  }

  /** Prunes every table the bot presents as a rolling window. */
  async prune(beforeIso: string): Promise<void> {
    await this.db.batch([
      this.db.prepare('DELETE FROM task_history WHERE done_at < ?').bind(beforeIso),
      this.db
        .prepare('DELETE FROM task_volunteer_log WHERE volunteered_at < ?')
        .bind(beforeIso),
      this.db.prepare('DELETE FROM task_actions WHERE created_at < ?').bind(beforeIso),
    ]);
  }

  // ---------- undo ----------

  async logAction(a: Omit<ActionRow, 'id' | 'created_at'>): Promise<void> {
    await this.db
      .prepare(
        `INSERT INTO task_actions(
           task_name, user_id, action_type, chat_id, message_id, created_at,
           prev_cursor, consumed_credits, target_rowid)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      )
      .bind(
        a.task_name,
        a.user_id,
        a.action_type,
        a.chat_id,
        a.message_id,
        nowIso(),
        a.prev_cursor,
        a.consumed_credits,
        a.target_rowid,
      )
      .run();
  }

  async actionByMessage(chatId: number, messageId: number): Promise<ActionRow | null> {
    return await this.db
      .prepare('SELECT * FROM task_actions WHERE chat_id = ? AND message_id = ?')
      .bind(chatId, messageId)
      .first<ActionRow>();
  }

  async deleteAction(id: number): Promise<void> {
    await this.db.prepare('DELETE FROM task_actions WHERE id = ?').bind(id).run();
  }

  // ---------- cached display names ----------

  async cacheName(userId: number, name: string): Promise<void> {
    await this.db
      .prepare(
        `INSERT INTO user_names(user_id, name, updated_at) VALUES (?, ?, ?)
         ON CONFLICT(user_id) DO UPDATE SET name = excluded.name, updated_at = excluded.updated_at`,
      )
      .bind(userId, name, nowIso())
      .run();
  }

  async cachedName(userId: number): Promise<string | null> {
    const row = await this.db
      .prepare('SELECT name FROM user_names WHERE user_id = ?')
      .bind(userId)
      .first<{ name: string }>();
    return row?.name ?? null;
  }
}
