import { authActionUrl } from './navigate';

let refreshing: Promise<boolean> | undefined;
async function refresh(): Promise<boolean> {
  if (!refreshing) {
    refreshing = (async () => {
      try {
        const response = await fetch(authActionUrl('/api/session/refresh'), { method: 'POST',
          credentials: 'include', cache: 'no-store', redirect: 'error',
          headers: { 'Content-Type': 'application/json' }, signal: AbortSignal.timeout(15_000) });
        return response.ok && (await response.json()).authenticated === true;
      } catch { return false; }
    })().finally(() => { refreshing = undefined; });
  }
  return refreshing;
}

/** Retry only a local preflight expiry: permission/revocation failures never trigger refresh. */
export async function sessionFetch(input: RequestInfo | URL, init?: RequestInit,
  replaySafe = true): Promise<Response> {
  const retryInput = input instanceof Request ? input.clone() : input;
  const response = await fetch(input, init);
  if (response.status !== 401) return response;
  const value = await response.clone().json().catch(() => null);
  if (value?.error?.code !== 'session_expired' || init?.signal?.aborted) return response;
  if (!await refresh() || !replaySafe || init?.signal?.aborted) return response;
  return fetch(retryInput, init);
}
