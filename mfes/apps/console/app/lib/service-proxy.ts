import { getToken } from 'next-auth/jwt';
import { randomUUID } from 'node:crypto';
import { NextResponse, type NextRequest } from 'next/server';
import { readJsonBody } from './json-request';
import { isSameOrigin } from './request-origin';
import { companyInPath, stepUpCookieName } from './services';

export type ProxyRequest = { service: string; method: string; path: string; body?: unknown; key?: string };

export type ProxyOptions = {
  /** The route's own fixed allowlist. Anything it does not name is refused unread. */
  allow: (service: string, method: string, path: string) => boolean;
  /** Service name to configured origin. Returning nothing is a 503, never a guess. */
  base: (service: string) => string | undefined;
  /** Noun for the error envelope — "company setup", "product field", "platform". */
  subject: string;
  /** Fixed per boundary; ordinary Console requests retain the small default. */
  maximumBodyBytes?: number;
  upstreamTimeoutMs?: number | ((input: ProxyRequest) => number);
  /**
   * A chance to return the upstream response as something other than a JSON envelope: a CSV
   * export, a spreadsheet template. Returning `null` falls through to the envelope.
   */
  passthrough?: (response: Response, input: ProxyRequest) => Response | null;
};

/** The only fields a request envelope may carry. An unknown one is a refusal, not a shrug. */
const ENVELOPE = ['service', 'path', 'method', 'body', 'key'];

const reply = (value: unknown, status: number, upstream?: Response) =>
  NextResponse.json(value, { status, headers: {
    'Cache-Control': 'no-store',
    ...(upstream?.headers.get('x-trace-id') ? { 'X-Trace-Id': upstream.headers.get('x-trace-id')! } : {}),
    ...(upstream?.headers.get('x-request-id') ? { 'X-Request-Id': upstream.headers.get('x-request-id')! } : {}),
  } });

/**
 * The URL to request, but only when it is the allowlisted path under the service's configured
 * prefix — otherwise nothing, and the caller refuses.
 *
 * Both sides are compared after URL normalization, which is the only way the comparison means
 * anything: the parser resolves dot segments (including their encoded forms) and a literal
 * string check does not.
 */
function resolveTarget(base: string, path: string): URL | null {
  try {
    const target = new URL(base.replace(/\/$/, '') + path);
    const prefix = new URL(base).pathname.replace(/\/$/, '');
    // `https://proxy.invalid` is a parsing device: it normalizes the path with no prefix to
    // absorb, which is exactly what each allowlist validated.
    const approved = new URL('https://proxy.invalid' + path);
    return target.pathname === prefix + approved.pathname && target.search === approved.search ? target : null;
  } catch {
    return null;
  }
}

/**
 * The session preflight every server-side call to a service shares.
 *
 * A locally expired token is reported as `session_expired` so the client's own refresh can
 * replay the call; a missing one is `authentication_required`. Neither is inferred from a
 * service's answer — this is only the preflight, and the service still authorizes every
 * request it receives.
 */
export async function accessToken(request: NextRequest): Promise<{ token: string } | { error: NextResponse }> {
  const secret = process.env.NEXTAUTH_SECRET;
  const authUrl = process.env.AUTH_URL;
  if (!secret || !authUrl) return { error: reply({ error: { message: 'Session service is not configured' } }, 503) };
  const token = await getToken({ req: request, secret, secureCookie: authUrl.startsWith('https://') });
  if (
    typeof token?.accessToken !== 'string' ||
    !token.accessToken ||
    typeof token.accessTokenExpires !== 'number' ||
    !Number.isFinite(token.accessTokenExpires) ||
    Date.now() >= token.accessTokenExpires - 10000
  ) {
    return {
      error: reply(
        { error: { code: token ? 'session_expired' : 'authentication_required', message: 'Your session needs to be refreshed' } },
        401,
      ),
    };
  }
  return { token: token.accessToken };
}

