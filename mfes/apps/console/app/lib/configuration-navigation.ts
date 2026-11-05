import { administrationResource, administrationReturn } from './administration-navigation';

/** Read destinations only, with bounded, independently checked parent navigation. */
export function configurationReturn(value: string | undefined, fallback: string,
  queryFor: (url: URL) => URLSearchParams | null, depth = 0): string {
  try {
    if (!value || !value.startsWith('/') || value.length > 4096 || depth > 6
      || /[\\#\x00-\x1f\x7f]/.test(value) || /%2f|%5c|%2e/i.test(value.split('?')[0]!)) return fallback;
    const url = new URL(value, 'https://console.invalid');
    if (url.origin !== 'https://console.invalid') return fallback;
    if (url.pathname === '/settings') return url.search ? fallback : '/settings';
    if (url.pathname === '/masters') return url.search ? fallback : '/masters';
    if (administrationResource(url.pathname) === 'companies'
      && !url.pathname.endsWith('/years') && !url.pathname.includes('/years/')) return administrationReturn('companies', value);
    const query = queryFor(url); if (!query) return fallback;
    query.delete('returnTo');
    for (const [key, entry] of query) if (/[\x00-\x1f\x7f]/.test(key + entry)) query.delete(key);
    if (url.searchParams.getAll('returnTo').length === 1) {
      const parent = configurationReturn(url.searchParams.get('returnTo')!, '', queryFor, depth + 1);
      if (parent && new URL(parent, url).pathname !== url.pathname) query.set('returnTo', parent);
    }
    return url.pathname + (query.size ? '?' + query : '');
  } catch { return fallback; }
}

/** The value has already passed its workflow's return validator. */
export function configurationTrail(back: string): string[] {
  const trail: string[] = [];
  for (let next: string | null = back; next && trail.length <= 6;) {
    if (trail.includes(next)) break;
    trail.push(next); next = new URL(next, 'https://console.invalid').searchParams.get('returnTo');
  }
  return trail;
}

/** The parent has been validated by the workflow; avoid duplicate or self-return links. */
export function configurationLink(path: string, back: string): string {
  const target = new URL(path, 'https://console.invalid'), parent = new URL(back, target);
  const origin = target.pathname === parent.pathname ? parent.searchParams.get('returnTo') : back;
  target.searchParams.delete('returnTo');
  if (origin) target.searchParams.set('returnTo', origin);
  return target.pathname + target.search;
}
