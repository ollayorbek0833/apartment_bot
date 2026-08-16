/**
 * Everything is stored in UTC and shown in the apartment's timezone.
 *
 * A duty done at 02:00 in Tashkent is 21:00 the previous day in UTC, and the
 * Python bot printed the UTC date — so the roster looked a day out.
 */
export function formatLocal(iso: string, timeZone: string, withTime = false): string {
  const d = new Date(iso);
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone,
    day: '2-digit',
    month: '2-digit',
    year: withTime ? 'numeric' : undefined,
    hour: withTime ? '2-digit' : undefined,
    minute: withTime ? '2-digit' : undefined,
    hour12: false,
  }).formatToParts(d);

  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? '';
  const date = withTime
    ? `${get('day')}.${get('month')}.${get('year')}`
    : `${get('day')}.${get('month')}`;
  return withTime ? `${date} ${get('hour')}:${get('minute')}` : date;
}

export function localDate(iso: string, timeZone: string): string {
  return formatLocal(iso, timeZone, false);
}

export function localDateTime(iso: string, timeZone: string): { date: string; time: string } {
  const full = formatLocal(iso, timeZone, true);
  const [date, time] = full.split(' ');
  return { date, time };
}

export function daysAgoIso(days: number): string {
  return new Date(Date.now() - days * 86_400_000).toISOString();
}