/**
 * The browser-to-service boundary every console screen writes through.
 *
 * The browser never holds the access token and never names a URL: it sends a service name, a
 * method and a path, and the route's allowlist decides whether that triple exists at all. The
 * token is attached here, server-side, which is the only reason this indirection exists.
 *
 * Shared because three routes need it, and three copies of a token-attaching proxy is how one
 * of them ends up without the origin check (CLAUDE.md §3). What stays per route is the
 * **policy**: the allowlist and the service-to-origin map.
 *
 * Paths are concatenated onto the configured base rather than resolved as URLs, because a
 * gateway origin carries a path prefix (`…:8090/accounting`) that `new URL('/v1/…', base)`
 * would silently drop — sending a company request to the gateway root.
 */
export async function proxyServiceRequest(request: NextRequest, options: ProxyOptions): Promise<Response> {
  if (!isSameOrigin(request)) return reply({ error: { message: 'Invalid request origin' } }, 403);
  // Authenticate before reading the body: a route that takes a large body (a Purchase carries up to 320 KiB)
  // must not buffer it for a caller who is not signed in.
  const session = await accessToken(request);
  if ('error' in session) return session.error;
  const read = await readJsonBody(request, options.maximumBodyBytes);
  if ('error' in read) return read.error;
  const input = read.value;
  if (
    typeof input.service !== 'string' ||
    typeof input.method !== 'string' ||
    typeof input.path !== 'string' ||
    input.path.length > 3000 ||
    Object.keys(input).some((key) => !ENVELOPE.includes(key)) ||
    (input.key !== undefined && (typeof input.key !== 'string' || !/^[a-zA-Z0-9_-]{1,128}$/.test(input.key))) ||
    !options.allow(input.service, input.method, input.path)
  ) {
    return reply({ error: { message: `Unsupported ${options.subject} request` } }, 422);
  }
  const proxied = input as ProxyRequest;
  const base = options.base(proxied.service);
  if (!base) return reply({ error: { message: `${options.subject} service is not configured` } }, 503);
  /*
   * The allowlists validate a path against a bare origin; a gateway base carries a service
   * prefix (`…:8090/accounting`). Those two can disagree: `%2e%2e` is a dot segment to the URL
   * parser but not to a literal `'..'` check, so a surplus one is absorbed at the root during
   * validation and pops the prefix during the request — an authenticated call to a path the
   * allowlist never approved. Confirming the resolved URL *is* the approved route under the
   * configured prefix states that invariant once, here, for all three routes.
   */
  const target = resolveTarget(base, proxied.path);
  if (!target) return reply({ error: { message: `Unsupported ${options.subject} request` } }, 422);
  // A company-scoped request carries whatever step-up proof the browser holds for that company.
  // Identity verifies its own proof; this only forwards it.
  const company = companyInPath(proxied.path, proxied.body);
  const proof = company ? request.cookies.get(stepUpCookieName(company))?.value : undefined;
  try {
    // The compared URL, not a second concatenation of the same parts.
    const response = await fetch(target.href, {
      method: proxied.method,
      cache: 'no-store',
      redirect: 'error',
      signal: AbortSignal.timeout(typeof options.upstreamTimeoutMs === 'function'
        ? options.upstreamTimeoutMs(proxied) : options.upstreamTimeoutMs ?? 15000),
      headers: {
        Authorization: 'Bearer ' + session.token,
        'X-Trace-Id': randomUUID().replaceAll('-', ''),
        'X-Request-Id': randomUUID(),
        'Content-Type': 'application/json',
        ...(proof ? { 'X-Company-Step-Up': proof } : {}),
        ...(proxied.key ? { 'Idempotency-Key': proxied.key } : {}),
      },
      ...(proxied.method === 'GET' ? {} : { body: JSON.stringify(proxied.body ?? {}) }),
    });
    const passed = options.passthrough?.(response, proxied) ?? null;
    if (passed) return passed;
    if (response.status === 204) return reply({ ok: true }, 200);
    let value: unknown;
    try { value = await response.json(); }
    catch {
      return reply({ error: { message: 'Unexpected service response' } }, response.ok ? 502 : response.status, response);
    }
    return reply(value, response.status, response);
  } catch {
    return reply({ error: { message: `${options.subject} service is unavailable. Retry the same action.` } }, 503);
  }
}
