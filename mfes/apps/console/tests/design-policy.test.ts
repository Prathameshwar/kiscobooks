/**
 * The console-to-`design` proxy boundary.
 *
 * The service authorizes every request again on arrival, so this is not the authorization
 * boundary — it is the reason a path the console never calls cannot be reached through the
 * console's own credentials. A `{service, path}` proxy without a closed allowlist is an open
 * relay into the service mesh, which is why this is tested path by path rather than by
 * eyeballing a regex.
 */
import { describe, expect, it } from 'vitest';
import { allowedDesignRequest } from '../app/lib/design-request-policy';
import { allowedProductRequest } from '../app/lib/product-request-policy';
import { assertDesignRow, assertDesignVersion, designBase } from '../app/lib/design-api';
import { isService, serviceOrigin } from '../app/lib/services';

const COMPANY = '01990000-0000-7000-8000-000000000001';
const TEMPLATE = '01990000-0000-7000-8000-000000000002';
const VERSION = '01990000-0000-7000-8000-000000000003';
const OTHER = '01990000-0000-7000-8000-00000000000b';
const root = '/v1/companies/' + COMPANY;

const allow = (method: string, path: string) => allowedProductRequest('design', method, path);

describe('the design service is addressable at all', () => {
  it('is a known service with its own configured origin', () => {
    expect(isService('design')).toBe(true);
    // Never a guess: an unconfigured origin makes the caller answer 503 rather than invent a host.
    expect(serviceOrigin('design')).toBeUndefined();
    process.env.DESIGN_GATEWAY_URL = 'http://127.0.0.1:8090/design/';
    expect(serviceOrigin('design')).toBe('http://127.0.0.1:8090/design');
    delete process.env.DESIGN_GATEWAY_URL;
  });

  it('routes design through the shared proxy allowlist, not past it', () => {
    expect(allow('GET', root + '/templates')).toBe(true);
    // The same path on another service's name is still refused — the name does not grant it.
    expect(allowedProductRequest('catalog', 'GET', root + '/templates')).toBe(false);
  });
});

describe('templates and versions', () => {
  it('allows the lifecycle the service actually implements', () => {
    expect(allow('POST', root + '/templates')).toBe(true);
    expect(allow('GET', root + '/templates?status=DRAFT&limit=50')).toBe(true);
    expect(allow('GET', root + '/templates?status=PUBLISHED')).toBe(true);
    expect(allow('GET', root + '/templates/' + TEMPLATE)).toBe(true);
    expect(allow('PUT', root + '/templates/' + TEMPLATE)).toBe(true);
    // Archiving is a DELETE that sets `status = ARCHIVED`; the row is never removed.
    expect(allow('DELETE', root + '/templates/' + TEMPLATE)).toBe(true);
    expect(allow('POST', root + '/templates/' + TEMPLATE + '/versions')).toBe(true);
    expect(allow('GET', root + '/templates/' + TEMPLATE + '/versions?limit=25')).toBe(true);
    expect(allow('GET', root + '/templates/' + TEMPLATE + '/versions/' + VERSION)).toBe(true);
    expect(allow('POST', root + '/templates/' + TEMPLATE + '/versions/' + VERSION + '/publish')).toBe(true);
  });

  it('refuses methods the service does not offer on a template', () => {
    expect(allow('PATCH', root + '/templates/' + TEMPLATE)).toBe(false);
    expect(allow('PUT', root + '/templates')).toBe(false);
    expect(allow('DELETE', root + '/templates')).toBe(false);
    // A published version is immutable: there is no edit-in-place path to one.
    expect(allow('PUT', root + '/templates/' + TEMPLATE + '/versions/' + VERSION)).toBe(false);
    expect(allow('PATCH', root + '/templates/' + TEMPLATE + '/versions/' + VERSION)).toBe(false);
    expect(allow('DELETE', root + '/templates/' + TEMPLATE + '/versions/' + VERSION)).toBe(false);
    expect(allow('GET', root + '/templates/' + TEMPLATE + '/versions/' + VERSION + '/publish')).toBe(false);
  });

  it('refuses a status the service would reject anyway, rather than forwarding it', () => {
    expect(allow('GET', root + '/templates?status=ARCHIVED')).toBe(false);
    expect(allow('GET', root + '/templates?status=draft')).toBe(false);
  });
});

