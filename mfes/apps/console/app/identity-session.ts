import { headers, cookies } from 'next/headers';
import { redirect } from 'next/navigation';
import { NextRequest } from 'next/server';
import { getToken } from 'next-auth/jwt';
import { randomUUID } from 'node:crypto';
import { companyInPath, serviceLabel, serviceOrigin, stepUpCookieName, type Service } from './lib/services';

/**
 * Server-side reads for a console page.
 *
 * One mechanism for every service: the token stays on the server, the step-up proof for the
 * company named in the path is attached, and an authentication failure sends the browser to
 * auth rather than rendering a page with a hole in it. Audit is the exception — it is read from
 * client components, which need a JSON error they can render, not a redirect.
 *
 * Where each service lives comes from `lib/services`, shared with the browser-facing proxy, so
 * the two cannot disagree about an origin or about which company a request is scoped to.
 */
async function serviceFetch(path: string, service: Service, method = 'GET'): Promise<Response> {
  const authUrl = process.env.AUTH_URL;
  const origin = serviceOrigin(service);
  const secret = process.env.NEXTAUTH_SECRET;
  // Audit is read from the browser, so it answers in JSON; the others redirect.
  const redirects = service !== 'audit';
  const unavailable = () => Response.json({ error: { code: 'service_unavailable', message: 'Session service is unavailable. Try again.' } },
    { status: 503, headers: { 'Cache-Control': 'no-store' } });
  if (!authUrl || !origin || !secret) return unavailable();
  if (!path.startsWith('/v1/') || path.includes('\\')) throw new Error(`Invalid ${serviceLabel(service)} path`);
  let request: NextRequest;
  try { new URL(origin); request = new NextRequest(authUrl, { headers: await headers() }); }
  catch { return unavailable(); }
  const hint = request.headers.get('x-janso-return-path');
  const returnTo = hint && hint.startsWith('/') && !hint.startsWith('//') && hint.length <= 3000 ? hint : null;
  const authDestination = (path: string) => {
    const destination = new URL(path, authUrl);
    if (returnTo) destination.searchParams.set('returnTo', returnTo);
    return destination.href;
  };
  const token = await getToken({ req: request, secret, secureCookie: authUrl.startsWith('https://') });
  if (!token || (typeof token.accessToken !== 'string' && !token.refreshToken)) {
    if (!redirects) return Response.json({ error: { code: 'authentication_required', message: 'Sign in again' } }, { status: 401 });
    redirect(authDestination('/login'));
  }
  if (typeof token.accessToken !== 'string' || !token.accessToken || typeof token.accessTokenExpires !== 'number' ||
      !Number.isFinite(token.accessTokenExpires) || Date.now() >= token.accessTokenExpires - 10_000) {
    if (!redirects) return Response.json({ error: { code: 'session_expired', message: 'Session expired' } },
      { status: 401, headers: { 'Cache-Control': 'no-store' } });
    redirect(authDestination('/refresh'));
  }
  const company = companyInPath(path);
  const proof = company ? (await cookies()).get(stepUpCookieName(company))?.value : undefined;
  let response: Response;
  // Concatenated, not resolved: a gateway origin carries a path prefix (`…:8090/accounting`)
  // that `new URL('/v1/…', origin)` would silently drop, sending the read to the gateway root.
  try { response = await fetch(new URL(origin + path), {
    method, cache: 'no-store', redirect: 'error', signal: AbortSignal.timeout(5000),
    headers: { Authorization: `Bearer ${token.accessToken}`, 'X-Trace-Id': randomUUID().replaceAll('-', ''), 'X-Request-Id': randomUUID(), ...(proof ? { 'X-Company-Step-Up': proof } : {}) },
  }); } catch { return unavailable(); }
  if (redirects && response.status === 401) redirect(authDestination('/login?error=SessionExpired'));
  if (redirects && response.status === 403 && company) {
    const error = await response.clone().json().catch(() => null);
    if (error?.error?.code === 'step_up_required') redirect(authDestination(`/step-up?company=${company}`));
  }
  return response;
}

export const identityFetch = (path: string): Promise<Response> => serviceFetch(path, 'identity');
export const auditFetch = (path: string, method = 'GET'): Promise<Response> => serviceFetch(path, 'audit', method);
export const accountingFetch = (path: string): Promise<Response> => serviceFetch(path, 'accounting');
