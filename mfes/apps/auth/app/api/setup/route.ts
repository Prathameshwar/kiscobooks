import { getToken } from 'next-auth/jwt';
import { NextRequest, NextResponse } from 'next/server';
import { createClient } from 'redis';
import { validToken } from '../../lib/refresh-coordinator';
import { exactStrings, identityCall, readUpstream } from '../../lib/local-auth-server';
import { normalizedEmail } from '../../lib/local-auth-shared';
import { authProvider, providerEndpoints } from '../../lib/provider';
import { passwordAcceptable } from '../../lib/registration-input';
import { allowSetupAttempt, correctSetupKey, readSetup, setupConfiguration, setupCookie, setupCookieValue, validDraft } from '../../lib/setup-server';
import type { components } from '@janso/api-client/identity';

type Check = components['schemas']['SetupCheck'];
const reply = (value: unknown, status = 200) => NextResponse.json(value, { status,
  headers: { 'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer' } });
const failure = (status: number, message: string) => reply({ error: message }, status);

async function identity(path: string, accessToken?: string, body?: unknown) {
  const configuration = setupConfiguration();
  return fetch(new URL(`/v1/setup/${path}`, configuration.identityUrl), {
    method: body === undefined ? 'GET' : 'POST', cache: 'no-store', redirect: 'error',
    signal: AbortSignal.timeout(10_000), headers: { 'X-Setup-Key': configuration.key,
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
}

async function accessToken(request: NextRequest): Promise<string | null> {
  const token = await getToken({ req: request, secret: process.env.NEXTAUTH_SECRET,
    secureCookie: setupConfiguration().authUrl.startsWith('https://') });
  return token && validToken(token.accessToken) && typeof token.accessTokenExpires === 'number' &&
    Number.isFinite(token.accessTokenExpires) && token.accessTokenExpires > Date.now() + 10_000 ? token.accessToken : null;
}

/** Local provider only: Identity's own statement of whether a platform administrator exists. */
async function localStatus(): Promise<{ administratorExists: boolean }> {
  const response = await identityCall('status');
  const state = response.ok ? await response.json() : null;
  if (state?.provider !== 'local' || typeof state?.setup?.administrator_exists !== 'boolean') throw new Error('Local authentication unavailable');
  return { administratorExists: state.setup.administrator_exists };
}

async function authChecks(): Promise<Check[]> {
  const results: Check[] = [];
  let redis: ReturnType<typeof createClient> | undefined;
  try {
    if (!process.env.AUTH_REDIS_URL) throw new Error('Missing Redis');
    redis = createClient({ url: process.env.AUTH_REDIS_URL, RESP: 2,
      socket: { connectTimeout: 3000, reconnectStrategy: false } });
    redis.on('error', () => undefined);
    await redis.connect();
    await redis.ping();
    results.push({ name: 'Auth refresh coordination', status: 'ready', message: 'Redis connected' });
  } catch { results.push({ name: 'Auth refresh coordination', status: 'failed', message: 'Configure AUTH_REDIS_URL and start Redis.' }); }
  finally { if (redis?.isOpen) redis.destroy(); }
  const local = authProvider() === 'local';
  try {
    // Authentik keeps its https-only issuer rule; the local issuer may be loopback HTTP in
    // development. providerEndpoints() applies the rule for the configured provider.
    const endpoints = providerEndpoints();
    const response = await fetch(endpoints.wellKnown, {
      cache: 'no-store', redirect: 'error', signal: AbortSignal.timeout(5000) });
    const discovery = await response.json();
    if (!response.ok || discovery.issuer !== endpoints.issuer) throw new Error('Invalid issuer');
    results.push({ name: 'Auth provider configuration', status: 'ready', message: 'Discovery and issuer match' });
  } catch { results.push({ name: 'Auth provider configuration', status: 'failed', message: local
    ? 'Check the local sign-in settings (AUTH_LOCAL_*) and that Identity serves discovery.' : 'Check Authentik and Auth application configuration.' }); }
  if (local) {
    try { await localStatus(); results.push({ name: 'Local sign-in service', status: 'ready', message: 'Identity accepted the Auth application' }); }
    catch { results.push({ name: 'Local sign-in service', status: 'failed', message: 'Check IDENTITY_URL, AUTH_LOCAL_BFF_SECRET and IDENTITY_LOCAL_AUTH.' }); }
  }
  // Fixed server-administered allowlist. Browser input never controls connection probes.
  let targets: Record<string, string> = {};
  try { targets = JSON.parse(process.env.SETUP_SERVICE_URLS ?? '{}'); } catch { /* Report missing checks below. */ }
  const serviceChecks = await Promise.all(['Audit', 'Catalog', 'Accounting', 'Vouchers', 'Reports', 'Notification'].map(async (name): Promise<Check> => {
    try {
      const url = new URL(targets[name]);
      if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) throw new Error('Invalid URL');
      const response = await fetch(new URL('/health/ready', url), { cache: 'no-store', redirect: 'error', signal: AbortSignal.timeout(3000) });
      if (!response.ok || (await response.json()).status !== 'ready') throw new Error('Not ready');
      return { name: `${name} API`, status: 'ready', message: 'Ready' };
    } catch { return { name: `${name} API`, status: 'failed', message: `Start ${name} and check SETUP_SERVICE_URLS.` }; }
  }));
  return [...results, ...serviceChecks];
}

/**
 * Local provider, first run: create the platform administrator's credential through Identity
 * (docs/local-auth.md §4). Reached only after the setup capability cookie has been verified, so
 * the setup key is never taken from the browser here: the server presents its own configured key,
 * exactly as the other setup calls do, together with the BFF secret. The password is validated,
 * forwarded once and never stored, logged or echoed; Identity decides whether setup is still open.
 */
async function createAdministrator(body: Record<string, unknown>, setupKey: string) {
  if (authProvider() !== 'local') return failure(422, 'Unknown setup action.');
  if (!allowSetupAttempt('create-administrator', 10)) return failure(429, 'Too many attempts. Retry in a minute.');
  const email = normalizedEmail(body.email);
  const name = typeof body.name === 'string' ? body.name.trim() : '';
  const password = body.password;
  if (!exactStrings(body, ['action', 'name', 'email', 'password', 'password_repeat']) ||
      !name || Array.from(name).length > 100 || /[\x00-\x1f\x7f]/.test(name)) return failure(422, "Enter the administrator's full name (up to 100 characters).");
  if (!email) return failure(422, 'Enter a valid email address.');
  if (typeof password !== 'string' || !passwordAcceptable(password)) return failure(422, 'Use 6–128 characters for the password.');
  if (body.password_repeat !== password) return failure(422, 'The passwords do not match.');
  const response = await identityCall('setup/administrator', { method: 'POST', body: { name, email, password },
    headers: { 'X-Setup-Key': setupKey } });
  if (response.status === 201) return reply({ created: true }, 201);
  if (response.status === 403) return failure(403, 'Setup access is no longer valid. Unlock setup again.');
  if (response.status === 409) return failure(409, 'An administrator account already exists or setup is closed. Reload to check its status.');
  if (response.status === 422) {
    const upstream = await readUpstream(response);
    return failure(422, upstream.fields.includes('password') ? 'This password cannot be used. Choose another.'
      : upstream.fields.includes('email') ? 'This email address cannot be used.' : 'Check the administrator details.');
  }
  return failure(response.status === 429 ? 429 : 503, response.status === 429 ? 'Too many attempts. Retry in a minute.'
    : 'The administrator account could not be created. Check Identity and try again.');
}

export async function GET(request: NextRequest) {
  try {
    const action = request.nextUrl.searchParams.get('action') ?? 'status';
    if (action === 'checks' && !allowSetupAttempt('connection-checks', 30)) return failure(429, 'Too many connection checks. Retry in a minute.');
    if (action === 'status') {
      const response = await identity('status');
      if (!response.ok) return failure(503, 'Setup status is unavailable. Check Identity and its migrations.');
      const state = await response.json();
      const access = await readSetup(request);
      const local = authProvider() === 'local';
      let administratorExists: boolean | undefined;
      if (local && access && state.available === true) {
        // Only an unlocked caller learns whether an administrator account already exists.
        try { administratorExists = (await localStatus()).administratorExists; }
        catch { return failure(503, 'Local sign-in status is unavailable. Check Identity and the Auth application settings.'); }
      }
      return reply({ available: state.available === true, completed: state.completed === true,
        unlocked: !!access, ...(access && state.available ? { draft: access.draft,
          applicationUrl: setupConfiguration().consoleUrl } : {}),
        ...(local ? { provider: 'local', ...(administratorExists === undefined ? {} : { administratorExists }) } : {}) });
    }
    if (!await readSetup(request)) return failure(403, 'Unlock setup to continue.');
    if (action === 'checks') {
      const response = await identity('checks');
      if (!response.ok) return failure(response.status, 'Connection checks are unavailable.');
      const checks: components['schemas']['SetupChecks'] = await response.json();
      checks.checks.push(...await authChecks());
      checks.ready = checks.checks.every(check => check.status !== 'failed');
      return reply(checks);
    }
    if (action === 'administrator') {
      const token = await accessToken(request);
      const local = authProvider() === 'local';
      if (!token) return failure(401, local ? 'Sign in as the administrator to continue.' : 'Sign in through Authentik to continue.');
      const response = await identity('administrator', token);
      if (!response.ok) return failure(response.status, response.status === 403
        ? (local ? 'This account needs a verified email address. Ask an operator to verify it and sign in again.'
          : 'Your Authentik account needs a verified email address. Verify it in Authentik and sign in again.')
        : (local ? 'A fresh sign-in is required. Please sign in again.' : 'Fresh Authentik sign-in is required. Please sign in again.'));
      return reply(await response.json());
    }
    return failure(422, 'Unknown setup action.');
  } catch { return failure(503, 'Setup is unavailable. Check the configured services and try again.'); }
}

export async function POST(request: NextRequest) {
  try {
    const configuration = setupConfiguration();
    if (request.headers.get('origin') !== new URL(configuration.authUrl).origin)
      return failure(403, 'This request must come from the setup screen.');
    if (Number(request.headers.get('content-length') ?? 0) > 8192) return failure(413, 'Setup request is too large.');
    // Content-Length is optional and untrusted. Bound the stream before buffering or parsing.
    const reader = request.body?.getReader();
    const chunks: Uint8Array[] = [];
    let length = 0;
    if (reader) {
      try {
        while (true) {
          const chunk = await reader.read();
          if (chunk.done) break;
          length += chunk.value.byteLength;
          if (length > 8192) { await reader.cancel(); return failure(413, 'Setup request is too large.'); }
          chunks.push(chunk.value);
        }
      } finally { reader.releaseLock(); }
    }
    const raw = Buffer.concat(chunks).toString('utf8');
    let body;
    try { body = JSON.parse(raw); } catch { return failure(422, 'Invalid setup request.'); }
    if (!body || typeof body !== 'object' || Array.isArray(body)) return failure(422, 'Invalid setup request.');
    if (body.action === 'unlock') {
      // Global per worker: untrusted forwarding headers cannot bypass brute-force limits.
      if (!allowSetupAttempt('unlock', 20)) return failure(429, 'Too many setup attempts. Retry in a minute.');
      if (!correctSetupKey(body.key, configuration.key)) return failure(403, 'The setup key is incorrect.');
      const state = await identity('status');
      if (!state.ok) return failure(503, 'Identity is unavailable.');
      if (!(await state.json()).available) return failure(409, 'First-run setup is closed or has already completed.');
      const response = reply({ unlocked: true, applicationUrl: configuration.consoleUrl });
      response.cookies.set(setupCookie, await setupCookieValue(), { httpOnly: true, secure: configuration.authUrl.startsWith('https://'),
        sameSite: 'lax', path: '/api/setup', maxAge: 1800 });
      return response;
    }
    const access = await readSetup(request);
    if (!access) return failure(403, 'Setup access expired. Unlock setup again.');
    if (body.action === 'create-administrator') return await createAdministrator(body, configuration.key);
    if (!validDraft(body.draft)) return failure(422, 'Invalid setup details.');
    if (body.action === 'save') {
      const response = reply({ saved: true });
      response.cookies.set(setupCookie, await setupCookieValue(body.draft), { httpOnly: true,
        secure: configuration.authUrl.startsWith('https://'), sameSite: 'lax', path: '/api/setup', maxAge: 1800 });
      return response;
    }
    if (body.action !== 'complete') return failure(422, 'Unknown setup action.');
    if (!allowSetupAttempt('completion', 30)) return failure(429, 'Too many completion requests. Retry in a minute.');
    const token = await accessToken(request);
    if (!token) return failure(401, authProvider() === 'local' ? 'Sign in as the administrator again before completing setup.'
      : 'Sign in through Authentik again before completing setup.');
    const response = await identity('complete', token, body.draft);
    if (!response.ok) return failure(response.status, response.status === 409 ? 'Setup already completed or the installation changed. Reload to check its status.'
      : response.status === 422 ? 'Check country, currency, time zone and application URL.'
      : response.status === 401 ? 'Sign in again before completing setup.' : 'Setup could not complete. Verify your email and configured services.');
    const result = await response.json();
    const session = await fetch(new URL('/v1/session', configuration.identityUrl), { cache: 'no-store', redirect: 'error',
      signal: AbortSignal.timeout(5000), headers: { Authorization: `Bearer ${token}` } }).catch(() => null);
    const data = session?.ok ? await session.json().catch(() => null) : null;
    const verified = data?.permissions?.includes('platform.tenant.read') === true;
    return reply({ ...result, verified, destination: new URL('/platform', configuration.consoleUrl).href });
  } catch { return failure(503, 'Setup could not complete. Retry safely; completed records will be reused.'); }
}
