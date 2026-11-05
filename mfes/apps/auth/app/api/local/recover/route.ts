import { NextRequest } from 'next/server';
import { MESSAGES, validOpaqueToken } from '../../../lib/local-auth-shared';
import { clientAddress, guardedJson, identityCall, readUpstream, reply } from '../../../lib/local-auth-server';
import { authProvider } from '../../../lib/provider';
import { passwordAcceptable } from '../../../lib/registration-input';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const unavailable = () => reply({ error: MESSAGES.recoveryUnavailable }, 503);
const invalid = () => reply({ valid: false, error: MESSAGES.recoveryInvalid }, 404);

/**
 * Operator-issued, single-use password recovery link (`/reset?token=…`, docs/local-auth.md §4).
 * Public intentionally: possession of the unguessable token is the credential. The token and
 * the new password are forwarded to Identity and nowhere else: never logged, never echoed back.
 */
export async function POST(request: NextRequest) {
  try {
    if (authProvider() !== 'local') return reply({ error: 'Not found.' }, 404);
    const guarded = await guardedJson(request, 4096);
    if (!guarded.ok) return guarded.response;
    const { body } = guarded;
    const keys = Object.keys(body).sort().join(',');
    if (body.action === 'inspect' && keys === 'action,token' && validOpaqueToken(body.token)) {
      let response: Response;
      try { response = await identityCall('password/recovery/inspect', { method: 'POST', clientAddress: clientAddress(request), body: { token: body.token } }); }
      catch { return unavailable(); }
      if (response.ok) return reply({ valid: true });
      if (response.status === 404) return invalid();
      return response.status === 429 ? reply({ error: MESSAGES.tooMany }, 429, { 'Retry-After': '60' }) : unavailable();
    }
    if (body.action === 'redeem' && keys === 'action,new_password,token' && validOpaqueToken(body.token) &&
        typeof body.new_password === 'string') {
      if (!passwordAcceptable(body.new_password)) return reply({ error: MESSAGES.recoveryRejected, fields: { new_password: MESSAGES.recoveryRejected } }, 422);
      let response: Response;
      try { response = await identityCall('password/recovery/redeem', { method: 'POST', clientAddress: clientAddress(request), body: { token: body.token, new_password: body.new_password } }); }
      catch { return unavailable(); }
      if (response.status === 204) return reply({ redeemed: true });
      if (response.status === 404) return invalid();
      if (response.status === 422) {
        const upstream = await readUpstream(response);
        return upstream.fields.includes('new_password')
          ? reply({ error: MESSAGES.recoveryRejected, fields: { new_password: MESSAGES.recoveryRejected } }, 422) : unavailable();
      }
      return response.status === 429 ? reply({ error: MESSAGES.tooMany }, 429, { 'Retry-After': '60' }) : unavailable();
    }
    return reply({ error: 'The request is invalid.' }, 422);
  } catch { return unavailable(); }
}
