import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { DisplayConfigProvider, PermissionProvider } from '@janso/ui';
import { TenantDirectory } from '../app/platform/tenants/TenantDirectory';
const { fetcher, navigate } = vi.hoisted(() => ({ fetcher: vi.fn(), navigate: vi.fn() }));
vi.mock('../app/lib/navigate', () => ({ goTo: navigate, signInUrl: () => 'http://localhost:4310/login' }));
vi.mock('../app/lib/session-fetch', () => ({ sessionFetch: fetcher }));
const id = '01900000-0000-7000-8000-000000000001';
const tenant = { id, name: 'Acme Books', slug: 'acme-books', status: 'active', created_at: '2026-10-20T10:00:00Z', updated_at: '2026-10-20T10:00:00Z' };
const detail = { ...tenant, primary_contact_email: 'owner@example.invalid', default_country_code: 'IN', default_currency_code: 'INR', default_timezone: 'Asia/Kolkata', default_locale: 'en', suspended_reason: null };
const permissions = ['platform.tenant.read', 'platform.tenant.create', 'platform.config.manage', 'platform.tenant.suspend'];
const page = (items = [tenant], next: string | null = null) => Response.json({ items, page: { next_cursor: next, has_more: !!next } });
function show(grants = permissions, ownTenantId?: string) {
  return render(<DisplayConfigProvider><PermissionProvider permissions={grants}><TenantDirectory permissions={grants} ownTenantId={ownTenantId} /></PermissionProvider></DisplayConfigProvider>);
}
beforeEach(() => {
  fetcher.mockReset(); navigate.mockReset(); window.history.replaceState({}, '', '/platform/tenants');
  fetcher.mockImplementation(async (_url, init) => {
    const request = JSON.parse(init.body);
    if (request.path.endsWith('tenant-options')) return Response.json({ countries: [{ code: 'IN', name: 'India' }], currencies: [{ code: 'INR', name: 'Indian rupee' }], timezones: [{ code: 'Asia/Kolkata', name: 'Asia/Kolkata' }, { code: 'UTC', name: 'UTC' }], languages: [{ code: 'en', name: 'English' }, { code: 'hi', name: 'Hindi' }] });
    return request.path.includes('?') ? page() : Response.json(detail);
  });
});
it('renders tenant summaries and keeps sign-in recovery out of successful pages', async () => {
  show(); expect(await screen.findByText('Acme Books')).toBeInTheDocument();
  expect(screen.getByRole('table', { name: 'Platform tenants' })).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'New tenant' })).toBeInTheDocument();
  expect(screen.queryByRole('link', { name: 'Sign in again' })).not.toBeInTheDocument();
});
it('opens tenant-administrator management from the tenant kebab with explicit platform access', async () => {
  show([...permissions, 'platform.tenant_access.read']); await screen.findByText('Acme Books');
  await userEvent.click(screen.getByRole('button', { name: /Actions.*Acme/ }));
  await userEvent.click(screen.getByRole('menuitem', { name: 'Manage tenant administrators' }));
  expect(navigate).toHaveBeenCalledWith('/platform/access/administrators?tenant=' + id);
});
it('withholds the administrator kebab without its grant and for the operating workspace', async () => {
  show([...permissions, 'platform.tenant_access.read'], id); await screen.findByText('Acme Books');
  await userEvent.click(screen.getByRole('button', { name: /Actions.*Acme/ }));
  expect(screen.queryByRole('menuitem', { name: 'Manage tenant administrators' })).not.toBeInTheDocument();
});
it('opens View details as a full page and retains directory filters', async () => {
  show(); await screen.findByText('Acme Books');
  await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Status' }), 'active');
  await userEvent.click(screen.getByRole('button', { name: /Actions.*Acme/ }));
  await userEvent.click(screen.getByRole('menuitem', { name: 'View details' }));
  expect(navigate).toHaveBeenCalledWith(expect.stringContaining(`/platform/tenants/${id}?returnTo=`));
  expect(new URL(navigate.mock.lastCall![0], 'http://localhost').searchParams.get('returnTo')).toContain('status=active');
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
});
it('places shared back navigation and breadcrumbs before the tenant title', async () => {
  show(); await screen.findByText('Acme Books');
  const back = screen.getByRole('link', { name: 'Back to platform administration' });
  expect(back).toHaveAttribute('href', '/platform'); expect(back.querySelector('svg')).not.toBeNull();
  expect(within(screen.getByRole('navigation', { name: 'Breadcrumb' })).getByText('Tenants')).toHaveAttribute('aria-current', 'page');
  expect(back.compareDocumentPosition(screen.getByRole('heading', { level: 1, name: 'Tenants' })) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});
it('provides an accessible refresh icon and reloads the directory', async () => {
  show(); await screen.findByText('Acme Books');
  const refresh = screen.getByRole('button', { name: 'Refresh tenants' });
  expect(refresh).toHaveAttribute('title', 'Refresh tenants');
  expect(refresh.querySelector('svg')).not.toBeNull();
  const before = fetcher.mock.calls.length;
  await userEvent.click(refresh);
  await waitFor(() => expect(fetcher.mock.calls.length).toBeGreaterThan(before));
});
it('links creation and editing to dedicated pages while retaining list state', async () => {
  show(); await screen.findByText('Acme Books');
  await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Status' }), 'active');
  const link = screen.getByRole('link', { name: 'New tenant' });
  expect(link).toHaveAttribute('href', expect.stringContaining('/platform/tenants/new?returnTo='));
  expect(new URL(link.getAttribute('href')!, 'http://localhost').searchParams.get('returnTo')).toContain('status=active');
  await userEvent.click(screen.getByRole('button', { name: /Actions.*Acme/ }));
  await userEvent.click(screen.getByRole('menuitem', { name: 'Edit details' }));
  expect(navigate).toHaveBeenCalledWith(expect.stringContaining(`/platform/tenants/${id}/edit?returnTo=`));
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
});
it('searches on the server and resets cursors for sort changes', async () => {
  show(); await screen.findByText('Acme Books');
  await userEvent.type(screen.getByRole('searchbox', { name: 'Search tenants' }), 'Acme');
  await waitFor(() => expect(JSON.parse(fetcher.mock.lastCall![1].body).path).toContain('q=Acme'));
  await userEvent.click(screen.getByRole('button', { name: /Created/ }));
  await waitFor(() => expect(JSON.parse(fetcher.mock.lastCall![1].body).path).toContain('sort=-created_at'));
});
it('walks signed next and previous cursors', async () => {
  fetcher.mockImplementation(async (_url, init) => JSON.parse(init.body).path.includes('cursor=') ? page([{ ...tenant, name: 'Beta Books' }]) : page([tenant], 'signed-cursor'));
  show(); await screen.findByText('Acme Books');
  await userEvent.click(screen.getByRole('button', { name: 'Next page of tenants' }));
  expect(await screen.findByText('Beta Books')).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Previous page of tenants' }));
  expect(await screen.findByText('Acme Books')).toBeInTheDocument();
});
it.each([401, 403, 422, 500])('provides a deliberate error state for %i', async status => {
  fetcher.mockImplementation(async () => Response.json({ error: { message: 'Directory unavailable' } }, { status })); show();
  expect(await screen.findByRole('alert')).toHaveTextContent('Directory unavailable');
  expect(screen.queryByRole('link', { name: 'Sign in again' }) !== null).toBe(status === 401);
});
it('hides mutation controls for read-only operators', async () => {
  show(['platform.tenant.read']); await screen.findByText('Acme Books');
  expect(screen.queryByRole('link', { name: 'New tenant' })).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: /Actions.*Acme/ }));
  expect(screen.getByRole('menuitem', { name: 'View details' })).toBeInTheDocument();
  expect(screen.queryByRole('menuitem', { name: 'Edit details' })).not.toBeInTheDocument();
});
it('does not offer a stale invitation for an active administrator', async () => {
  show(); await screen.findByText('Acme Books');
  await userEvent.click(screen.getByRole('button', { name: /Actions.*Acme/ }));
  expect(screen.queryByRole('menuitem', { name: 'Administrator invitation' })).not.toBeInTheDocument();
});
it('requires a reason before suspension and blocks suspension of the operating workspace', async () => {
  show(permissions, id); await screen.findByText('Acme Books');
  await userEvent.click(screen.getByRole('button', { name: /Actions.*Acme/ }));
  expect(screen.getByRole('menuitem', { name: /Deactivate tenant/ })).toHaveAttribute('aria-disabled', 'true');
});
