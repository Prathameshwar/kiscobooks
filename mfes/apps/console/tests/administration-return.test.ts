import { expect, it } from 'vitest';
import { administrationDirectoryReturn, administrationLink, administrationReturn } from '../app/lib/administration-navigation';
import { roleId, userId } from './access-fixtures';
it.each(['https://evil.invalid/users', '//evil.invalid/users', '/users/new', '/users/' + userId + '/edit', '/users?returnTo=//evil.invalid', '/users?status=made-up&limit=0&sort=secret', '/users?q=%0Aevil'].map(value => ({ value })))('rejects unsupported returns or query values: $value', ({ value }) => {
  expect(administrationReturn('users', value)).toBe('/users');
});
it('retains a bounded role-to-assignment-to-user navigation chain and directory filters', () => {
  const directory = '/roles?q=View&limit=25', role = administrationLink('/roles/' + roleId, directory), assignments = administrationLink('/assignments?role_id=' + roleId, role), user = administrationLink('/users/' + userId, assignments);
  expect(administrationReturn('users', assignments)).toBe(assignments);
  expect(administrationLink('/users/' + userId + '/edit', user)).toContain('returnTo=');
  expect(administrationDirectoryReturn('roles', user)).toBe(directory);
});
it('reuses the existing detail on successful editing without creating a back-to-self loop', () => {
  const detail = administrationLink('/roles/' + roleId, '/roles?q=View');
  expect(administrationLink('/roles/' + roleId, detail)).toBe(detail);
});
it('resets opaque cursors while retaining supported filters on a return', () => {
  expect(administrationReturn('departments', '/departments?q=OP&limit=25&is_active=true&cursor=opaque&sort=code')).toBe('/departments?q=OP&limit=25&is_active=true&sort=code');
});
it('preserves an assignment origin when reviewing new subject filters', () => {
  const role = administrationLink('/roles/' + roleId, '/roles?q=View');
  const assignments = administrationLink('/assignments?role_id=' + roleId, role);
  const review = administrationLink('/assignments?subject_type=user&subject_id=' + userId, assignments);
  expect(new URL(review, 'https://console.invalid').searchParams.get('returnTo')).toBe(role);
  expect(review).toContain('subject_id=' + userId);
});
it('bounds return nesting and rejects long values', () => {
  expect(administrationReturn('users', '/users?q=' + 'a'.repeat(5000))).toBe('/users');
  expect(administrationReturn('roles', '/roles?returnTo=' + encodeURIComponent('/roles/' + roleId + '?returnTo=https://evil.invalid'))).not.toContain('evil.invalid');
});
it('accepts only lifecycle filters supported by the destination resource', () => {
  expect(administrationReturn('users', '/users?status=closed')).toBe('/users');
  expect(administrationReturn('companies', '/companies/manage?status=invited')).toBe('/companies/manage');
  expect(administrationReturn('tenants', '/platform/tenants?status=deactivated')).toBe('/platform/tenants');
  expect(administrationReturn('users', '/users?status=invited')).toBe('/users?status=invited');
});
