/** Setup capability is encrypted, HttpOnly and independent of the Authentik session cookie. */
import { createHash, timingSafeEqual } from 'node:crypto';
import { encode, decode } from 'next-auth/jwt';
import { NextRequest } from 'next/server';
import type { components } from '@janso/api-client/identity';

export type SetupDraft = components['schemas']['SetupRequest'];
export const setupCookie = 'janso-platform-setup';
const digest = (value: string) => createHash('sha256').update(value).digest('hex');
const attempts = new Map<string, { until: number; count: number }>();

export function allowSetupAttempt(identity: string, limit = 20): boolean {
  const now = Date.now();
  for (const [key, record] of attempts) if (record.until <= now) attempts.delete(key);
  if (attempts.size > 4096) return false;
  const key = digest(identity);
  const record = attempts.get(key) ?? { until: now + 60_000, count: 0 };
  record.count++;
  attempts.set(key, record);
  return record.count <= limit;
}

export function setupConfiguration() {
  const key = process.env.IDENTITY_SETUP_KEY;
  const secret = process.env.NEXTAUTH_SECRET;
  const identityUrl = process.env.IDENTITY_URL;
  const authUrl = process.env.NEXTAUTH_URL;
  const consoleUrl = process.env.CONSOLE_URL;
  if (!key || key.length < 32 || key.length > 128 || !secret || !identityUrl || !authUrl || !consoleUrl) throw new Error('Setup unavailable');
  for (const value of [identityUrl, authUrl, consoleUrl]) {
    const url = new URL(value);
    if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password || url.search || url.hash ||
        url.port === '0' || url.pathname !== '/' || /\s/.test(value) ||
        (url.protocol === 'http:' && !['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)))
      throw new Error('Invalid setup endpoint');
  }
  return { key, secret: digest(`${secret}:platform-setup`), identityUrl, authUrl, consoleUrl };
}

export function correctSetupKey(value: unknown, expected: string): boolean {
  return typeof value === 'string' && value.length >= 32 && value.length <= 128 &&
    timingSafeEqual(Buffer.from(digest(value)), Buffer.from(digest(expected)));
}

export async function readSetup(request: NextRequest): Promise<{ draft?: SetupDraft } | null> {
  const { key, secret } = setupConfiguration();
  const cookie = request.cookies.get(setupCookie)?.value;
  if (!cookie || cookie.length > 4096) return null;
  try {
    const value = await decode({ token: cookie, secret });
    if (value?.setup !== digest(key)) return null;
    if (value.draft !== undefined && !validDraft(value.draft)) return null;
    return { draft: value.draft as SetupDraft | undefined };
  } catch { return null; }
}

export async function setupCookieValue(draft?: SetupDraft): Promise<string> {
  const { key, secret } = setupConfiguration();
  return encode({ token: { setup: digest(key), ...(draft ? { draft } : {}) }, secret, maxAge: 1800 });
}

export function validDraft(value: unknown): value is SetupDraft {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const fields: Record<string, number> = { platform_name: 200, public_url: 2048, workspace_name: 200,
    workspace_slug: 63, administrator_name: 100, country_code: 2, currency_code: 3, timezone: 64 };
  const body = value as Record<string, unknown>;
  // Existing encrypted drafts may predate the language selector; the API defaults them to en.
  return Object.keys(body).every(key => key in fields || key === 'locale') &&
    (body.locale === undefined || typeof body.locale === 'string' && /^[a-z]{2}$/.test(body.locale)) && Object.entries(fields).every(([key, max]) =>
    typeof body[key] === 'string' && (body[key] as string).length <= max) &&
    Buffer.byteLength(JSON.stringify(body), 'utf8') <= 2200;
}
