import { consoleUrl } from './navigate';

/** Server configuration only; no provider credential or account lookup is exposed. */
export function passwordRecoveryDestination(): string | null {
  if (process.env.AUTHENTIK_SELF_SERVICE_RECOVERY_ENABLED !== 'true') return null;
  try {
    const issuer = new URL(process.env.AUTHENTIK_ISSUER ?? '');
    if (issuer.protocol !== 'https:' || issuer.username || issuer.password || issuer.search || issuer.hash) return null;
    return new URL('/if/flow/bill-self-service-recovery/', issuer.origin).href;
  } catch { return null; }
}

/** Recovery never accepts an arbitrary redirect from the query string. */
export function recoverySignInHref(candidate?: string): string {
  if (!candidate || candidate.length > 2048) return '/login';
  try {
    const base = new URL(consoleUrl());
    const target = new URL(candidate, base);
    const auth = process.env.NEXTAUTH_URL ? new URL(process.env.NEXTAUTH_URL) : null;
    if (target.username || target.password || !['http:', 'https:'].includes(target.protocol)) return '/login';
    if (target.origin !== base.origin && !(auth && target.origin === auth.origin && target.pathname === '/setup')) return '/login';
    return '/login?returnTo=' + encodeURIComponent(target.href);
  } catch { return '/login'; }
}
