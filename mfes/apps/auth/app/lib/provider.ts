/**
 * The one place that decides who owns credentials for this installation and where its OpenID
 * Connect endpoints live (docs/local-auth.md §2).
 *
 * `AUTH_PROVIDER` is `local` (the default when unset) or `authentik`. Anything else is a
 * configuration error: it throws, so every caller fails closed exactly as it does for any other
 * missing or malformed authentication setting. Nothing here reads a request or a browser value.
 */

export type ProviderId = 'local' | 'authentik';

const LOOPBACK = ['localhost', '127.0.0.1', '[::1]'];

export function authProvider(): ProviderId {
  const value = process.env.AUTH_PROVIDER?.trim();
  if (!value) return 'local';
  if (value === 'local' || value === 'authentik') return value;
  throw new Error('Invalid authentication provider configuration');
}

/** For public pages that must render something sensible instead of crashing on a bad value. */
export function safeAuthProvider(): ProviderId | null {
  try { return authProvider(); } catch { return null; }
}

function required(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`Missing authentication configuration: ${name}`);
  return value;
}

/** A URL that never carries credentials, a query or a fragment, over HTTPS or loopback HTTP. */
function plainUrl(value: string): URL {
  const url = new URL(value);
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash ||
      (url.protocol === 'http:' && !LOOPBACK.includes(url.hostname))) throw new Error('Invalid authentication endpoint configuration');
  return url;
}

export type ProviderEndpoints = {
  id: ProviderId;
  name: string;
  issuer: string;
  clientId: string;
  clientSecret: string;
  /** OIDC discovery document, used by NextAuth and the setup connection checks. */
  wellKnown: string;
  tokenUrl: string;
  revokeUrl: string;
};

export function providerEndpoints(): ProviderEndpoints {
  if (authProvider() === 'local') {
    const issuer = required('AUTH_LOCAL_ISSUER');
    plainUrl(issuer);
    const base = issuer.replace(/\/$/, '');
    return { id: 'local', name: 'KiscoBooks', issuer,
      clientId: required('AUTH_LOCAL_CLIENT_ID'), clientSecret: required('AUTH_LOCAL_CLIENT_SECRET'),
      wellKnown: `${base}/.well-known/openid-configuration`, tokenUrl: `${base}/token`, revokeUrl: `${base}/revoke` };
  }
  const issuer = required('AUTHENTIK_ISSUER');
  const origin = new URL(issuer).origin;
  if (!issuer.startsWith('https://')) throw new Error('The identity provider requires HTTPS');
  return { id: 'authentik', name: 'Authentik', issuer,
    clientId: required('AUTHENTIK_CLIENT_ID'), clientSecret: required('AUTHENTIK_CLIENT_SECRET'),
    wellKnown: `${issuer.replace(/\/$/, '')}/.well-known/openid-configuration`,
    tokenUrl: `${origin}/application/o/token/`, revokeUrl: `${origin}/application/o/revoke/` };
}

/** The Auth app's own public origin: where the browser is, and the only origin a callback may use. */
export function authOrigin(): string {
  const url = plainUrl(process.env.NEXTAUTH_URL ?? '');
  if (url.pathname !== '/') throw new Error('Invalid authentication endpoint configuration');
  return url.origin;
}

/** What the Auth app server needs to call Identity's `/internal/v1/local-auth/*` surface. */
export function localBff(): { secret: string; identityUrl: URL } {
  const secret = required('AUTH_LOCAL_BFF_SECRET');
  // Identity requires at least 32 bytes; refusing a short one here names the mistake early.
  if (secret.length < 32) throw new Error('Invalid authentication endpoint configuration');
  const identityUrl = plainUrl(required('IDENTITY_URL'));
  if (identityUrl.pathname !== '/') throw new Error('Invalid authentication endpoint configuration');
  return { secret, identityUrl };
}
