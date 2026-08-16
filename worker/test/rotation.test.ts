/**
 * The rotation rules, tested against the pure engine.
 *
 * Each block corresponds to a defect that was live in the Python bot, so a
 * regression here is a regression in the apartment.
 */
import { describe, expect, it } from 'vitest';

import { cursorAfter, nextTurn, simulate, startIndex, type RosterMember } from '../src/core/rotation';

const A = 101, B = 102, C = 103, D = 104;

function roster(...pairs: [number, number][]): RosterMember[] {
  return pairs.map(([user_id, position]) => ({ user_id, position }));
}

const ABC = roster([A, 0], [B, 1], [C, 2]);
const noCredits = () => new Map<number, number>();

describe('turn order', () => {
  it('runs in position order from the cursor', () => {
    expect(simulate(ABC, 0, noCredits(), 4)).toEqual([A, B, C, A]);
  });

  it('resumes from wherever the cursor points', () => {
    expect(simulate(ABC, 2, noCredits(), 3)).toEqual([C, A, B]);
  });

  it('returns nothing for an empty roster instead of throwing', () => {
    expect(simulate([], 0, noCredits(), 3)).toEqual([]);
    expect(nextTurn([], 0, noCredits())).toBeNull();
  });
});

describe('removing somebody never moves anybody else', () => {
  // The cursor used to be an index into the active list, so taking one person
  // out shifted every later index and silently handed the duty to the wrong
  // roommate — while the bot replied "rotation preserved".
  it('keeps the same person next when an earlier member leaves', () => {
    const after = roster([B, 1], [C, 2]);          // A removed, positions unchanged
    expect(simulate(ABC, 1, noCredits(), 1)).toEqual([B]);
    expect(simulate(after, 1, noCredits(), 1)).toEqual([B]);
  });

  it('passes the turn forward when the person who was up leaves', () => {
    const after = roster([B, 1], [C, 2]);
    expect(simulate(ABC, 0, noCredits(), 1)).toEqual([A]);
    expect(simulate(after, 0, noCredits(), 1)).toEqual([B]);
  });

  it('wraps to the front when the cursor points past every survivor', () => {
    const after = roster([A, 0], [B, 1]);          // C removed
    expect(simulate(after, 2, noCredits(), 1)).toEqual([A]);
  });

  it('puts a returning member back in their original slot', () => {
    const without = roster([A, 0], [C, 2]);
    expect(simulate(without, 0, noCredits(), 3)).toEqual([A, C, A]);
    expect(simulate(ABC, 0, noCredits(), 3)).toEqual([A, B, C]);
  });
});

describe('skip credits', () => {
  it('passes over a credit holder and spends exactly one credit', () => {
    const credits = new Map([[A, 1]]);
    const turn = nextTurn(ABC, 0, credits)!;
    expect(turn.userId).toBe(B);
    expect(turn.skipped).toEqual([A]);
    expect(credits.get(A)).toBe(0);
  });

  it('passes over several in a row', () => {
    const credits = new Map([[A, 1], [B, 1]]);
    const turn = nextTurn(ABC, 0, credits)!;
    expect(turn.userId).toBe(C);
    expect(turn.skipped).toEqual([A, B]);
  });

  it('spends nothing when everybody holds one', () => {
    // Charging a credit to every single person and then still making one of
    // them do it is a tax, not a skip. The old walk lapped the roster and did
    // exactly that, destroying one credit per turn for nothing.
    const credits = new Map([[A, 1], [B, 1], [C, 1]]);
    const turn = nextTurn(ABC, 0, credits)!;
    expect(turn.userId).toBe(A);
    expect(turn.skipped).toEqual([]);
    expect([...credits.values()]).toEqual([1, 1, 1]);
  });

  it('never leaves a duty with nobody responsible', () => {
    // The worst bug the audit found: with the only zero-credit member removed
    // and everyone left holding two, the old scan budget ran out and the duty
    // reported "no users assigned" permanently, roster intact.
    const survivors = roster([B, 1], [C, 2], [D, 3]);
    const credits = new Map([[B, 2], [C, 2], [D, 2]]);
    expect(simulate(survivors, 0, credits, 1)).toEqual([B]);
    expect(simulate(survivors, 0, credits, 5)).toHaveLength(5);
  });
});

describe('the preview and the live engine agree', () => {
  it('predicts exactly the turns that then happen', () => {
    const ABCD = roster([A, 0], [B, 1], [C, 2], [D, 3]);
    const start = new Map([[B, 1], [D, 2]]);

    const predicted = simulate(ABCD, 0, start, 6);

    const live = new Map(start);
    let cursor = 0;
    const actual: number[] = [];
    for (let i = 0; i < 6; i++) {
      const turn = nextTurn(ABCD, cursor, live)!;
      actual.push(turn.userId);
      cursor = cursorAfter(ABCD, turn);
    }

    expect(actual).toEqual(predicted);
  });

  it('leaves the credit ledger untouched when previewing', () => {
    const credits = new Map([[A, 2]]);
    simulate(ABC, 0, credits, 5);
    expect(credits.get(A)).toBe(2);
  });
});

describe('startIndex', () => {
  it('lands on the member the cursor names', () => {
    expect(startIndex(ABC, 1)).toBe(1);
  });

  it('falls forward when that member is gone', () => {
    expect(startIndex(roster([B, 1], [C, 2]), 0)).toBe(0);
  });

  it('wraps when the cursor is past the end', () => {
    expect(startIndex(ABC, 99)).toBe(0);
  });
});
