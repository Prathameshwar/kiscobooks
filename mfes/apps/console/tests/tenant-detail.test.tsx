import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import userEvent from '@testing-library/user-event';
import { TenantDetail } from '../app/platform/tenants/TenantDetail';
const { call } = vi.hoisted(() => ({ call: vi.fn() }));
vi.mock('../app/lib/platform-api', async () => ({ ...await vi.importActual('../app/lib/platform-api'), platformCall: call }));
const id = '01900000-0000-7000-8000-000000000001';
const detail = { id, name: 'Acme books', status: 'active', primary_contact_email: 'owner@example.invalid', default_country_code: 'IN', default_state_code: 'IN-MH', default_currency_code: 'INR', default_timezone: 'Asia/Kolkata', default_locale: 'en', created_at: '2026-10-21T00:00:00Z', updated_at: '2026-10-21T00:00:00Z', suspended_reason: null };
const options = { countries: [{ code: 'IN', name: 'India' }], states: [{ code: 'IN-MH', name: 'Maharashtra', country_code: 'IN' }], currencies: [{ code: 'INR', name: 'Indian Rupee' }], languages: [{ code: 'en', name: 'English' }], timezones: [{ code: 'Asia/Kolkata', name: 'Asia/Kolkata' }] };
beforeEach(() => { call.mockReset(); call.mockImplementation((path: string) => Promise.resolve(path.endsWith('tenant-options') ? options : detail)); });
it('shows labelled full-page details, safe back state and an authorized edit link', async () => {
 render(<TenantDetail tenantId={id} permissions={['platform.config.manage']} returnTo="/platform/tenants?status=active" />);
 expect(await screen.findByRole('heading', { name: 'Acme books' })).toBeInTheDocument();
 expect(screen.getByText('Maharashtra')).toBeInTheDocument(); expect(screen.getByText('India')).toBeInTheDocument();
 expect(screen.getByRole('link', { name: 'Back to tenants' })).toHaveAttribute('href', '/platform/tenants?status=active');
 expect(screen.getByRole('link', { name: 'Edit details' })).toHaveAttribute('href', expect.stringContaining('/edit'));
 expect(screen.queryByText(/workspace-/)).not.toBeInTheDocument();
});
it('retains stored codes when optional labels cannot load and hides editing for closed tenants', async () => {
 call.mockImplementation((path: string) => path.endsWith('tenant-options') ? Promise.reject({ status: 503 }) : Promise.resolve({ ...detail, status: 'closed' }));
 render(<TenantDetail tenantId={id} permissions={['platform.config.manage']} returnTo="https://evil.invalid" />);
 expect(await screen.findByText('IN-MH')).toBeInTheDocument(); expect(screen.queryByRole('link', { name: 'Edit details' })).not.toBeInTheDocument();
 expect(screen.getByRole('link', { name: 'Back to tenants' })).toHaveAttribute('href', '/platform/tenants');
});
it.each([401,403,404,503])('handles detail error %s and retries outages', async status => {
 call.mockRejectedValue({ status, message: status === 404 ? 'Tenant not found.' : 'Unable to load tenant.' });
 render(<TenantDetail tenantId={id} permissions={[]} />);
 expect(await screen.findByRole('alert')).toBeInTheDocument();
 if (status === 401) expect(screen.getByRole('link', { name: 'Sign in again' })).toBeInTheDocument();
 if (status === 503) { call.mockResolvedValue(detail); await userEvent.click(screen.getByRole('button', { name: 'Try again' })); await waitFor(() => expect(screen.getByRole('heading', { name: 'Acme books' })).toBeInTheDocument()); }
});
