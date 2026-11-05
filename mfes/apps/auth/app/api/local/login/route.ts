import { NextRequest } from 'next/server';
import { callbackTarget, lockedMessage, lockoutMinutes, MESSAGES, normalizedLogin, validOpaqueToken } from '../../../lib/local-auth-shared';
import { clientAddress, exactStrings, guardedJson, identityCall, readUpstream, reply } from '../../../lib/local-auth-server';
import { authOrigin, authProvider } from '../../../lib/provider';
import { boundedJson } from '../../../lib/registration-server';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const notFound = () => reply({ error: 'Not found.' }, 404);
const unavailable = () => reply({ error: MESSAGES.unavailable }, 503);

/**
 * Is this authorization request still open? Lets the sign-in page say "expired" before a person
 * types a password. Public intentionally: the request id is a 256-bit secret the caller already
 * holds, and the answer is only open-or-not.
 */
export async function GET(request: NextRequest) {
  try {
    if (authProvider() !== 'local') return notFound();
    if (request.headers.get('sec-fetch-site') === 'cross-site') return reply({ error: MESSAGES.notAllowed }, 403);
    const id = request.nextUrl.searchParams.get('request');
    if (!validOpaqueToken(id)) return reply({ valid: false, error: MESSAGES.expiredRequest }, 404);
    let response: Response;
    try { response = await identityCall(`requests/${encodeURIComponent(id)}`); } catch { return unavailable(); }
    if (response.status === 404) return reply({ valid: false, error: MESSAGES.expiredRequest }, 404);
    if (!response.ok) return unavailable();
    return reply({ valid: true });
  } catch { return unavailable(); }
}

/**
 * Password sign-in for an open OIDC authorization request. Public intentionally: it is the
 * sign-in itself. Unknown identifiers and wrong passwords have the same answer. Both identifiers
 * share an account throttle and lockout; this route adds the browser hardening.
 */
export async function POST(request: NextRequest) {
  try {
    if (authProvider() !== 'local') return notFound();
    const guarded = await guardedJson(request, 4096);
    if (!guarded.ok) return guarded.response;
    const { body } = guarded;
    // Keep the previous email field working while clients move to identifier; refuse both at once.
    const key = Object.hasOwn(body, 'identifier') ? 'identifier' : 'email';
    const identifier = normalizedLogin(body[key]);
    const password = body.password;
    if (!exactStrings(body, ['request_id', key, 'password']) || !validOpaqueToken(body.request_id) || !identifier ||
        typeof password !== 'string' || !password || password.length > 512) return reply({ error: MESSAGES.loginInput }, 422);
    let response: Response;
    try { response = await identityCall('login', { method: 'POST', clientAddress: clientAddress(request),
      body: { request_id: body.request_id, identifier, password } }); }
    catch { return unavailable(); }
    if (response.ok) {
      let target: string | null = null;
      try { target = callbackTarget(((await boundedJson(response, 4096)) as { redirect_to?: unknown })?.redirect_to, authOrigin()); }
      catch { /* An unreadable success is treated as unavailable below. */ }
      return target ? reply({ redirect_to: target }) : unavailable();
    }
    const upstream = await readUpstream(response);
    switch (response.status) {
      case 401: return reply({ error: MESSAGES.badCredentials, code: 'invalid_credentials' }, 401);
      case 403:
        if (upstream.code === 'account_pending') return reply({ error: MESSAGES.pending, code: 'account_pending' }, 403);
        if (upstream.code === 'account_disabled') return reply({ error: MESSAGES.disabled, code: 'account_disabled' }, 403);
        return unavailable();
      case 404: return reply({ error: MESSAGES.expiredRequest, code: 'request_expired' }, 404);
      case 423: {
        const minutes = lockoutMinutes(upstream.retryAfter);
        return reply({ error: lockedMessage(minutes), code: 'account_locked', ...(minutes ? { retry_after_minutes: minutes } : {}) }, 423);
      }
      case 429: return reply({ error: MESSAGES.tooMany, code: 'rate_limited' }, 429, { 'Retry-After': '60' });
      default: return unavailable();
    }
  } catch { return unavailable(); }
}
