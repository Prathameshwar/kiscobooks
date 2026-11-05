import { beforeEach, expect, it, vi } from 'vitest';
import { allowedProductRequest } from '../app/lib/product-request-policy';
import {
  canEditPricing,
  pricingBody,
  pricingCommand,
  pricingLink,
  pricingReturn,
} from '../app/lib/pricing-masters';
import { masterConfig } from '../app/lib/catalog-masters';
import { serviceCall } from '../app/lib/service-call';
import {
  COMPANY,
  RECORD,
  FRESH,
  SOURCE,
  fields,
  row,
  access,
  response,
  resetFixtures,
} from './pricing-master-fixtures';
vi.mock('../app/lib/service-call', async (original) => ({
  ...(await original<typeof import('../app/lib/service-call')>()),
  serviceCall: vi.fn(),
}));
const root = '/v1/companies/' + COMPANY,
  api = vi.mocked(serviceCall);
beforeEach(() => {
  vi.clearAllMocks();
  resetFixtures();
});
it.each(['sales-channels', 'price-levels', 'price-plans'])(
  'allows only native %s methods',
  (resource) => {
    for (const [method, path] of [
      ['GET', '/' + resource],
      ['POST', '/' + resource],
      ['GET', '/' + resource + '/' + RECORD],
      ['PATCH', '/' + resource + '/' + RECORD],
      [
        'GET',
        '/entities/catalog.' +
          resource.replaceAll('-', '_').replace(/s$/, '') +
          '/field-set?operation=update',
      ],
    ])
      expect(allowedProductRequest('catalog', method!, root + path)).toBe(true);
    for (const method of ['DELETE', 'PUT'])
      expect(
        allowedProductRequest(
          'catalog',
          method,
          root + '/' + resource + '/' + RECORD,
        ),
      ).toBe(false);
  },
);
it.each(['price-levels', 'price-plans'])(
  'rejects invented %s lifecycle/publication routes',
  (resource) => {
    for (const action of ['activate', 'deactivate', 'publish', 'revisions'])
      expect(
        allowedProductRequest(
          'catalog',
          'POST',
          root + '/' + resource + '/' + RECORD + '/' + action,
        ),
      ).toBe(false);
  },
);
it.each([
  'q=a',
  'q=ok&q=other',
  'limit=201',
  'limit=0',
  'sort=name',
  'as_of=2026-10-25',
  'is_active=true',
  'item_id=' + RECORD,
  'purpose=OTHER',
  'currency=inr',
  'price_level_id=nope',
  'operation=create',
])('closes unsupported plan query %s', (query) =>
  expect(
    allowedProductRequest('catalog', 'GET', root + '/price-plans?' + query),
  ).toBe(false),
);
it('admits purpose, level and currency filters and idempotent baseline setup', () => {
  expect(
    allowedProductRequest(
      'catalog',
      'GET',
      root + '/price-plans?purpose=SALE&currency=INR&price_level_id=' + SOURCE,
    ),
  ).toBe(true);
  expect(
    allowedProductRequest('catalog', 'POST', root + '/pricing/bootstrap'),
  ).toBe(true);
  expect(
    allowedProductRequest('catalog', 'GET', root + '/pricing/bootstrap'),
  ).toBe(false);
  expect(
    allowedProductRequest(
      'catalog',
      'POST',
      root + '/pricing/bootstrap?extra=true',
    ),
  ).toBe(false);
});
it.each([
  '//evil.invalid',
  'https://evil.invalid',
  '/masters/price-plans/%2e%2e',
  '/masters/price-plans#bad',
  '/masters/price-plans\\edit',
  '/masters/price-plans/' + RECORD + '/publish',
])('rejects unsafe navigation %s', (value) =>
  expect(pricingReturn(value)).toBe('/settings'),
);
it('retains bounded internal return navigation and valid filters', () => {
  const back = '/masters/price-plans?purpose=SALE&currency=INR&limit=50';
  expect(pricingReturn(back)).toBe(back);
  expect(
    new URL(
      pricingLink('/masters/price-plans/' + RECORD + '/edit', back),
      'https://console.invalid',
    ).searchParams.get('returnTo'),
  ).toBe(back);
  expect(pricingReturn('/masters/price-plans?unknown=true&purpose=SALE')).toBe(
    '/masters/price-plans?purpose=SALE',
  );
});
it.each(['3', '65', '4.0', '4e0', 'abc'])(
  'rejects invalid level number %s',
  (ordinal) =>
    expect(
      pricingBody(
        masterConfig('price-levels')!,
        fields('price_level', 'create'),
        { code: 'EXTRA', name: 'Extra', ordinal },
      ).errors.ordinal,
    ).toBeTruthy(),
);
it('reserves baseline codes and keeps the native complete level patch', () => {
  const config = masterConfig('price-levels')!,
    original = row('price-levels');
  expect(
    pricingBody(config, fields('price_level', 'create'), {
      code: 'PRICE1',
      name: 'Extra',
      ordinal: '4',
    }).errors.code,
  ).toBeTruthy();
  expect(
    pricingBody(
      config,
      fields('price_level', 'update'),
      { ...original, name: 'New name', code: 'CHANGED', ordinal: '9' },
      original,
    ).body,
  ).toEqual({ expected_version: 4, name: 'New name', is_active: true });
});
it('fixes plan identity and omits sale-level semantics for purchase', () => {
  const config = masterConfig('price-plans')!,
    original = row('price-plans');
  expect(
    pricingBody(
      config,
      fields('price_plan', 'update'),
      { ...original, name: 'New', purpose: 'PURCHASE', currency: 'USD' },
      original,
    ).body,
  ).toEqual({ expected_version: 4, name: 'New' });
  expect(
    pricingBody(config, fields('price_plan', 'create'), {
      ...config.initial,
      code: 'BUY',
      name: 'Buy',
      currency: 'INR',
      purpose: 'PURCHASE',
      price_level_id: SOURCE,
    }).body.price_level_id,
  ).toBeNull();
});
it('withholds purchase edits without both purchase authorities', () => {
  const original = { ...row('price-plans'), purpose: 'PURCHASE' };
  expect(
    canEditPricing(
      masterConfig('price-plans')!,
      fields('price_plan'),
      original,
      { ...access, purchaseManage: false },
    ),
  ).toBe(false);
});
it('withholds plan edits when its purpose is protected', () => {
  const original = row('price-plans');
  delete original.purpose;
  expect(
    canEditPricing(
      masterConfig('price-plans')!,
      fields('price_plan'),
      original,
      access,
    ),
  ).toBe(false);
});
it('verifies command receipts against the current company record', async () => {
  api.mockImplementation(
    async (_endpoint, request) => response(request) as never,
  );
  const saved = await pricingCommand({
    path: root + '/price-plans',
    method: 'POST',
    body: { code: 'NEW', name: 'New' },
  });
  expect(saved).toMatchObject({ id: FRESH, company_id: COMPANY, name: 'New' });
  expect(api.mock.calls[1]![1].path).toBe(root + '/price-plans/' + FRESH);
});
it.each(['id', 'generation', 'company', 'read'])(
  'rejects an unverified %s pricing save',
  async (kind) => {
    api.mockImplementation(async (_endpoint, request) => {
      if (request.method === 'PATCH')
        return {
          id: kind === 'id' ? FRESH : RECORD,
          row_version: 5,
          policy_generation: kind === 'generation' ? 0 : 8,
          source_version: 3,
        } as never;
      if (kind === 'read') throw { status: 403, message: 'Protected' };
      return {
        ...row('price-plans'),
        company_id: kind === 'company' ? FRESH : COMPANY,
        row_version: 5,
      } as never;
    });
    await expect(
      pricingCommand({
        path: root + '/price-plans/' + RECORD,
        method: 'PATCH',
        body: {},
      }),
    ).rejects.toMatchObject({ status: 502 });
  },
);
