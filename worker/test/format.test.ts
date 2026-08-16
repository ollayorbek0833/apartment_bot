/**
 * Duty-name rules and the typo suggestion.
 */
import { describe, expect, it } from 'vitest';

import { RESERVED_NAMES, TASK_NAME_RE, closestTask } from '../src/tg/format';

function acceptable(name: string): boolean {
  return TASK_NAME_RE.test(name) && !RESERVED_NAMES.has(name);
}

describe('duty names', () => {
  it('accepts what can actually be typed as a command', () => {
    for (const good of ['oshxona', 'cook', 'hammom_2', 'a', 'x'.repeat(32)]) {
      expect(acceptable(good), good).toBe(true);
    }
  });

  it('rejects a name the bot already owns', () => {
    // /add_task history used to be accepted, creating a duty that /history
    // could never reach because the command handler always wins.
    for (const reserved of ['history', 'now', 'cancel', 'data', 'claim', 'credits']) {
      expect(acceptable(reserved), reserved).toBe(false);
    }
  });

  it('rejects a name that cannot be a command at all', () => {
    for (const bad of ['Kitchen', 'my task', 'oshxona!', '', 'x'.repeat(33), 'oshxona-2', 'ошхона']) {
      expect(acceptable(bad), bad).toBe(false);
    }
  });
});

describe('typo suggestions', () => {
  const tasks = ['oshxona', 'hammom', 'axlat'];

  it('catches a one-letter slip', () => {
    expect(closestTask('oshxna', tasks)).toBe('oshxona');
    expect(closestTask('hammon', tasks)).toBe('hammom');
  });

  it('stays silent for an unrelated command from another bot', () => {
    expect(closestTask('weather', tasks)).toBeNull();
    expect(closestTask('stats', tasks)).toBeNull();
  });

  it('has nothing to suggest when there are no duties', () => {
    expect(closestTask('oshxona', [])).toBeNull();
  });
});
