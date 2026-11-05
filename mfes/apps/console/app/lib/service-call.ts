'use client';

import { sessionFetch } from './session-fetch';

export type RequestFailure = { status: number; code?: string; message: string; fields?: Record<string, string> };

export type ServiceRequest = {
  /** Omitted for a boundary that serves one fixed service (the platform route). */
  service?: string;
  path: string;
  method?: string;
  body?: unknown;
  /**
   * The idempotency key. Named rather than positional on purpose: this is the parameter with
   * money consequences, and it used to sit in an unlabelled slot beside the body.
   */
  key?: string;
  signal?: AbortSignal;
};

export const replayableServiceRequest = (request: Pick<ServiceRequest, 'method' | 'key'>) =>
  (request.method ?? 'GET') === 'GET' || !!request.key;

/**
 * One browser-to-service call, through one of the console's own route handlers.
 *
 * The browser names a service, a method and a path — never a URL, never a token. The route's
 * allowlist decides whether that triple exists at all (`lib/service-proxy`).
 *
 * **The replay rule lives here, once.** A GET, or a write carrying an idempotency key, may be
 * retried after a token refresh; a keyless write may not, because a retried create is a second
 * company and a retried payment is a second payment (CLAUDE.md §6.2). Three copies of this
 * client previously disagreed about it, which is exactly how a double-charge ships.
 */
export async function serviceCall<T>(endpoint: string, request: ServiceRequest, subject: string): Promise<T> {
  const { service, path, method = 'GET', body, key, signal } = request;
  const response = await sessionFetch(
    endpoint,
    {
      method: 'POST',
      cache: 'no-store',
      signal,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...(service ? { service } : {}), path, method, ...(body ? { body } : {}), ...(key ? { key } : {}) }),
    },
    replayableServiceRequest(request),
  );
  const value = await response.json().catch(() => null);
  if (!response.ok) {
    throw {
      status: response.status,
      code: value?.error?.code,
      fields: value?.error?.fields,
      message: value?.error?.message ?? 'Unable to complete this request. Try again.',
    } satisfies RequestFailure;
  }
  if (!value || typeof value !== 'object') throw { status: 502, message: `Unexpected ${subject} response. Try again.` } satisfies RequestFailure;
  return value as T;
}

/** Whatever was thrown, as something a screen can render. */
export function requestFailure(value: unknown, subject = 'service'): RequestFailure {
  return value && typeof value === 'object' && 'status' in value
    ? (value as RequestFailure)
    : { status: 503, message: `The ${subject} is unavailable. Try again.` };
}
