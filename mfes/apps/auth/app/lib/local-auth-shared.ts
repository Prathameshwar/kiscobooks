/**
 * Pure helpers and fixed user messages for the local sign-in provider, shared by the browser
 * forms and the BFF routes (docs/local-auth.md §4). No I/O, no secrets, no environment.
 *
 * Every message a person reads is defined here and chosen by status or code. Upstream error
 * text is never forwarded or displayed, so Identity cannot leak detail through this app.
 */

/** An opaque 256-bit identifier (authorization request id, recovery token): base64url or hex. */
const OPAQUE = /^[A-Za-z0-9_-]{16,256}$/;
export function validOpaqueToken(value: unknown): value is string {
  return typeof value === 'string' && OPAQUE.test(value);
}

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
export function normalizedEmail(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const email = value.trim().toLowerCase();
  return email.length <= 254 && EMAIL.test(email) ? email : null;
}

/** Sign-in also accepts generated administrator usernames, which signup reserves. */
export function normalizedLogin(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const identifier = value.trim().toLowerCase();
  if (/[\x00-\x1f\x7f]/.test(identifier)) return null;
  return identifier.includes('@') ? normalizedEmail(identifier)
    : /^[a-z0-9][a-z0-9._-]{2,63}$/.test(identifier) ? identifier : null;
}

export const CALLBACK_PATH_PREFIX = '/api/auth/callback/';

/**
 * Where Identity may send the browser after a successful sign-in: this app's own NextAuth
 * callback and nowhere else. Anything else (another origin, another path, credentials, a
 * relative or scripted URL) is refused, so a compromised or confused upstream cannot turn the
 * sign-in form into an open redirect.
 */
export function callbackTarget(value: unknown, appOrigin: string): string | null {
  if (typeof value !== 'string' || value.length > 4096) return null;
  try {
    const target = new URL(value);
    if (target.origin !== appOrigin || target.username || target.password || target.hash ||
        !target.pathname.startsWith(CALLBACK_PATH_PREFIX)) return null;
    return target.href;
  } catch { return null; }
}

export const MESSAGES = {
  badCredentials: 'Username, email or password is incorrect.',
  pending: 'Your account is waiting for administrator approval. You can sign in once it has been approved.',
  disabled: 'This account cannot sign in. Contact your administrator.',
  expiredRequest: 'This sign-in request has expired. Start again.',
  tooMany: 'Too many attempts. Please wait a few minutes and try again.',
  unavailable: 'Sign in is temporarily unavailable. Please try again.',
  loginInput: 'Enter your username or email address and password.',
  notAllowed: 'Request is not allowed.',
  recoveryInvalid: 'This recovery link is invalid or has expired. Ask your administrator for a new one.',
  recoveryUnavailable: 'Password recovery is temporarily unavailable. Please try again.',
  recoveryRejected: 'This password cannot be used. Check the length and that both entries match.',
  currentPasswordWrong: 'Your current password is incorrect.',
  newPasswordRejected: 'Choose a different password. This one cannot be used.',
  changeUnavailable: 'Password change is temporarily unavailable. Please try again.',
  sessionEnded: 'Your session has ended. Sign in again before changing your password.',
} as const;

/** "Locked for N minutes", from Identity's `retry_after` (seconds). Null when unusable. */
export function lockoutMinutes(retryAfterSeconds: unknown): number | null {
  if (typeof retryAfterSeconds !== 'number' || !Number.isFinite(retryAfterSeconds) || retryAfterSeconds <= 0) return null;
  return Math.min(1440, Math.max(1, Math.ceil(retryAfterSeconds / 60)));
}

/** The minutes our own BFF reports back to the browser: a whole number of minutes, or nothing. */
export function validMinutes(value: unknown): number | null {
  return typeof value === 'number' && Number.isInteger(value) && value >= 1 && value <= 1440 ? value : null;
}

export function lockedMessage(minutes: number | null): string {
  if (minutes === null) return 'This account is temporarily locked after too many failed attempts. Please try again later.';
  return `This account is temporarily locked after too many failed attempts. Try again in ${minutes} minute${minutes === 1 ? '' : 's'}.`;
}
