import { createClient } from 'redis';
import type { RegistrationInput, RegistrationErrors } from './registration-input';
import { authProvider, localBff, type ProviderId } from './provider';

export function registrationConfiguration() {
  if (process.env.AUTH_REGISTRATION_MODE !== 'manual-review') throw new Error('Registration unavailable');
  const provider: ProviderId = authProvider();
  // The Authentik flow executor needs the issuer; the local provider needs Identity's BFF
  // credentials instead and must not require any AUTHENTIK_* setting.
  const issuer = provider === 'authentik' ? new URL(process.env.AUTHENTIK_ISSUER ?? '') : null;
  if (provider === 'local') localBff();
  const auth = new URL(process.env.NEXTAUTH_URL ?? '');
  if ((issuer && (issuer.protocol !== 'https:' || issuer.username || issuer.password || issuer.search || issuer.hash)) ||
      !['http:', 'https:'].includes(auth.protocol) || auth.username || auth.password || auth.pathname !== '/' || auth.search || auth.hash ||
      (auth.protocol === 'http:' && !['localhost', '127.0.0.1', '[::1]'].includes(auth.hostname)) ||
      !/^rediss?:\/\//.test(process.env.AUTH_REDIS_URL ?? '')) throw new Error('Invalid registration configuration');
  return { provider, origin: auth.origin, endpoint: issuer ? new URL('/api/v3/flows/executor/bill-account-enrollment/', issuer.origin) : null, workspaceEnabled: process.env.AUTH_REGISTRATION_WORKSPACE_ENABLED === 'true',
    // A same-provider terminal URL passes Authentik's redirect allowlist. The BFF
    // recognizes completion and displays its own result; the browser never follows it.
    completeUrl: '/if/user/' };
}

// A global, distributed cap also protects direct development ports: forwarded client IPs
// are deliberately not trusted. Production ingress should add its per-IP nginx limit.
export async function allowRegistration(): Promise<boolean> {
  const client = createClient({ url: process.env.AUTH_REDIS_URL, RESP: 2, disableOfflineQueue: true,
    socket: { connectTimeout: 2000, reconnectStrategy: false } });
  client.on('error', () => { /* Never log a connection URL. */ });
  try {
    await client.connect();
    const count = await client.withCommandOptions({ timeout: 1000 }).eval(
      "local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],60) end; return n",
      { keys: ['janso:registration:minute'], arguments: [] });
    return typeof count === 'number' && count <= 20;
  } finally { if (client.isOpen) client.destroy(); }
}

export async function boundedJson(response: Response, maximum: number): Promise<unknown> {
  if (Number(response.headers.get('content-length') ?? 0) > maximum || !response.body) throw new Error('Invalid body');
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let length = 0;
  let timedOut = false;
  const timer = setTimeout(() => { timedOut = true; void reader.cancel(); }, 10_000);
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      length += value.byteLength;
      if (length > maximum) { await reader.cancel(); throw new Error('Invalid body'); }
      chunks.push(value);
    }
    if (timedOut) throw new Error('Body timed out');
    return JSON.parse(Buffer.concat(chunks).toString('utf8'));
  } finally { clearTimeout(timer); reader.releaseLock(); }
}

type Challenge = { component?: string; fields?: { field_key: string }[];
  response_errors?: Record<string, unknown>; final_redirect?: boolean; to?: string };
export async function enroll(input: RegistrationInput): Promise<{ errors?: RegistrationErrors; created: boolean }> {
  const configuration = registrationConfiguration();
  if (!configuration.endpoint) throw new Error('Registration is not served by this provider');
  const endpoint = new URL(configuration.endpoint);
  endpoint.searchParams.set('query', new URLSearchParams({ next: configuration.completeUrl }).toString());
  const options = { cache: 'no-store' as const, redirect: 'error' as const,
    signal: AbortSignal.timeout(15_000), headers: { Accept: 'application/json' } };
  // Start a separate anonymous provider session. Never forward the caller's cookies,
  // authorization headers, role flags or attributes to Authentik.
  const initial = await fetch(endpoint, options);
  if (!initial.ok) throw new Error('Provider unavailable');
  const challenge = await boundedJson(initial, 32768) as Challenge;
  const expected = ['name', 'username', 'email', 'password', 'password_repeat', 'country_code', 'state_code', ...(configuration.workspaceEnabled ? ['workspace_name'] : [])];
  if (challenge.component !== 'ak-stage-prompt' || challenge.fields?.length !== expected.length ||
      !expected.every(key => challenge.fields?.some(field => field.field_key === key))) throw new Error('Unexpected enrollment flow');
  const cookies = initial.headers.getSetCookie().map(cookie => cookie.split(';')[0]);
  if (!cookies.length || cookies.some(cookie => /[\r\n]/.test(cookie))) throw new Error('Invalid provider session');
  const csrf = cookies.find(cookie => cookie.startsWith('authentik_csrf='))?.split('=')[1];
  let result = await fetch(endpoint, { ...options, redirect: 'manual', method: 'POST', headers: { ...options.headers,
    'Content-Type': 'application/json', Cookie: cookies.join('; '), Referer: configuration.endpoint.origin,
    ...(csrf ? { 'X-CSRFToken': csrf } : {}) }, body: JSON.stringify(configuration.workspaceEnabled ? input : Object.fromEntries(Object.entries(input).filter(([key]) => key !== 'workspace_name'))) });
  // UserWrite and skipped handoff stages can each redirect to this executor.
  // Follow a bounded number of GETs to the identical URL; never resend a password.
  const jar = new Map(cookies.map(cookie => [cookie.slice(0, cookie.indexOf('=')), cookie]));
  for (let redirects=0; result.status === 302 && redirects < 5; redirects++) {
    if (new URL(result.headers.get('location') ?? '', endpoint).href !== endpoint.href) throw new Error('Unexpected provider redirect');
    for (const raw of result.headers.getSetCookie()) {
      const cookie = raw.split(';')[0];
      if (/[\r\n]/.test(cookie)) throw new Error('Invalid provider session');
      jar.set(cookie.slice(0, cookie.indexOf('=')), cookie);
    }
    result = await fetch(endpoint, { ...options, redirect:'manual', headers: { ...options.headers, Cookie: [...jar.values()].join('; ') } });
  }
  if (!result.ok) throw new Error('Provider unavailable');
  const next = await boundedJson(result, 32768) as Challenge;
  if (next.component === 'xak-flow-redirect' && next.final_redirect === true && next.to === configuration.completeUrl) return { created: true };
  if (next.component === 'ak-stage-prompt' && next.response_errors) {
    const errors: RegistrationErrors = {};
    for (const key of expected as (keyof RegistrationInput)[]) if (Object.hasOwn(next.response_errors, key)) {
      errors[key] = key === 'username' ? 'Choose another username. This one cannot be used.' :
        key.startsWith('password') ? 'Check your password and confirmation.' : 'Check this account detail.';
    }
    return { created: false, errors };
  }
  throw new Error('Unexpected enrollment result');
}
