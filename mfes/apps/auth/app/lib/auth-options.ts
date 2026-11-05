import type { NextAuthOptions } from 'next-auth';
import { coordinatedRefresh, validLifetime, validToken } from './refresh-coordinator';
import { providerEndpoints } from './provider';
import { parseRegion } from './registration-regions';

function required(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`Missing authentication configuration: ${name}`);
  return value;
}

export function safeReturnUrl(value: string | null): string {
  const base = new URL(required('CONSOLE_URL'));
  if (!value) return base.href;
  try {
    const target = new URL(value, base);
    if (target.origin === base.origin && !target.username && !target.password) return target.href;
  } catch { /* Return the configured console URL for malformed input. */ }
  return base.href;
}

export function authOptions(): NextAuthOptions {
  // One resolver picks the provider (AUTH_PROVIDER) and its endpoints; see provider.ts.
  const { id, name, issuer, clientId, clientSecret, wellKnown, tokenUrl, revokeUrl } = providerEndpoints();
  const secret = required('NEXTAUTH_SECRET');
  const authUrl = new URL(required('NEXTAUTH_URL'));
  for (const value of [authUrl.href, issuer, required('CONSOLE_URL'), required('IDENTITY_URL')]) {
    const url = new URL(value);
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash)
      throw new Error('Invalid authentication endpoint configuration');
  }
  if (process.env.AUTH_COOKIE_DOMAIN && authUrl.protocol !== 'https:')
    throw new Error('Shared authentication cookies require HTTPS');
  return {
    secret,
    session: { strategy: 'jwt', maxAge: 8 * 60 * 60 },
    ...(process.env.AUTH_COOKIE_DOMAIN ? { cookies: { sessionToken: {
      name: '__Secure-next-auth.session-token', options: { httpOnly: true, secure: true,
        sameSite: 'lax' as const, path: '/', domain: process.env.AUTH_COOKIE_DOMAIN },
    } } } : {}),
    pages: { signIn: '/login', error: '/login' },
    providers: [{
      id, name, type: 'oauth', wellKnown,
      clientId, clientSecret, idToken: true,
      checks: ['pkce', 'state', 'nonce'],
      authorization: { params: { scope: 'openid profile email offline_access billing.api' } },
      profile(profile) { return { id: profile.sub, name: profile.name, email: profile.email }; },
    }],
    callbacks: {
      async jwt({ token, account, profile }) {
        if (account) {
          const lifetime = (account.expires_at ?? 0) - Date.now() / 1000;
          if (!validToken(account.access_token) || typeof account.expires_at !== 'number' ||
              !Number.isFinite(account.expires_at) || !validLifetime(lifetime) ||
              (account.refresh_token !== undefined && !validToken(account.refresh_token))) {
            return { ...token, accessToken: undefined, refreshToken: undefined,
              accessTokenExpires: 0, refreshError: true, refreshFailure: 'invalid' };
          }
          token.accessToken = account.access_token;
          token.refreshToken = account.refresh_token;
          token.accessTokenExpires = (account.expires_at ?? 0) * 1000;
          // Sign-in profile is supplied by the checked OIDC exchange; client session
          // updates cannot overwrite this. No profile field grants billing authority.
          token.registrationRegion = parseRegion((profile as { billing_registration_region?: unknown } | undefined)?.billing_registration_region);
          delete token.refreshError;
          delete token.refreshFailure;
          return token;
        }
        if (validToken(token.accessToken) && typeof token.accessTokenExpires === 'number' &&
            Number.isFinite(token.accessTokenExpires) && Date.now() < token.accessTokenExpires - 30_000) return token;
        if (!validToken(token.refreshToken)) return { ...token, accessToken: undefined, refreshError: true, refreshFailure: 'invalid' };
        const refreshToken = token.refreshToken;
        const result = await coordinatedRefresh({ secret, issuer, clientId, refreshToken }, async () => {
          const response = await fetch(tokenUrl, {
            method: 'POST', cache: 'no-store', redirect: 'error',
            signal: AbortSignal.timeout(5000),
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: new URLSearchParams({ grant_type: 'refresh_token', refresh_token: refreshToken,
              client_id: clientId, client_secret: clientSecret }),
          });
          const refreshed = await response.json();
          if (!response.ok) return { error: response.status === 400 || response.status === 401 ? 'invalid' : 'unavailable' };
          if (!validToken(refreshed.access_token) || !validLifetime(refreshed.expires_in) ||
              (refreshed.refresh_token !== undefined && !validToken(refreshed.refresh_token))) return { error: 'invalid' };
          return { accessToken: refreshed.access_token,
            accessTokenExpires: Date.now() + refreshed.expires_in * 1000,
            refreshToken: refreshed.refresh_token ?? refreshToken };
        });
        if ('error' in result) return { ...token, accessToken: undefined, accessTokenExpires: 0,
          ...(result.error === 'invalid' ? { refreshToken: undefined } : {}),
          refreshError: true, refreshFailure: result.error };
        return { ...token, ...result, refreshError: false, refreshFailure: undefined };
      },
      async session({ session, token }) {
        // Access/refresh tokens stay in the encrypted HttpOnly cookie, never in this JSON.
        if (token.refreshError) {
          session.expires = new Date(0).toISOString();
          Object.assign(session, { authError: token.refreshFailure === 'unavailable' ? 'unavailable' : 'expired' });
        }
        return session;
      },
      async redirect({ url, baseUrl }) {
        const auth = new URL(baseUrl);
        try {
          const target = new URL(url, auth);
          if (target.origin === auth.origin && !target.username && !target.password) return target.href;
        } catch { /* Use the configured return destination. */ }
        return safeReturnUrl(url);
      },
    },
    events: {
      async signOut({ token }) {
        // An expired access token cannot authorize Identity's durable revocation.
        if (token && typeof token.accessTokenExpires === 'number' &&
            Date.now() >= token.accessTokenExpires - 30_000 && validToken(token.refreshToken)) {
          const current = await authOptions().callbacks!.jwt!({ token } as never);
          if (!current.refreshError) token = current;
        }
        if (validToken(token?.accessToken) && process.env.IDENTITY_URL) {
          await fetch(new URL('/v1/session/revoke', process.env.IDENTITY_URL), {
            method: 'POST', cache: 'no-store', redirect: 'error', signal: AbortSignal.timeout(5000),
            headers: { Authorization: `Bearer ${token.accessToken}` },
          }).catch(() => undefined);
        }
        if (!validToken(token?.refreshToken)) return;
        await fetch(revokeUrl, {
          method: 'POST', cache: 'no-store', redirect: 'error', signal: AbortSignal.timeout(5000),
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body: new URLSearchParams({ token: token.refreshToken, token_type_hint: 'refresh_token',
            client_id: clientId, client_secret: clientSecret }),
        }).catch(() => undefined);
      },
    },
  };
}
