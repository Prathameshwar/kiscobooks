import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { TenantLifecycleDialog } from '../app/platform/tenants/TenantLifecycleDialog';
import { TenantDetail } from '../app/platform/tenants/TenantDetail';
const { call } = vi.hoisted(() => ({ call: vi.fn() }));
vi.mock('../app/lib/platform-api', async () => ({ ...(await vi.importActual('../app/lib/platform-api')), platformCall: call }));
vi.mock('../app/components/PlatformHistory', () => ({ PlatformHistory: () => <p>Audit history</p> }));
const id = '01900000-0000-7000-8000-000000000001', stamp = '2026-10-26T00:00:00Z';
const tenant = { id, name: 'Acme', slug: 'acme', status: 'active', created_at: stamp, updated_at: stamp, default_country_code: 'IN', default_currency_code: 'INR', default_locale: 'en', default_timezone: 'Asia/Kolkata', suspended_reason: null };
beforeEach(() => { call.mockReset(); call.mockImplementation((_path, method) => Promise.resolve(method === 'POST' ? { ...tenant, status: 'suspended', updated_at: '2026-10-26T00:01:00Z' } : tenant)); });
it('offers activation and administrator navigation on tenant details while protecting its own workspace', async () => {
  const grants = ['platform.tenant.read', 'platform.tenant.suspend', 'platform.tenant_access.read'];
  const view = render(<TenantDetail tenantId={id} permissions={grants} />);
  await screen.findByRole('button', { name: 'Deactivate tenant' });
  expect(screen.getByRole('link', { name: 'Manage tenant administrators' })).toHaveAttribute('href', '/platform/access/administrators?tenant=' + id);
  view.unmount(); render(<TenantDetail tenantId={id} ownTenantId={id} permissions={grants} />);
  expect(await screen.findByRole('button', { name: 'Deactivate tenant' })).toBeDisabled();
  expect(screen.queryByRole('link', { name: 'Manage tenant administrators' })).not.toBeInTheDocument();
});
it('validates reason and sends the displayed revision with a replay key', async () => {
  const changed = vi.fn(), close = vi.fn();
  render(<TenantLifecycleDialog tenant={tenant} returnTo="/platform/tenants" onClose={close} onChanged={changed} onReview={vi.fn()} />);
  await userEvent.click(screen.getByRole('button', { name: 'Deactivate tenant' }));
  expect(call).not.toHaveBeenCalled(); expect(screen.getByText(/Enter a reason with 3/)).toBeInTheDocument();
  await userEvent.type(screen.getByRole('textbox', { name: 'Reason' }), 'Access review');
  await userEvent.click(screen.getByRole('button', { name: 'Deactivate tenant' }));
  expect(call.mock.calls[0][2]).toEqual({ status: 'suspended', reason: 'Access review', expected_updated_at: stamp });
  expect(call.mock.calls[0][3]).toEqual(expect.any(String));
  expect(changed).toHaveBeenCalledWith(expect.stringContaining('Tenant deactivated')); expect(close).toHaveBeenCalled();
});
it('retries an uncertain result with exactly the same request and key', async () => {
  call.mockRejectedValueOnce({ status: 503, message: 'Result unavailable' }).mockResolvedValueOnce({ ...tenant, status: 'suspended' });
  render(<TenantLifecycleDialog tenant={tenant} returnTo="/platform/tenants" onClose={vi.fn()} onChanged={vi.fn()} onReview={vi.fn()} />);
  await userEvent.type(screen.getByRole('textbox', { name: 'Reason' }), 'Access review');
  await userEvent.click(screen.getByRole('button', { name: 'Deactivate tenant' }));
  await userEvent.click(await screen.findByRole('button', { name: 'Retry same request' }));
  expect(call.mock.calls[1][2]).toEqual(call.mock.calls[0][2]); expect(call.mock.calls[1][3]).toEqual(call.mock.calls[0][3]);
});
it('offers refresh after a conflict and does not claim success', async () => {
  call.mockRejectedValue({ status: 409, message: 'Tenant changed' }); const review = vi.fn(), changed = vi.fn();
  render(<TenantLifecycleDialog tenant={tenant} returnTo="/platform/tenants" onClose={vi.fn()} onChanged={changed} onReview={review} />);
  await userEvent.type(screen.getByRole('textbox', { name: 'Reason' }), 'Access review'); await userEvent.click(screen.getByRole('button', { name: 'Deactivate tenant' }));
  await userEvent.click(await screen.findByRole('button', { name: 'Refresh and review' })); expect(review).toHaveBeenCalled(); expect(changed).not.toHaveBeenCalled();
});
