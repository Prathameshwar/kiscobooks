import { expect, it } from 'vitest';
import { accessReviewPermissions } from '../app/lib/access-permissions';
import { sessionFor } from './helpers';

it('offers scoped access administration without flattening business or composition authority', async () => {
  const session = await sessionFor();
  session.permissions = ['company.read'];
  session.grants = [{ scope_type: 'department', scope_id: 'department', valid_from: '2026-10-01', valid_to: '2026-10-22', permissions: ['role.read', 'role.assign', 'role.manage', 'ledger.post_journal'] }];
  expect(accessReviewPermissions(session, '2026-10-22')).toEqual(['company.read', 'role.read', 'role.assign']);
  expect(session.permissions).toEqual(['company.read']);
});

it('excludes future and expired grants and wildcard permissions', async () => {
  const session = await sessionFor(); session.permissions = [];
  session.grants = [
    { scope_type: 'company', scope_id: 'company', valid_from: '2026-10-23', valid_to: null, permissions: ['role.read'] },
    { scope_type: 'department', scope_id: 'department', valid_from: '2026-10-01', valid_to: '2026-10-21', permissions: ['role.assign'] },
    { scope_type: 'tenant', scope_id: null, valid_from: '2026-10-01', valid_to: null, permissions: ['role.*'] },
  ];
  expect(accessReviewPermissions(session, '2026-10-22')).toEqual([]);
});
