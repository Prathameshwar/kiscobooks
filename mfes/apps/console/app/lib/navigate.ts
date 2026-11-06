/**
 * Leaving the console.
 *
 * `auth` is a separate micro-frontend on its own origin in development, so the router cannot
 * take you there. Behind nginx both sit under one origin and this becomes a same-origin path,
 * which is why the target is configuration rather than a literal.
 *
 * Its own module so a test can replace it — asserting "we navigated" is otherwise a fight
 * with jsdom's read-only `location`.
 */

/** Where sign-in lives. The default is `pnpm dev:auth`. */
export function signInUrl(): string {
  const configured = process.env.NEXT_PUBLIC_AUTH_URL;
  if (typeof window === 'undefined') {
    const publicAuth = process.env.AUTH_URL;
    return configured ?? (publicAuth ? new URL('/login', publicAuth).href : 'http://localhost:4310/login');
  }
  // NEXT_PUBLIC values are frozen at build time. A production build without that value must
  // still use the auth app on the browser's public origin, never a developer's localhost.
  if (!['localhost', '127.0.0.1'].includes(window.location.hostname)) {
    if (!configured || /^https?:\/\/(?:localhost|127\.0\.0\.1)(?::\d+)?(?:\/|$)/i.test(configured)) return window.location.origin + '/login';
  }
  return configured ?? 'http://localhost:4310/login';
}

export function authActionUrl(path: '/logout' | '/api/session/refresh' | '/change-password'): string {
  return new URL(path, new URL(signInUrl(), window.location.href)).href;
}

/**
 * Where a company that demands a fresh sign-in is verified. Auth owns that flow — it holds the
 * provider session and writes the proof cookie — and returns the browser to the page it left,
 * which is why the current path travels with it (`apps/auth/app/step-up`).
 */
export function stepUpUrl(company: string): string {
  const destination = new URL('/step-up', new URL(signInUrl(), window.location.href));
  destination.searchParams.set('company', company);
  destination.searchParams.set('returnTo', window.location.pathname + window.location.search);
  return destination.href;
}

/**
 * Re-renders the current page against the new server context. A company switch changes the
 * permissions, the display config and every company-scoped read on the page, all of which are
 * resolved in Server Components — so the page is re-requested rather than patched in place.
 *
 * Its own function for `goTo`'s reason: asserting "we reloaded" is otherwise a fight with
 * jsdom's read-only `location`.
 */
export function reload(): void {
  window.location.reload();
}

export function goTo(url: string): void {
  window.location.assign(url);
}
