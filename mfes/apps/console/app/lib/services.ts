/**
 * Which origin serves which service, and which company a request is scoped to.
 *
 * One table rather than one per caller. The console reaches services from two places — Server
 * Components (`app/identity-session`) and the browser-facing proxy (`lib/service-proxy`) — and
 * before this they each carried their own env mapping, so adding a service meant registering it
 * twice and only one of the two knew that a gateway origin carries a path prefix.
 *
 * Nothing here is authorization: a route's allowlist decides which services and paths it will
 * forward at all, and the service authorizes the request again on arrival.
 */
export type Service = 'identity' | 'audit' | 'accounting' | 'catalog' | 'vouchers' | 'reports' | 'notification' | 'design';

const SERVICES: Record<Service, { env: () => string | undefined; prefix: string; label: string }> = {
  identity: { env: () => process.env.IDENTITY_URL, prefix: '', label: 'Identity' },
  // The audit gateway is addressed at the gateway root and prefixed per call.
  audit: { env: () => process.env.AUDIT_GATEWAY_URL, prefix: '/audit', label: 'Audit' },
  accounting: { env: () => process.env.ACCOUNTING_GATEWAY_URL, prefix: '', label: 'Accounting' },
  catalog: { env: () => process.env.CATALOG_GATEWAY_URL, prefix: '', label: 'Catalog' },
  vouchers: { env: () => process.env.VOUCHERS_GATEWAY_URL, prefix: '', label: 'Vouchers' },
  notification: { env: () => process.env.NOTIFICATION_GATEWAY_URL, prefix: '', label: 'Notification' },
  reports: { env: () => process.env.REPORTS_GATEWAY_URL, prefix: '', label: 'Reports' },
  design: { env: () => process.env.DESIGN_GATEWAY_URL, prefix: '', label: 'Design' },
};

export function isService(name: unknown): name is Service {
  return typeof name === 'string' && name in SERVICES;
}

/** The configured base for a service, or nothing — never a guess, so a caller answers 503. */
export function serviceOrigin(name: string): string | undefined {
  if (!isService(name)) return undefined;
  const origin = SERVICES[name].env();
  return origin ? origin.replace(/\/$/, '') + SERVICES[name].prefix : undefined;
}

export function serviceLabel(name: Service): string {
  return SERVICES[name].label;
}

/**
 * The company a request is scoped to, from its path or its body.
 *
 * Anchored on the path segment, so only `/companies/{id}` names a company — an id that happens
 * to appear later in a path does not. The body is the fallback for a create, where the company
 * is a field rather than a segment.
 */
export function companyInPath(path: string, body?: unknown): string | undefined {
  const matched = /\/companies\/([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})(?:\/|$|\?)/i.exec(path)?.[1];
  if (matched) return matched.toLowerCase();
  try {
    const query = new URL(path, 'https://service.invalid').searchParams.get('company_id');
    if (query) return query.toLowerCase();
  } catch {
    /* A path that is not a path names no company. */
  }
  const field = (body as { company_id?: unknown } | undefined)?.company_id;
  return typeof field === 'string' ? field.toLowerCase() : undefined;
}

/** The step-up proof this browser holds for a company, if any. Identity verifies its own proof. */
export function stepUpCookieName(company: string): string {
  return 'janso-step-up-' + company.toLowerCase();
}
