import { expect, it } from 'vitest';
import { flattenNavigation, navigationFor } from '../app/nav';
import { showNewVoucher } from '../app/lib/new-voucher-actions';
import { sessionFor } from './helpers';

const company = '01990000-0000-7000-8000-000000000001';
const keys = ['vouchers.read', 'vouchers.create', 'design.template.read'];
const paths = ['/operate/income', '/operate/expense', '/operate/inventory', '/vouchers', '/invoice-designer', '/documents/vouchers'];
it.each(['other-company', 'expired', 'future', 'department', 'missing', 'no-company'])('hides every voucher destination and New for %s authority', async scenario => {
  const session = await sessionFor({ permissions: keys });
  session.company = { id: scenario === 'no-company' ? undefined : company, name: 'QA' };
  session.grants = scenario === 'missing' ? [] : [{
    scope_type: scenario === 'department' ? 'department' : 'company',
    scope_id: scenario === 'other-company' ? '01990000-0000-7000-8000-000000000002' : company,
    permissions: keys, valid_from: scenario === 'future' ? '2999-01-01' : '2000-01-01',
    valid_to: scenario === 'expired' ? '2001-01-01' : null,
  }];
  const destinations = flattenNavigation(navigationFor(session).flatMap(section => section.items)).map(item => item.href);
  for (const path of paths) expect(destinations).not.toContain(path);
  expect(showNewVoucher(session)).toBe(false);
});
it.each(['tenant', 'company'] as const)('shows voucher navigation and New for current %s grants', async scope_type => {
  const session = await sessionFor({ permissions: keys });
  session.company = { id: company, name: 'QA' };
  session.grants = [{ scope_type, scope_id: scope_type === 'tenant' ? null : company, permissions: keys, valid_from: '2000-01-01', valid_to: null }];
  const destinations = flattenNavigation(navigationFor(session).flatMap(section => section.items)).map(item => item.href);
  for (const path of paths) expect(destinations).toContain(path);
  expect(showNewVoucher(session)).toBe(true);
});

it.each(['tenant admin', 'company admin', 'company user', 'billing clerk', 'billing approver', 'viewer', 'platform admin'])('uses grants rather than the %s classification', async role => {
  const session = await sessionFor({ permissions: [] });
  session.role = role; session.company = { id: company, name: 'QA' }; session.grants = [];
  expect(showNewVoucher(session)).toBe(false);
  expect(flattenNavigation(navigationFor(session).flatMap(section => section.items)).some(item => item.href === '/vouchers')).toBe(false);
  session.permissions = keys;
  session.grants = [{ scope_type: 'company', scope_id: company, permissions: keys, valid_from: '2000-01-01', valid_to: null }];
  expect(showNewVoucher(session)).toBe(true);
});
