/**
 * Leaving this app.
 *
 * The console is a separate micro-frontend on its own origin in development, so `next/link`
 * and the router cannot take you there — they navigate within one app. Behind nginx the two
 * sit under a single origin and this becomes a same-origin path, which is why the target is
 * configuration rather than a literal.
 *
 * Kept in its own module so a test can replace it: asserting "we navigated" is otherwise a
 * fight with jsdom's read-only `location`.
 */

/** Where the console lives. Overridden per environment; the default is `pnpm dev:console`. */
export function consoleUrl(): string {
  return process.env.NEXT_PUBLIC_CONSOLE_URL ?? 'http://localhost:4320';
}

export function goTo(url: string): void {
  window.location.assign(url);
}
