const id = '[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}';
const uuidQuery = new RegExp('^' + id + '$', 'i');

/** Every query key this boundary will forward, per route. Anything else is refused. */
function onlyKeys(search: URLSearchParams, allowed: readonly string[]): boolean {
  return [...search.keys()].every((key) => allowed.includes(key));
}

/**
 * The fixed company-context and company-management boundary. Browser input cannot select another
 * service, another URL, or a route this list does not name (CLAUDE.md §5.1, deny by default).
 *
 * Reads are tunnelled as `{method:'GET'}` through the same POST handler as writes, so one
 * allowlist governs both rather than a second one growing beside it.
 *
 * Feature changes serve both setup and reviewed configuration. Identity enforces
 * dependencies, first-use locks and object scope; browser visibility grants no authority.
 */
export function allowedCompanyRequest(service: string, method: string, path: string): boolean {
  if (path.includes('\\') || path.includes('..') || path.includes('#') || /%2f|%5c/i.test(path)) return false;
  let url: URL;
  try {
    url = new URL(path, 'https://company.invalid');
  } catch {
    return false;
  }
  // A path that re-points the origin ("//evil.test/x", "https://evil.test/x") is not a path.
  if (url.origin !== 'https://company.invalid' || !path.startsWith('/v1/')) return false;
  const route = url.pathname;
  const search = url.searchParams;
  if ([...search.keys()].length !== new Set(search.keys()).size || route.includes('%')) return false;

  if (service === 'identity') {
    if (new RegExp('^/v1/companies/' + id + '/setup$', 'i').test(route)) return method === 'GET' && !url.search;
    if (new RegExp('^/v1/companies/' + id + '/setup/retry$', 'i').test(route)) return method === 'POST' && !url.search;
    if (new RegExp('^/v1/company-setup-commands/' + id + '$', 'i').test(route)) return method === 'GET' && !url.search;
    if (new RegExp('^/v1/companies/' + id + '/gst-outward-profile-setup$', 'i').test(route)) return method === 'GET' && !url.search;
    if (new RegExp('^/v1/companies/' + id + '/gst-outward-profiles$', 'i').test(route)) return method === 'POST' ? !url.search : method === 'GET' && onlyKeys(search, ['limit','cursor']);
    if (new RegExp('^/v1/companies/' + id + '/gst-outward-profiles/' + id + '$', 'i').test(route)) return method === 'PATCH' && !url.search;
    if (new RegExp('^/v1/companies/' + id + '/gst-registration-setup$', 'i').test(route)) return method === 'GET' && !url.search;
    if (new RegExp('^/v1/companies/' + id + '/tax-registrations$', 'i').test(route)) return method === 'POST' ? !url.search : method === 'GET' && onlyKeys(search, ['limit','cursor']);
    if (new RegExp('^/v1/companies/' + id + '/tax-registrations/' + id + '$', 'i').test(route)) return method === 'PATCH' && !url.search;
    if (route === '/v1/session') {
      const company = search.get('company_id');
      return method === 'GET' && onlyKeys(search, ['company_id']) && (company === null || uuidQuery.test(company));
    }
    // Management reads require company.read upstream; the working-company chooser stays a self-read.
    if (route === '/v1/companies') return method === 'POST' ? !url.search
      : method === 'GET' && onlyKeys(search, ['q', 'limit', 'cursor', 'sort', 'status', 'include_unlisted']);
    if (route === '/v1/session/companies') {
      return method === 'GET' && onlyKeys(search, ['q', 'limit', 'cursor']);
    }
    // "Set as my default". A self-write over Identity's own allowlist of preference fields —
    // this boundary forwards the method, and Identity decides which fields exist.
    if (route === '/v1/session/preferences') return method === 'PATCH' && !url.search;
    if (route === '/v1/company-classifications' || route === '/v1/company-features') {
      return method === 'GET' && !url.search;
    }
    if (route === '/v1/entities/identity.company/field-set') {
      const company = search.get('company_id');
      return method === 'GET' && onlyKeys(search, ['company_id']) && (company === null || uuidQuery.test(company));
    }
    if (route === '/v1/reference/countries' || route === '/v1/reference/currencies') return method === 'GET' && !url.search;
    if (new RegExp('^/v1/reference/countries/[A-Z]{2}/(?:states|licence-types)$').test(route)) return method === 'GET' && !url.search;
    if (url.search) return false;
    if (new RegExp('^/v1/companies/' + id + '/bank-accounts$', 'i').test(route)) return method === 'POST';
    if (new RegExp('^/v1/companies/' + id + '$', 'i').test(route)) return method === 'GET' || method === 'PATCH';
    if (new RegExp('^/v1/companies/' + id + '/(?:display-config|features|setup-readiness)$', 'i').test(route)) return method === 'GET';
    return (
      method === 'POST' &&
      new RegExp('^/v1/companies/' + id + '/features/[a-z][a-z0-9_]{0,39}/(?:enable|disable)$', 'i').test(route)
    );
  }

  const scoped = '^/v1/companies/' + id;
  if (service === 'vouchers') {
    return method === 'POST' && !url.search
      && new RegExp(scoped + '/voucher-type-defaults/bootstrap$', 'i').test(route);
  }
  if (service === 'catalog') {
    if (new RegExp(scoped + '/price-plans$', 'i').test(route)) {
      return method === 'GET' && onlyKeys(search, ['purpose', 'currency', 'price_level_id', 'limit'])
        && search.get('purpose') === 'SALE' && /^[A-Z]{3}$/.test(search.get('currency') ?? '')
        && uuidQuery.test(search.get('price_level_id') ?? '') && search.get('limit') === '2';
    }
    if (new RegExp(scoped + '/product-types/' + id + '/revisions$', 'i').test(route)) {
      return method === 'GET' && onlyKeys(search, ['published', 'limit']) && search.get('published') === 'true' && search.get('limit') === '1';
    }
    if (new RegExp(scoped + '/(?:item-groups|product-types)$', 'i').test(route)) {
      return method === 'GET' && (
        onlyKeys(search, ['code', 'limit']) && search.get('code') === 'DEFAULT' && search.get('limit') === '1'
        || onlyKeys(search, ['q', 'limit']) && search.get('q') === 'Default' && search.get('limit') === '50'
      );
    }
    return method === 'POST' && !url.search && new RegExp(scoped + '/(?:warehouse-configuration|pricing|tax-defaults|unit-defaults)/bootstrap$', 'i').test(route);
  }
  if (service !== 'accounting') return false;
  if (new RegExp(scoped + '/fiscal-years/next-preview$', 'i').test(route)) {
    const source = search.get('source_year_id');
    return method === 'GET' && onlyKeys(search, ['source_year_id']) && (source === null || uuidQuery.test(source));
  }
  if (new RegExp(scoped + '/(?:fiscal-years|fiscal-periods)$', 'i').test(route)) {
    return method === 'GET' && onlyKeys(search, ['limit', 'cursor', 'sort', 'q', 'status', 'fiscal_year_id']);
  }
  if (url.search) return false;
  if (new RegExp(scoped + '/finance/field-sets/(?:fiscal-years|fiscal-periods)$', 'i').test(route)) return method === 'GET';
  if (new RegExp(scoped + '/financial-setup$', 'i').test(route)) return method === 'GET';
  if (new RegExp(scoped + '/financial-setup/reconciliation-review$', 'i').test(route)) return method === 'GET';
  if (new RegExp(scoped + '/financial-setup/zero-opening-review$', 'i').test(route)) return method === 'GET';
  if (new RegExp(scoped + '/financial-setup/confirm-zero-opening$', 'i').test(route)) return method === 'POST';
  if (new RegExp(scoped + '/financial-setup/reconcile$', 'i').test(route)) return method === 'POST';
  if (new RegExp(scoped + '/financial-setup/initialize$', 'i').test(route)) return method === 'POST';
  if (new RegExp(scoped + '/accounting-setup/initialize$', 'i').test(route)) return method === 'POST';
  if (new RegExp(scoped + '/fiscal-years/generate$', 'i').test(route)) return method === 'POST';
  if (new RegExp(scoped + '/fiscal-years/' + id + '$', 'i').test(route)) return method === 'GET';
  if (new RegExp(scoped + '/fiscal-years/' + id + '/readiness$', 'i').test(route)) return method === 'GET';
  return method === 'POST' && new RegExp(scoped + '/fiscal-periods/' + id + '/transition$', 'i').test(route);
}
