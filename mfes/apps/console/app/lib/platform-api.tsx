'use client';

import { Notice } from '@janso/ui';
import { requestFailure, serviceCall, type RequestFailure } from './service-call';
import { signInUrl } from './navigate';

export type PlatformFailure = RequestFailure;
/**
 * A platform-administration call. The envelope, the token preflight and the replay rule are
 * `lib/service-call`'s — this binds the route and the noun.
 *
 * `service: 'identity'` is explicit because the one proxy routes by service name; the platform
 * route's own allowlist still refuses every path outside `/v1/platform/`.
 */
export function platformCall<T>(path: string, method = 'GET', body?: unknown, key?: string, signal?: AbortSignal): Promise<T> {
  return serviceCall<T>('/api/platform', { service: 'identity', path, method, body, key, signal }, 'platform');
}
export function platformFailure(value: unknown): PlatformFailure {
  return requestFailure(value, 'platform service');
}
export function PlatformSignIn({ returnTo = '/platform/tenants', onNavigate }: { returnTo?: string; onNavigate?: () => void }) {
  const href = new URL(signInUrl()); href.searchParams.set('reauth', '1'); href.searchParams.set('returnTo', returnTo);
  return <a className="janso-link" href={href.href} onClick={onNavigate}>Sign in again</a>;
}
export function PlatformError({ value, returnTo, onNavigate }: { value: PlatformFailure | null; returnTo?: string; onNavigate?: () => void }) {
  if (!value) return null;
  return <Notice tone="danger">{value.message}{value.status === 401 || value.code === 'platform_reauthentication_required'
    ? <> <PlatformSignIn returnTo={returnTo} onNavigate={onNavigate} /></> : null}</Notice>;
}

/** Only the directory and its allowlisted list state can be a form's return destination. */
export function tenantReturnTo(value: string | null | undefined): string {
  if (!value || value.length > 3000 || !value.startsWith('/platform/tenants') || /[\\\r\n]/.test(value)) return '/platform/tenants';
  try {
    const url = new URL(value, 'https://console.invalid');
    if (url.origin !== 'https://console.invalid' || url.pathname !== '/platform/tenants' || url.hash ||
      [...url.searchParams.keys()].some(key => !['q', 'status', 'sort', 'limit', 'cursor'].includes(key))) return '/platform/tenants';
    return url.pathname + url.search;
  } catch { return '/platform/tenants'; }
}
