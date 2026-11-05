import { describe, expect, it } from 'vitest';
import { allowedConfigurationRequest } from '../app/lib/product-configuration-policy';
import { allowedProductRequest } from '../app/lib/product-request-policy';
import { COMPANY, DRAFT, ITEM, SCOPE, REVISION } from './product-configuration-fixtures';
const base = `/v1/companies/${COMPANY}`;
describe('native configuration proxy boundary', () => {
  it.each(['AC/DC', 'Dr..Who', 'A\\B'])('preserves reference search punctuation: %s', q => {
    const path = base + '/product-configuration/options/product-type-revisions?' + new URLSearchParams({ q });
    expect(allowedConfigurationRequest('GET', path)).toBe(true);
    expect(allowedProductRequest('catalog', 'GET', path)).toBe(true);
  });
  it('keeps configuration lookups in their namespace when search text names a product route', () => {
    expect(allowedProductRequest('catalog', 'GET', base + '/product-configuration/options/items?q=/products')).toBe(true);
  });
  it.each(['items', 'product-type-revisions', 'attribute-set-revisions', 'identifier-profiles', 'inventory-template-revisions', 'warranty-revisions', 'return-policy-revisions', 'handling-revisions', 'currencies'])('keeps configuration reference lookup for %s reachable through the composed policy', source => {
    const path = base + '/product-configuration/options/' + source + '?limit=50&q=QA';
    expect(allowedConfigurationRequest('GET', path)).toBe(true);
    expect(allowedProductRequest('catalog', 'GET', path)).toBe(true);
  });
  it.each([['POST', '/product-configuration/options/items'], ['GET', '/product-configuration/options/users'], ['GET', '/product-configuration/options/items?fields=secret']])('keeps unsupported reference access refused: %s %s', (method, route) => {
    expect(allowedProductRequest('catalog', method, base + route)).toBe(false);
  });
  it.each([['GET', '/product-configuration-scopes?limit=25&sort=-id'], ['POST', '/product-configuration-scopes'], ['GET', `/product-configuration-scopes/${SCOPE}/drafts?status=DRAFT`], ['GET', `/product-configuration-scopes/${SCOPE}/revisions?limit=1`], ['POST', '/product-configurations'], ['PATCH', `/product-configurations/${DRAFT}`], ['GET', `/product-configurations/${DRAFT}/preview`], ['POST', `/product-configurations/${DRAFT}/publish`], ['GET', `/product-configuration-revisions/${REVISION}`], ['GET', '/product-configuration/effective?as_of=2028-01-01&kind=GOODS'], ['GET', '/product-configuration/options/product-type-revisions?kind=GOODS&q=General'], ['GET', '/product-configuration/options/currencies?value=INR'], ['GET', `/items/${ITEM}/configuration-adoption/preview?as_of=2028-01-01`], ['POST', `/items/${ITEM}/configuration-adoption`], ['GET', '/entities/catalog.product_pricing_policy/field-set?operation=update']])('allows %s %s', (method, route) => { expect(allowedConfigurationRequest(method, base + route)).toBe(true); expect(allowedProductRequest('catalog', method, base + route)).toBe(true); });
  it.each([['DELETE', `/product-configurations/${DRAFT}`], ['PATCH', `/product-configuration-revisions/${REVISION}`], ['GET', `/product-configurations/${DRAFT}/publish`], ['POST', `/product-configurations/${DRAFT}/preview`], ['GET', '/product-configuration-scopes?limit=25&limit=50'], ['GET', '/product-configuration-scopes?q=secret'], ['GET', '/product-configuration/options/users'], ['GET', '/product-configuration/options/groups?fields=secret'], ['GET', '/product-configuration/options/../groups'], ['GET', '/product-configuration/options/%2fitems'], ['GET', '/product-configuration/effective#other']])('rejects %s %s', (method, route) => expect(allowedConfigurationRequest(method, base + route)).toBe(false));
  it('does not capture unrelated master requests', () => expect(allowedConfigurationRequest('GET', base + '/units')).toBeUndefined());
  it('permits the atomic company draft route and refuses retired ownership queries', () => {
    expect(allowedProductRequest('catalog', 'POST', base + '/product-configurations/company')).toBe(true);
    expect(allowedConfigurationRequest('GET', base + '/product-configurations/company')).toBe(false);
    expect(allowedConfigurationRequest('GET', base + '/product-configuration-scopes?scope_kind=COMPANY')).toBe(true);
    expect(allowedConfigurationRequest('GET', base + '/product-configuration-scopes?scope_kind=GROUP')).toBe(false);
    expect(allowedConfigurationRequest('GET', base + '/product-configuration-scopes?group_id=' + ITEM)).toBe(false);
    for (const source of ['product-types', 'groups', 'families']) expect(allowedConfigurationRequest('GET', base + '/product-configuration/options/' + source)).toBe(false);
  });
});
