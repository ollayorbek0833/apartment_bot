/**
 * Whose turn is it?
 *
 * This file is pure: it takes a roster and a credit ledger and returns an
 * answer. Nothing here touches the database, which is what lets the read-only
 * preview (`/now`, `/show`) and the real thing run the identical code. In the
 * Python version those were two separate implementations and they drifted:
 * the preview would give up and report "no users" while the roster was intact.
 */

export interface RosterMember {
  /** Telegram user id. */
  user_id: number;
  /** Stable slot in the rotation. Never renumbered, so removals are harmless. */
  position: number;
}

export interface Turn {
  /** Index into the roster array that was passed in. */
  index: number;
  /** Whose turn it is. */
  userId: number;
  /** Users who held a skip credit and were passed over, one credit each. */
  skipped: number[];
}

/**
 * Where does the rotation resume?
 *
 * `cursor` is a position VALUE, not an array index. If the member it pointed at
 * has been removed, the turn passes to the next active member after them,
 * wrapping to the front. Storing an array index here is the bug that used to
 * hand the duty to the wrong person every time somebody moved out.
 */
export function startIndex(roster: RosterMember[], cursor: number): number {
  for (let i = 0; i < roster.length; i++) {
    if (roster[i].position >= cursor) return i;
  }
  return 0;
}

/**
 * The single definition of a turn. Mutates `credits` for the members it skips.
 */
export function nextTurn(
  roster: RosterMember[],
  cursor: number,
  credits: Map<number, number>,
): Turn | null {
  if (roster.length === 0) return null;

  let index = startIndex(roster, cursor);

  // If everybody holds a credit, nobody can be skipped onto anybody else.
  // Charging one from each and still making one of them do it is a tax, not a
  // skip, so the turn simply stands and no credit is spent.
  const everyoneHasCredit = roster.every((m) => (credits.get(m.user_id) ?? 0) > 0);
  if (everyoneHasCredit) {
    return { index, userId: roster[index].user_id, skipped: [] };
  }

  const skipped: number[] = [];
  for (let step = 0; step < roster.length; step++) {
    const member = roster[index % roster.length];
    const balance = credits.get(member.user_id) ?? 0;
    if (balance > 0) {
      credits.set(member.user_id, balance - 1);
      skipped.push(member.user_id);
      index += 1;
      continue;
    }
    break;
  }

  const finalIndex = index % roster.length;
  return { index: finalIndex, userId: roster[finalIndex].user_id, skipped };
}

/**
 * The next `steps` turns, changing nothing. Same walk as the live engine.
 */
export function simulate(
  roster: RosterMember[],
  cursor: number,
  credits: Map<number, number>,
  steps: number,
): number[] {
  if (roster.length === 0) return [];

  const scratch = new Map(credits);
  let position = cursor;
  const result: number[] = [];

  for (let i = 0; i < Math.max(0, steps); i++) {
    const turn = nextTurn(roster, position, scratch);
    if (!turn) break;
    result.push(turn.userId);
    position = roster[(turn.index + 1) % roster.length].position;
  }

  return result;
}

/** The cursor value to store once `turn` has been taken. */
export function cursorAfter(roster: RosterMember[], turn: Turn): number {
  return roster[(turn.index + 1) % roster.length].position;
}
