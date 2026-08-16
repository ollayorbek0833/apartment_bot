import type { Api } from 'grammy';
import type { User } from 'grammy/types';
import type { Repo } from '../db/repo';

/** @username, else "First Last", else "First". */
export function formatUser(user: { username?: string; first_name?: string; last_name?: string }): string {
  if (user.username) return `@${user.username}`;
  if (user.first_name && user.last_name) return `${user.first_name} ${user.last_name}`;
  return user.first_name || 'Unknown user';
}

/**
 * Resolve display names without hammering Telegram.
 *
 * The Python bot called getChatMember once per row of the CSV export and once
 * per duty every morning. Names are cached in D1 and only fetched when missing,
 * and every fetch is remembered.
 */
export class NameResolver {
  private memo = new Map<number, string>();

  constructor(
    private api: Pick<Api, 'getChatMember'>,
    private repo: Repo,
    private chatId: number,
  ) {}

  /** Record a name we already have in hand, e.g. from the sender of a message. */
  async remember(user: User): Promise<string> {
    const name = formatUser(user);
    this.memo.set(user.id, name);
    await this.repo.cacheName(user.id, name);
    return name;
  }

  async resolve(userId: number): Promise<string> {
    const hit = this.memo.get(userId);
    if (hit) return hit;

    try {
      const member = await this.api.getChatMember(this.chatId, userId);
      const name = formatUser(member.user);
      this.memo.set(userId, name);
      await this.repo.cacheName(userId, name);
      return name;
    } catch {
      const cached = await this.repo.cachedName(userId);
      const name = cached ?? `User(${userId})`;
      this.memo.set(userId, name);
      return name;
    }
  }

  async resolveAll(userIds: number[]): Promise<Map<number, string>> {
    const unique = [...new Set(userIds)];
    const out = new Map<number, string>();
    for (const id of unique) out.set(id, await this.resolve(id));
    return out;
  }
}
