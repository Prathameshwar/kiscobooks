/**
 * Server-only plumbing for the local sign-in provider's BFF routes (docs/local-auth.md §4).
 *
 * The Auth app server is the only caller of Identity's `/internal/v1/local-auth/*` surface and
 * proves it with `X-Auth-Bff-Secret`. This module is where that call is made, where browser
 * requests are held to the same hardening as `/api/registration`, and where an upstream answer is
 * reduced to a status, a code and a set of field names. Upstream text is never forwarded, and no
 * function here logs anything: request bodies carry passwords and recovery tokens.
 */
import { isIP } from 'node:net';
import { NextRequest, NextResponse } from 'next/server';
import { authOrigin, localBff } from './provider';
import { boundedJson } from './registration-server';

export const reply = (value: unknown, status = 200, headers: Record<string, string> = {}) => NextResponse.json(value, {
  status, headers: { 'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer', 'X-Content-Type-Options': 'nosniff', ...headers } });

export type Guarded = { ok: true; body: Record<string, unknown> } | { ok: false; response: NextResponse };

/**
 * A browser POST is accepted only from this app's own origin, as JSON, within `maximum` bytes.
 * Content-Length is advisory, so the stream itself is bounded as well. Throws on a bad
 * installation configuration; callers answer that with their generic 503.
 */
export async function guardedJson(request: NextRequest, maximum: number): Promise<Guarded> {
  const refuse = (status: number, error: string): Guarded => ({ ok: false, response: reply({ error }, status) });
  if (request.headers.get('origin') !== authOrigin() ||
      request.headers.get('sec-fetch-site') === 'cross-site') return refuse(403, 'Request is not allowed.');
  if (!/^application\/json(?:\s*;|$)/i.test(request.headers.get('content-type') ?? '')) return refuse(415, 'Send the request as JSON.');
  if (Number(request.headers.get('content-length') ?? 0) > maximum) return refuse(413, 'The request is too large.');
  let value: unknown;
  try { value = await boundedJson(new Response(request.body, { headers: request.headers }), maximum); }
  catch { return refuse(400, 'The request is invalid or too large.'); }
  if (!value || typeof value !== 'object' || Array.isArray(value)) return refuse(422, 'The request is invalid.');
  return { ok: true, body: value as Record<string, unknown> };
}

/** The body has exactly these string keys: no mass assignment, no missing field. */
export function exactStrings(body: Record<string, unknown>, keys: readonly string[]): boolean {
  return Object.keys(body).length === keys.length && keys.every(key => typeof body[key] === 'string');
}

/** How many reverse proxies in front of this app each append the address they saw (0–3; default 0). */
function trustedProxyHops(): number {
  const hops = Number(process.env.AUTH_TRUSTED_PROXY_HOPS ?? '0');
  return Number.isInteger(hops) && hops >= 1 && hops <= 3 ? hops : 0;
}

/**
 * The person's address, as far as a proxy this installation runs can vouch for it. `X-Forwarded-For`
 * is only believable at its *end*: each trusted proxy appends the address it received from, and every
 * earlier entry is whatever the client claimed. With `AUTH_TRUSTED_PROXY_HOPS=N` the entry N from the
 * end is the person. With none configured (the default, and the case when this app is reached
 * directly) no header can be believed, so none is used: a client could otherwise rotate its address
 * to dodge a limit, or borrow someone else's to spend their budget.
 *
 * Identity uses the value only to throttle, and trusts it only because this server proves itself with
 * the BFF secret. A missing value means "no per-address limit", never a shared one for every user.
 */
export function clientAddress(request: NextRequest): string | undefined {
  const hops = trustedProxyHops();
  if (!hops) return undefined;
  const chain = (request.headers.get('x-forwarded-for') ?? '').split(',').map(part => part.trim()).filter(Boolean);
  if (chain.length && chain.length < hops) return undefined;
  const candidate = chain.length ? chain[chain.length - hops] : request.headers.get('x-real-ip')?.trim();
  return candidate && isIP(candidate) ? candidate : undefined;
}

export async function identityCall(path: string, options: { method?: 'GET' | 'POST'; body?: unknown;
  headers?: Record<string, string>; clientAddress?: string } = {}): Promise<Response> {
  const { secret, identityUrl } = localBff();
  const method = options.method ?? (options.body === undefined ? 'GET' : 'POST');
  return fetch(new URL(`/internal/v1/local-auth/${path}`, identityUrl), {
    method, cache: 'no-store', redirect: 'error', signal: AbortSignal.timeout(8000),
    headers: { Accept: 'application/json', 'X-Auth-Bff-Secret': secret,
      ...(options.body === undefined ? {} : { 'Content-Type': 'application/json' }),
      ...(options.clientAddress ? { 'X-Client-Address': options.clientAddress } : {}), ...options.headers },
    ...(options.body === undefined ? {} : { body: JSON.stringify(options.body) }),
  });
}

export type Upstream = { code: string | null; fields: string[]; retryAfter: number | null };

/**
 * Reads only what the platform error envelope is allowed to tell us: a machine code, the names
 * of fields in error and a lockout delay. Messages are discarded unread. Unparseable or
 * oversized bodies yield an empty result, which every caller treats as "unavailable".
 */
export async function readUpstream(response: Response): Promise<Upstream> {
  const empty: Upstream = { code: null, fields: [], retryAfter: null };
  try {
    const value = await boundedJson(response, 8192);
    if (!value || typeof value !== 'object') return empty;
    const top = value as Record<string, unknown>;
    const envelope = top.error && typeof top.error === 'object' ? top.error as Record<string, unknown> : {};
    const code = typeof envelope.code === 'string' && /^[a-z0-9_]{1,64}$/.test(envelope.code) ? envelope.code : null;
    const source = [envelope.fields, top.fields].find(candidate => candidate && typeof candidate === 'object' && !Array.isArray(candidate));
    const fields = source ? Object.keys(source as object).filter(key => /^[a-z_]{1,64}$/.test(key)) : [];
    const delay = [envelope.retry_after, top.retry_after, Number(response.headers.get('retry-after'))]
      .find(candidate => typeof candidate === 'number' && Number.isFinite(candidate) && candidate > 0);
    return { code, fields, retryAfter: typeof delay === 'number' ? delay : null };
  } catch { return empty; }
}
