import { expect, it } from 'vitest';
import { companyBootstrapAccess } from '../app/lib/company-bootstrap';
import type { Session } from '../app/session';

const keys = ['accounting.finance.read', 'accounting.finance.initialize', 'period.read', 'period.manage', 'warehouse.read', 'warehouse.manage', 'price_plan.read', 'price_plan.manage', 'item_group.read', 'product_type.read', 'item_group.manage', 'tax_rule.read', 'tax_rule.manage', 'tax_rule.publish', 'unit.read', 'unit.manage', 'pack_type.read', 'pack_type.manage', 'vouchers.read', 'vouchers.type.manage'];
function grants(permissions: string[], scope_type = 'tenant', valid_to: string | null = null): Pick<Session, 'grants'> {
  return { grants: [{ permissions, scope_type, scope_id: null, valid_from: '2020-01-01', valid_to }] };
}
it('uses current tenant-wide authority for each independent owner step', () => {
  expect(companyBootstrapAccess(grants(keys))).toEqual({ chart: true, books: true, warehouses: true, pricing: true, productGroup: true, tax: true, units: true, packs: true, vouchers: true });
});
it.each(['company', 'department'])('does not borrow %s grants for a new company', scope => {
  expect(Object.values(companyBootstrapAccess(grants(keys, scope))).every(value => !value)).toBe(true);
});
it('does not borrow expired grants', () => {
  expect(Object.values(companyBootstrapAccess(grants(keys, 'tenant', '2020-01-02'))).every(value => !value)).toBe(true);
});
it('initializes the chart without needing period or arbitrary master authority', () => {
  const result = companyBootstrapAccess(grants(['accounting.finance.read', 'accounting.finance.initialize']));
  expect(result.chart).toBe(true); expect(result.books).toBe(false);
  expect(companyBootstrapAccess(grants(['accounting.setup.read', 'accounting.setup.manage'])).chart).toBe(true);
});
it('requires both read and manage keys on Catalog bootstrap steps', () => {
  const result = companyBootstrapAccess(grants(['warehouse.manage', 'price_plan.manage', 'item_group.manage']));
  expect(result.warehouses).toBe(false); expect(result.pricing).toBe(false); expect(result.productGroup).toBe(false);
});
it('plans the fixed company administrator bootstrap only for an authorised new-company creator', () => {
  const creator = grants(['company.create']);
  expect(companyBootstrapAccess(creator, { creating: true })).toEqual({ chart: true, books: true, warehouses: true, pricing: true, productGroup: true, tax: true, units: true, packs: true, vouchers: true });
  expect(Object.values(companyBootstrapAccess(creator)).every(value => !value)).toBe(true);
  for (const scope of ['company', 'department', 'platform']) {
    expect(Object.values(companyBootstrapAccess(grants(['company.create'], scope), { creating: true })).every(value => !value)).toBe(true);
  }
  expect(Object.values(companyBootstrapAccess(grants(['company.create'], 'tenant', '2020-01-02'), { creating: true })).every(value => !value)).toBe(true);
});
