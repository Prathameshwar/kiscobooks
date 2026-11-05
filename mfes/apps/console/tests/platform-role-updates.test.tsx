import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { PlatformRoleUpdates } from '../app/components/PlatformRoleUpdates';
import Page from '../app/platform/system-roles/page';
import { pageContext } from '../app/lib/page-context';
import { serviceCall } from '../app/lib/service-call';
import { allowedPlatformRequest } from '../app/lib/platform-request';
import { companyContextFor, sessionFor } from './helpers';

vi.mock('../app/lib/service-call', async original => ({ ...await original<typeof import('../app/lib/service-call')>(), serviceCall: vi.fn() }));
vi.mock('../app/lib/page-context', () => ({ pageContext: vi.fn() }));
vi.mock('../app/providers', () => ({ Providers: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/components/ConsoleShell', () => ({ ConsoleShell: ({ children }: { children: React.ReactNode }) => children }));
const plan = { current_digest: 'a'.repeat(64), catalogue_digest: 'b'.repeat(64), changes: [{ key: 'tenant_admin', added: ['report.export'], removed: [], metadata_changed: false, deactivate: false }] };
const result = { changed: true, current_digest: 'c'.repeat(64), catalogue_digest: plan.catalogue_digest, added_grants: 1, removed_grants: 0, inserted_roles: 0, updated_roles: 0, deactivated_roles: 0 };
beforeEach(() => { vi.mocked(serviceCall).mockReset(); vi.mocked(serviceCall).mockResolvedValue(plan); });

it('applies only the reviewed fingerprints and reason through the fixed API', async () => {
  vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => request.method === 'POST' ? result as never : plan as never);
  render(<PlatformRoleUpdates />);
  await screen.findByText('Add: report.export');
  fireEvent.change(screen.getByLabelText('Reason for role update'), { target: { value: 'Reviewed permanent report authority' } });
  fireEvent.click(screen.getByRole('button', { name: 'Apply reviewed role updates' }));
  await screen.findByText(/System roles updated/);
  const input = vi.mocked(serviceCall).mock.calls.find(call => call[1].method === 'POST')![1];
  expect(input.path).toBe('/v1/platform/system-roles/reconcile');
  expect(input.key).toBeTruthy();
  expect(input.body).toEqual({ expected_current_digest: plan.current_digest, expected_catalogue_digest: plan.catalogue_digest, reason: 'Reviewed permanent report authority' });
});

it('retries an uncertain update with the identical body and key', async () => {
  let writes = 0;
  vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => {
    if (request.method !== 'POST') return plan as never;
    if (++writes === 1) throw { status: 503, message: 'Connection interrupted' };
    return result as never;
  });
  render(<PlatformRoleUpdates />);
  await screen.findByText('Add: report.export');
  fireEvent.change(screen.getByLabelText('Reason for role update'), { target: { value: 'Reviewed permanent authority' } });
  fireEvent.click(screen.getByRole('button', { name: 'Apply reviewed role updates' }));
  await screen.findByRole('button', { name: 'Retry the same role update' });
  expect(screen.getByLabelText('Reason for role update')).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'Retry the same role update' }));
  await screen.findByText(/System roles updated/);
  const writesMade = vi.mocked(serviceCall).mock.calls.filter(call => call[1].method === 'POST');
  expect(writesMade[1]![1]).toEqual(writesMade[0]![1]);
});

it('keeps application disabled when the preview cannot be verified', async () => {
  vi.mocked(serviceCall).mockResolvedValue({ ...plan, current_digest: 'invalid' });
  render(<PlatformRoleUpdates />);
  await screen.findByRole('button', { name: 'Reload role changes' });
  expect(screen.queryByRole('button', { name: 'Apply reviewed role updates' })).not.toBeInTheDocument();
});

it.each([true, false])('requires platform configuration authority on the page: %s', async permitted => {
  const session = await sessionFor({ permissions: permitted ? ['platform.config.manage'] : ['role.manage', 'report.read'] });
  vi.mocked(pageContext).mockResolvedValue({ session, context: companyContextFor() });
  render(await Page());
  if (permitted) await screen.findByText('Add: report.export');
  else { expect(screen.getByRole('alert')).toBeVisible(); expect(serviceCall).not.toHaveBeenCalled(); }
});

it('allows only the fixed preview and reconcile methods without query overrides', () => {
  expect(allowedPlatformRequest('GET', '/v1/platform/system-roles')).toBe(true);
  expect(allowedPlatformRequest('POST', '/v1/platform/system-roles/reconcile')).toBe(true);
  expect(allowedPlatformRequest('POST', '/v1/platform/system-roles')).toBe(false);
  expect(allowedPlatformRequest('DELETE', '/v1/platform/system-roles/reconcile')).toBe(false);
  expect(allowedPlatformRequest('POST', '/v1/platform/system-roles/reconcile?role=controller')).toBe(false);
});
