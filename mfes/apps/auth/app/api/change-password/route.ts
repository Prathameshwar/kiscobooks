import { getToken } from 'next-auth/jwt';
import { NextRequest, NextResponse } from 'next/server';
import { MESSAGES } from '../../lib/local-auth-shared';
import { exactStrings, guardedJson, readUpstream } from '../../lib/local-auth-server';
import { authProvider, localBff } from '../../lib/provider';
import { passwordAcceptable } from '../../lib/registration-input';

const reply = (value: unknown, status = 200, headers: Record<string, string> = {}) => NextResponse.json(value, { status, headers: { 'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer', ...headers } });

/**
 * Local provider: change the signed-in user's own password through Identity
 * (`POST /v1/session/password`, docs/local-auth.md §4), authenticated by the session's access
 * token. The current password is verified by Identity, which rate limits it and counts failures
 * toward lockout. Neither password is logged or echoed.
 */
async function changeLocal(request: NextRequest, accessToken: string) {
  const guarded = await guardedJson(request, 4096);
  if (!guarded.ok) return guarded.response;
  const { body } = guarded;
  if (!exactStrings(body, ['current_password', 'new_password'])) return reply({ error: 'The request is invalid.' }, 422);
  const current = body.current_password as string, next = body.new_password as string;
  if (!current || current.length > 512) return reply({ error: MESSAGES.currentPasswordWrong, fields: { current_password: MESSAGES.currentPasswordWrong } }, 422);
  if (!passwordAcceptable(next)) return reply({ error: MESSAGES.newPasswordRejected, fields: { new_password: MESSAGES.newPasswordRejected } }, 422);
  const response = await fetch(new URL('/v1/session/password', localBff().identityUrl), {
    method: 'POST', cache: 'no-store', redirect: 'error', signal: AbortSignal.timeout(8000),
    headers: { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ current_password: current, new_password: next }),
  });
  if (response.status === 204) return reply({ changed: true });
  if (response.status === 401) return reply({ error: MESSAGES.sessionEnded }, 401);
  if (response.status === 429) return reply({ error: MESSAGES.tooMany }, 429, { 'Retry-After': '60' });
  if (response.status === 422) {
    const upstream = await readUpstream(response);
    const fields: Record<string, string> = {};
    if (upstream.fields.includes('current_password')) fields.current_password = MESSAGES.currentPasswordWrong;
    if (upstream.fields.includes('new_password')) fields.new_password = MESSAGES.newPasswordRejected;
    if (Object.keys(fields).length) return reply({ error: 'Please check the highlighted fields.', fields }, 422);
  }
  return reply({ error: MESSAGES.changeUnavailable }, 503);
}

// Authenticated self-service: no caller-selected account. Authentik mode only navigates to the
// provider's own flow; local mode changes the password in-app.
export async function POST(request: NextRequest) {
  try {
    const auth = new URL(process.env.NEXTAUTH_URL ?? '');
    if (request.headers.get('origin') !== auth.origin || request.headers.get('sec-fetch-site') === 'cross-site') return reply({ error: 'Request is not allowed.' }, 403);
    const secret = process.env.NEXTAUTH_SECRET;
    if (!secret) throw new Error('Configuration unavailable');
    const token = await getToken({ req: request, secret, secureCookie: auth.protocol === 'https:' });
    if (!token || typeof token.accessToken !== 'string' || !token.accessToken || typeof token.accessTokenExpires !== 'number' || !Number.isFinite(token.accessTokenExpires) || token.accessTokenExpires <= Date.now() + 10000) return reply({ error: 'Sign in again before changing your password.' }, 401);
    if (authProvider() === 'local') return await changeLocal(request, token.accessToken);
    const issuer = new URL(process.env.AUTHENTIK_ISSUER ?? '');
    if (issuer.protocol !== 'https:' || issuer.username || issuer.password || issuer.search || issuer.hash) throw new Error('Configuration unavailable');
    return reply({ destination: new URL('/if/flow/bill-password-change/', issuer.origin).href });
  } catch { return reply({ error: 'Password change is temporarily unavailable. Please try again.' }, 503); }
}
