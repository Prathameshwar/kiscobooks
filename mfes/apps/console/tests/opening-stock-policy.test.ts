import { expect, it } from 'vitest';
import { allowedOpeningRequest as allow } from '../app/lib/opening-stock-policy';
import { COMPANY, CONTROL, ITEM } from './opening-stock-fixtures';
const root = `/v1/companies/${COMPANY}/stock/openings`;
it.each([
  'readiness',
  'capabilities',
  `${CONTROL}`,
  `${CONTROL}/manifest`,
  `${CONTROL}/reconciliation`,
  `${CONTROL}/accounting-preview`,
  `${CONTROL}/cohorts?include_reversed=false&item_id=${ITEM}&limit=200`,
  `${CONTROL}/revisions?sort=-id`,
  `${CONTROL}/export?token=signed`,
])('allows bounded opening read %s', (path) =>
  expect(allow('accounting', 'GET', `${root}/${path}`)).toBe(true),
);
it.each([
  '',
  '/calculate',
  '/confirm-zero',
  '/adopt',
  `/${CONTROL}/replace`,
  `/${CONTROL}/reopen`,
  `/${CONTROL}/finalize`,
])('allows only defined company commands %s', (path) =>
  expect(allow('accounting', 'POST', root + path)).toBe(true),
);
it.each([
  `${CONTROL}/cohorts?limit=201`,
  `${CONTROL}/cohorts?limit=0`,
  `${CONTROL}/cohorts?limit=25&limit=50`,
  `${CONTROL}/cohorts?company_id=${COMPANY}`,
  `${CONTROL}/revisions?include_reversed=true`,
  `${CONTROL}/export?token=x&extra=1`,
  `${CONTROL}/manifest?token=x`,
  `${CONTROL}/cohorts?cursor=%0a`,
  `../openings/readiness`,
  '%2e%2e/openings/readiness',
  'readiness#fragment',
  'readiness\n',
  `${CONTROL}/destroy`,
])('rejects malformed or expanded request %s', (path) =>
  expect(allow('accounting', 'GET', `${root}/${path}`)).toBe(false),
);
it('does not expose stock posting or arbitrary services', () => {
  expect(
    allow('accounting', 'POST', `/v1/companies/${COMPANY}/stock/postings`),
  ).toBe(false);
  expect(allow('identity', 'GET', root + '/readiness')).toBe(false);
  expect(allow('accounting', 'DELETE', root + '/' + CONTROL)).toBe(false);
  expect(
    allow('accounting', 'GET', 'https://evil.test' + root + '/readiness'),
  ).toBe(false);
});
it('allows only bounded Catalog conversion reads', () => {
  const bindings = `/v1/companies/${COMPANY}/items/${ITEM}/unit-bindings`;
  expect(allow('catalog', 'GET', bindings + '?limit=50')).toBe(true);
  expect(allow('catalog', 'GET', bindings + '?limit=50&as_of=2026-04-01')).toBe(false);
  const path = `/v1/companies/${COMPANY}/item-unit-bindings/${ITEM}/revisions`;
  expect(allow('catalog', 'GET', path + '?as_of=2026-04-01&limit=200')).toBe(
    true,
  );
  expect(allow('catalog', 'POST', path)).toBe(false);
  expect(allow('catalog', 'GET', path + '?q=anything')).toBe(false);
});
it.each([
  'template',
  CONTROL,
  `${CONTROL}/report-ticket`,
  `${CONTROL}/report?token=signed`,
])('allows import evidence %s', (path) =>
  expect(
    allow(
      'vouchers',
      'GET',
      `/v1/companies/${COMPANY}/stock-opening-imports/${path}`,
    ),
  ).toBe(true),
);
