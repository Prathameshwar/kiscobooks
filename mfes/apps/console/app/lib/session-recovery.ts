import { headers } from 'next/headers';
import { redirect } from 'next/navigation';

/** Retry only within this console; never follow a caller's external URL. */
export function recoveryPath(value: unknown): string {
  if (typeof value !== 'string' || value.length > 3000 || !value.startsWith('/')) return '/';
  try {
    const decoded = decodeURIComponent(value);
    if (decoded.startsWith('//') || /[\\\x00-\x1f\x7f]/.test(decoded)) return '/';
    const url = new URL(value, 'https://console.invalid');
    const decodedUrl = new URL(decoded, 'https://console.invalid');
    if (url.origin !== 'https://console.invalid' || decodedUrl.origin !== url.origin ||
        /^\/(?:session-recovery|api|_next)(?:\/|$)/.test(decodedUrl.pathname)) return '/';
    return url.pathname + url.search;
  } catch { return '/'; }
}

/** No partial session or guessed money/display configuration escapes a failed read. */
export async function redirectSessionFailure(status: number): Promise<never> {
  const returnTo = recoveryPath((await headers()).get('x-janso-return-path'));
  const query = new URLSearchParams({ reason: status === 403 ? 'access' : 'unavailable', returnTo });
  redirect('/session-recovery?' + query);
}