describe('assignments, resolution, assets and components', () => {
  it('allows routing rules to be listed, created and amended', () => {
    expect(allow('POST', root + '/assignments')).toBe(true);
    expect(allow('GET', root + '/assignments?voucher_kind=SALES_INVOICE&include_inactive=true')).toBe(true);
    expect(allow('PATCH', root + '/assignments/' + TEMPLATE)).toBe(true);
    expect(allow('POST', root + '/resolve')).toBe(true);
    // An assignment is deactivated through PATCH, so there is no DELETE to reach.
    expect(allow('DELETE', root + '/assignments/' + TEMPLATE)).toBe(false);
    expect(allow('GET', root + '/assignments?voucher_kind=sales_invoice')).toBe(false);
    expect(allow('GET', root + '/resolve')).toBe(false);
  });

  it('answers where one design is used, by template id and nothing looser (plan R4)', () => {
    expect(allow('GET', root + '/assignments?template_id=' + TEMPLATE + '&limit=200')).toBe(true);
    expect(allow('GET', root + '/assignments?template_id=' + TEMPLATE.toUpperCase())).toBe(true);
    expect(allow('GET', root + '/assignments?template_id=' + TEMPLATE + '&voucher_kind=PURCHASE&include_inactive=false')).toBe(true);
    // Not an id, a repeated key, or a filter on a write: each is refused before the service sees it.
    expect(allow('GET', root + '/assignments?template_id=not-a-uuid')).toBe(false);
    expect(allow('GET', root + '/assignments?template_id=')).toBe(false);
    expect(allow('GET', root + '/assignments?template_id=' + TEMPLATE + '&template_id=' + OTHER)).toBe(false);
    expect(allow('POST', root + '/assignments?template_id=' + TEMPLATE)).toBe(false);
    expect(allow('PATCH', root + '/assignments/' + TEMPLATE + '?template_id=' + TEMPLATE)).toBe(false);
  });

  it('allows the asset and component surface the designer places on a layout', () => {
    // An upload carries its bytes past this proxy's ceiling, so it has its own route
    // (`api/design-asset-upload`, P4) and is refused here (stale `true` corrected 2026-11-04).
    expect(allow('POST', root + '/assets')).toBe(false);
    expect(allow('GET', root + '/assets?asset_type=LOGO&include_inactive=false')).toBe(true);
    expect(allow('GET', root + '/assets/' + TEMPLATE)).toBe(true);
    expect(allow('DELETE', root + '/assets/' + TEMPLATE)).toBe(true);
    expect(allow('POST', root + '/components')).toBe(true);
    expect(allow('GET', root + '/components?category=TERMS')).toBe(true);
    expect(allow('PATCH', root + '/components/' + TEMPLATE)).toBe(true);
    expect(allow('DELETE', root + '/components/' + TEMPLATE)).toBe(false);
  });

  /*
   * The one place this boundary is deliberately narrower than the API. `POST /renders` records
   * that a document was printed, under `design.render.record`; a browser asserting that is
   * evidence of nothing, and print evidence is the thing a reprint is verified against.
   */
  it('reads print evidence and never writes it from a browser', () => {
    expect(allow('GET', root + '/renders?limit=50')).toBe(true);
    expect(allow('GET', root + '/renders?voucher_id=' + VERSION)).toBe(true);
    expect(allow('POST', root + '/renders')).toBe(false);
    expect(allow('GET', root + '/renders?voucher_id=not-a-uuid')).toBe(false);
  });
});

