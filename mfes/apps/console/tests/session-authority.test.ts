import { expect, it } from 'vitest';
import { organisationPermissions, canAdministerOrganisation } from '../app/lib/session-authority';
const grant = (scope_type: string, permissions = ['notification.provider.read']) => ({ permissions, scope_type, scope_id: null, valid_from: '2020-01-01', valid_to: null });
it('does not promote company, department or missing grants into organisation authority', () => {
  for (const grants of [undefined, [], [grant('company')], [grant('department')]]) {
    expect(organisationPermissions({ grants })).toEqual([]);
    expect(canAdministerOrganisation({ grants })).toBe(false);
  }
});
it('keeps only active tenant grants and deduplicates their keys', () => {
  const grants = [grant('tenant'), grant('tenant'), { ...grant('tenant', ['role.read']), valid_to: '2022-01-01' }, { ...grant('tenant', ['company.create']), valid_from: '2099-01-01' }];
  expect(organisationPermissions({ grants }, '2026-10-23')).toEqual(['notification.provider.read']);
  expect(canAdministerOrganisation({ grants })).toBe(true);
});
