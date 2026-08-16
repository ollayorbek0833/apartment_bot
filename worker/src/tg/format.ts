/**
 * Everything the bot says, and the rules about duty names.
 *
 * Deliberately free of any grammY import so it can be unit-tested directly and
 * reused by the cron job without dragging the Telegram client along.
 */
import type { DutyService } from '../core/service';
import type { Repo } from '../db/repo';
import { localDateTime } from './time';

/** A duty is typed as a command, so its name must be a legal command. */
export const TASK_NAME_RE = /^[a-z0-9_]{1,32}$/;

/**
 * Names the bot already owns. A duty called "history" would be created happily
 * and then never reach the duty handler, because the command handler wins.
 */
export const RESERVED_NAMES = new Set([
  'add_task', 'add_user', 'remove_user', 'data',
  'now', 'history', 'my_tasks', 'help', 'help_admin',
  'show', 'start', 'cancel', 'tasks', 'credits', 'claim',
]);

export function editDistance(a: string, b: string): number {
  const prev = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i++) {
    let diagonal = prev[0];
    prev[0] = i;
    for (let j = 1; j <= b.length; j++) {
      const tmp = prev[j];
      prev[j] = Math.min(prev[j] + 1, prev[j - 1] + 1, diagonal + (a[i - 1] === b[j - 1] ? 0 : 1));
      diagonal = tmp;
    }
  }
  return prev[b.length];
}

/**
 * The nearest real duty to a mistyped one, or null if nothing is close.
 *
 * Silence for every unknown command is right — other bots live in the group.
 * But a near-miss is almost always a typo, and staying silent used to get the
 * typist blamed for skipping their turn the next morning.
 */
export function closestTask(name: string, tasks: string[]): string | null {
  let best: string | null = null;
  let bestScore = Infinity;
  for (const t of tasks) {
    const d = editDistance(name, t);
    if (d < bestScore) {
      bestScore = d;
      best = t;
    }
  }
  const allowed = Math.max(1, Math.floor(name.length / 4));
  return best !== null && bestScore <= allowed ? best : null;
}

export interface NameLookup {
  resolve(userId: number): Promise<string>;
}

export async function buildDigest(
  repo: Repo,
  duty: DutyService,
  names: NameLookup,
): Promise<string> {
  const tasks = await repo.allTasks();
  if (tasks.length === 0) return 'No tasks configured.';

  const lines = ['📍 Current Responsibilities'];
  for (const task of tasks) {
    const upcoming = await duty.preview(task, 1);
    if (upcoming.length === 0) {
      lines.push(`🔹 /${task}: no users`);
      continue;
    }
    // Leading slash so the duty is tappable straight from the announcement.
    lines.push(`🔹 /${task}: ${await names.resolve(upcoming[0])}`);
  }
  return lines.join('\n');
}

export function buildCsv(
  rows: { task_name: string; user_id: number; ts: string; type: string }[],
  names: Map<number, string>,
  timeZone: string,
): string {
  // Excel runs a leading =, +, - or @ as a formula, and display names are
  // user-controlled.
  const safe = (v: string) => {
    const s = String(v);
    const escaped = /^[=+\-@]/.test(s) ? `'${s}` : s;
    return /[",\n]/.test(escaped) ? `"${escaped.replace(/"/g, '""')}"` : escaped;
  };

  // Five headings, five values. The Python version wrote four headings and
  // three values, so the COMPLETED/VOLUNTEER column vanished and every field
  // landed under the wrong one.
  const out = ['date,time,task,user,type'];
  for (const row of rows) {
    const { date, time } = localDateTime(row.ts, timeZone);
    out.push(
      [
        date,
        time,
        safe(row.task_name),
        safe(names.get(row.user_id) ?? `User(${row.user_id})`),
        row.type,
      ].join(','),
    );
  }
  return out.join('\n');
}