describe('the shape of a request, before its meaning', () => {
  it.each([
    ['a protocol-relative host disguised as a path', 'GET', '//evil.invalid/v1/companies/' + COMPANY + '/templates'],
    ['an encoded separator', 'GET', root + '/templates/%2e%2e/assets'],
    ['a fragment', 'GET', root + '/templates#/assets'],
    ['a backslash', 'GET', root + '\\templates'],
    ['two query strings', 'GET', root + '/templates?limit=5?limit=200'],
    ['a repeated key', 'GET', root + '/templates?limit=1&limit=200'],
    ['an unknown filter', 'GET', root + '/templates?archived=true'],
    ['a limit above the service bound', 'GET', root + '/templates?limit=201'],
    ['a limit below one', 'GET', root + '/templates?limit=0'],
    ['a non-numeric limit', 'GET', root + '/templates?limit=all'],
    ['an empty cursor', 'GET', root + '/templates?cursor='],
    ['a query on a detail read', 'GET', root + '/templates/' + TEMPLATE + '?expand=versions'],
    ['a company that is not a uuid', 'GET', '/v1/companies/all/templates'],
    ['the all-zero company sentinel as a scope', 'GET', '/v1/companies/00000000-0000-0000-0000-00000000000g/templates'],
  ])('refuses %s', (_name, method, path) => {
    expect(allow(method, path)).toBe(false);
  });

  it('leaves a path outside its namespace to the other allowlists', () => {
    // `undefined`, not `false`: claiming a path it does not own would let this policy veto
    // another service's route by accident.
    expect(allowedDesignRequest('GET', root + '/items')).toBeUndefined();
    expect(allowedDesignRequest('GET', root + '/tax-categories')).toBeUndefined();
    expect(allowedDesignRequest('GET', root + '/templates')).toBe(true);
  });

  it('refuses an unrecognised path inside its own namespace', () => {
    expect(allowedDesignRequest('GET', root + '/templates/' + TEMPLATE + '/render')).toBe(false);
    expect(allowedDesignRequest('POST', root + '/templates/' + TEMPLATE + '/duplicate')).toBe(false);
  });
});

describe('response verification', () => {
  it('builds the template path the screens read from', () => {
    expect(designBase(COMPANY)).toBe(root + '/templates');
    expect(designBase(COMPANY, '/' + TEMPLATE + '/versions')).toBe(root + '/templates/' + TEMPLATE + '/versions');
  });

  it('accepts this company’s row and the tenant-wide house style', () => {
    const SCOPE_ALL = '00000000-0000-0000-0000-000000000000';
    expect(assertDesignRow({ id: TEMPLATE, company_id: COMPANY }, COMPANY).id).toBe(TEMPLATE);
    expect(assertDesignRow({ id: TEMPLATE, company_id: SCOPE_ALL }, COMPANY).id).toBe(TEMPLATE);
    expect(assertDesignRow({ id: TEMPLATE }, COMPANY).id).toBe(TEMPLATE);
  });

  it('does not let a shipped flag excuse another company’s id', () => {
    // `is_system` says a design is shipped; only `SCOPE_ALL` says it belongs to no company,
    // and only that makes "this reply is not for the open company" the wrong conclusion.
    expect(() =>
      assertDesignRow({ id: TEMPLATE, company_id: OTHER, is_system: true }, COMPANY),
    ).toThrow();
  });

  it('rejects a reply for the company the reader just left', () => {
    // The company is switchable from the rail, so this arrives in practice; painting it would
    // show one company's template under another's name.
    expect(() => assertDesignRow({ id: TEMPLATE, company_id: OTHER }, COMPANY)).toThrow();
    expect(() => assertDesignRow({ id: TEMPLATE, company_id: COMPANY }, COMPANY, OTHER)).toThrow();
    expect(() => assertDesignRow({ id: 'not-a-uuid', company_id: COMPANY }, COMPANY)).toThrow();
  });

  it('rejects a save that did not append a revision', () => {
    expect(assertDesignVersion({ id: VERSION, template_id: TEMPLATE, version_number: 3 }, TEMPLATE).id).toBe(VERSION);
    expect(() => assertDesignVersion({ id: VERSION, version_number: 0 })).toThrow();
    expect(() => assertDesignVersion({ id: VERSION })).toThrow();
    expect(() => assertDesignVersion({ id: VERSION, version_number: 1.5 })).toThrow();
    expect(() => assertDesignVersion({ id: VERSION, template_id: OTHER, version_number: 1 }, TEMPLATE)).toThrow();
  });
});
