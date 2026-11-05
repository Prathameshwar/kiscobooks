import { getToken } from 'next-auth/jwt';
import { NextRequest, NextResponse } from 'next/server';
import { boundedJson } from '../../lib/registration-server';
import { parseChoices, parseRegion, regionErrors } from '../../lib/registration-regions';

const reply = (value: unknown, status: number) => NextResponse.json(value, { status, headers: { 'Cache-Control': 'no-store' } });
async function forward(request: NextRequest, body?: unknown) {
  const secret = process.env.NEXTAUTH_SECRET, base = process.env.IDENTITY_URL, auth = process.env.NEXTAUTH_URL;
  if (!secret || !base || !auth) return reply({ error: { message: 'Workspace setup is unavailable.' } }, 503);
  const token = await getToken({ req: request, secret, secureCookie: auth.startsWith('https://') });
  if (!token || typeof token.accessToken !== 'string' || !token.accessToken || typeof token.accessTokenExpires !== 'number' ||
      !Number.isFinite(token.accessTokenExpires) || token.accessTokenExpires <= Date.now() + 10000) return reply({ error: { message: 'Sign in to continue workspace setup.' } }, 401);
  try {
    const response = await fetch(new URL(body === undefined ? '/v1/onboarding/status' : '/v1/onboarding/tenant', base), {
      method: body === undefined ? 'GET' : 'POST', cache: 'no-store', redirect: 'error', signal: AbortSignal.timeout(10000),
      headers: { Authorization: 'Bearer ' + token.accessToken, 'Content-Type': 'application/json' },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
    const value = await boundedJson(response, 2 * 1024 * 1024) as Record<string, unknown>;
    if (response.ok && body === undefined && value.linked === false && value.email_verified === true) {
      const choices = parseChoices(value.options), region = parseRegion(token.registrationRegion);
      if (choices && region && !Object.keys(regionErrors(region, choices)).length) value.registration_region = region;
    }
    return reply(value, response.status);
  } catch { return reply({ error: { message: 'Workspace setup is unavailable. Please try again.' } }, 503); }
}
export function GET(request: NextRequest) { return forward(request); }
export async function POST(request: NextRequest) {
  const origin = request.headers.get('origin');
  if (!origin || origin !== request.nextUrl.protocol + '//' + (request.headers.get('host') ?? request.nextUrl.host)) return reply({ error: { message: 'Invalid request origin.' } }, 403);
  if (!request.headers.get('content-type')?.startsWith('application/json')) return reply({ error: { message: 'JSON required.' } }, 415);
  let body;
  try { body = await boundedJson(new Response(request.body, { headers: request.headers }), 4096); }
  catch { return reply({ error: { message: 'Invalid workspace details.' } }, 422); }
  return forward(request, body);
}
