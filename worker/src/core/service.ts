/**
 * The rules, one level above SQL and one level below Telegram.
 *
 * Handlers call these; the tests call these. Nothing in here knows what a
 * Telegram message looks like.
 */
import { Repo } from '../db/repo';
import { cursorAfter, nextTurn, simulate, type RosterMember } from './rotation';

export interface TakenTurn {
  /** Whose turn was consumed. For a cover this is the person who was up. */
  turnOwner: number;
  /** Cursor value before the turn, so /cancel can put it back exactly. */
  prevCursor: number;
  /** Users whose skip credit paid for being passed over. */
  consumed: number[];
}

export class DutyService {
  constructor(private repo: Repo) {}

  /** Read-only: the next `steps` people, changing nothing. */
  async preview(task: string, steps: number): Promise<number[]> {
    const roster = await this.repo.roster(task);
    if (roster.length === 0) return [];
    return simulate(roster, await this.repo.cursor(task), await this.repo.credits(task), steps);
  }

  /**
   * Advance the rotation for real. Returns null when the roster is empty.
   *
   * Deliberately not a transaction: D1 has no interactive transactions, and
   * this is a five-person flat where two people cannot plausibly complete the
   * same duty in the same millisecond. The cooldown makes a double-tap a no-op.
   */
  async takeTurn(task: string): Promise<TakenTurn | null> {
    const roster = await this.repo.roster(task);
    if (roster.length === 0) return null;

    const prevCursor = await this.repo.cursor(task);
    const credits = await this.repo.credits(task);
    const turn = nextTurn(roster, prevCursor, credits);
    if (!turn) return null;

    await this.repo.spendCredits(task, turn.skipped);
    await this.repo.setCursor(task, cursorAfter(roster, turn));

    return { turnOwner: turn.userId, prevCursor, consumed: turn.skipped };
  }

  /** Put a taken turn back exactly as it was. */
  async undoTurn(task: string, prevCursor: number | null, consumed: number[]): Promise<void> {
    if (prevCursor !== null) await this.repo.setCursor(task, prevCursor);
    await this.repo.refundCredits(task, consumed);
  }

  async rosterOf(task: string): Promise<RosterMember[]> {
    return this.repo.roster(task);
  }
}
