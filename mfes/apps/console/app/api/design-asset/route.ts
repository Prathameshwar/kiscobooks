import { getToken } from 'next-auth/jwt';
import { NextRequest, NextResponse } from 'next/server';
import { serviceOrigin, stepUpCookieName } from '../../lib/services';

const uuid = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
const media = new Set(['image/png', 'image/jpeg', 'image/webp']);

const failure = (status: number, message: string) =>
  NextResponse.json({ error: { message } }, { status, headers: { 'Cache-Control': 'no-store' } });

/**
 * A brand asset's bytes, for `<img src>` in the designer's own browser preview (plan
 * P4, 2026-11-03).
 *
 * `<img>` issues a plain `GET` with no body, so this cannot go through the console's
 * tunnelling JSON proxy (`lib/service-proxy.ts`), which reads its target from a POSTed
 * envelope — the same reason `report-download` has its own route. The token is minted
 * by Design itself (`AssetDetail.download_token`, signed and expiring) and only ever
 * named here, never the asset's storage path.
 */
export async function GET(request: NextRequest) {
  if (request.headers.get('sec-fetch-site') === 'cross-site') return failure(403, 'Invalid request origin');
  const params = request.nextUrl.searchParams;
  const entries = [...params.keys()];
  const company = params.get('company');
  const asset = params.get('asset');
  const token = params.get('token');
  if (
    entries.length !== 3 ||
    new Set(entries).size !== 3 ||
    !company || !uuid.test(company) ||
    !asset || !uuid.test(asset) ||
    !token || token.length > 4096 || !/^[a-zA-Z0-9_-]+$/.test(token)
  ) {
    return failure(422, 'Select a valid asset to view');
  }
  const secret = process.env.NEXTAUTH_SECRET;
  const authUrl = process.env.AUTH_URL;
  if (!secret || !authUrl) return failure(503, 'Session service is not configured');
  const session = await getToken({ req: request, secret, secureCookie: authUrl.startsWith('https://') });
  if (
    typeof session?.accessToken !== 'string' || !session.accessToken ||
    typeof session.accessTokenExpires !== 'number' || !Number.isFinite(session.accessTokenExpires) ||
    Date.now() >= session.accessTokenExpires - 10000
  ) {
    return failure(401, 'Sign in to view this asset');
  }
  const base = serviceOrigin('design');
  if (!base) return failure(503, 'Design service is not configured');
  const proof = request.cookies.get(stepUpCookieName(company))?.value;
  try {
    const response = await fetch(
      `${base}/v1/companies/${company}/assets/${asset}/download?token=${encodeURIComponent(token)}`,
      {
        headers: {
          Authorization: 'Bearer ' + session.accessToken,
          ...(proof ? { 'X-Company-Step-Up': proof } : {}),
        },
        cache: 'no-store',
        redirect: 'error',
        signal: AbortSignal.timeout(15000),
      },
    );
    if (!response.ok || !response.body) return failure(response.status === 404 ? 404 : 502, 'This asset is unavailable');
    const type = response.headers.get('content-type')?.split(';')[0] ?? '';
    if (!media.has(type)) return failure(502, 'Unexpected asset response');
    const headers = new Headers({
      'Content-Type': type,
      'Cache-Control': 'private, no-store',
      'X-Content-Type-Options': 'nosniff',
      'Content-Security-Policy': "default-src 'none'; sandbox",
      'Referrer-Policy': 'no-referrer',
    });
    const length = response.headers.get('content-length');
    if (length && /^\d+$/.test(length)) headers.set('Content-Length', length);
    return new NextResponse(response.body, { headers });
  } catch {
    return failure(503, 'Design service is unavailable. Retry.');
  }
}
