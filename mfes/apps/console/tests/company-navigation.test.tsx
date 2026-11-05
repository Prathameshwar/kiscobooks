import { expect, it } from 'vitest';
import { flattenNavigation, navigationFor } from '../app/nav';
import { sessionFor } from './helpers';
it('keeps unavailable destinations and empty sections absent even for broad readers', async () => {
  const session = await sessionFor({ permissions: ['invoice.read', 'payment.read', 'ledger.read', 'tax.read', 'stock.read'] });
  session.company = { name: 'A', id: 'a' };
  const sections = navigationFor(session);
  expect(sections.map(section => section.label)).toEqual(['Operate', 'Your account']);
  expect(sections.flatMap(section => section.items.map(item => item.href))).toEqual(['/', '/my-access']);
});
it('opens company administration links without disclosing tenant-only directories', async () => {
  const session = await sessionFor({ permissions: ['vouchers.read', 'report.read', 'company.read'] });
  session.company = { name: 'A', id: 'a' };
  session.grants = [{ permissions: session.permissions, scope_type: 'company', scope_id: 'a', valid_from: '2020-01-01', valid_to: null }];
  const paths = navigationFor(session).flatMap(section => flattenNavigation(section.items).map(item => item.href));
  expect(paths).toContain('/vouchers'); expect(paths).toContain('/reports'); expect(paths).toContain('/organisation'); expect(paths).toContain('/companies/manage'); for (const path of ['/user-groups', '/platform', '/users']) expect(paths).not.toContain(path);
});
it('removes company work when no company is open but retains active organisation authority', async () => {
  const session = await sessionFor({ permissions: ['report.read', 'company.read'] });
  session.grants = [{ permissions: ['company.read'], scope_type: 'tenant', scope_id: null, valid_from: '2020-01-01', valid_to: null }];
  const paths = navigationFor(session).flatMap(section => flattenNavigation(section.items).map(item => item.href));
  expect(paths).not.toContain('/reports'); expect(paths).toContain('/organisation');
});
it('offers organisation people administration to a tenant user-directory administrator', async () => {
  const session = await sessionFor({ permissions: ['user.read', 'role.assign'] });
  session.grants = [{ permissions: session.permissions, scope_type: 'tenant', scope_id: null, valid_from: '2020-01-01', valid_to: null }];
  expect(navigationFor(session).flatMap(section => flattenNavigation(section.items).map(item => item.href))).toContain('/organisation');
});
