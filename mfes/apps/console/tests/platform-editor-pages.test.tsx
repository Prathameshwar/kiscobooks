import { render, screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import DetailsPage from '../app/platform/details/page';
import PricingPage from '../app/platform/pricing/page';
import NewPage from '../app/platform/tenants/new/page';
import EditPage from '../app/platform/tenants/[tenantId]/edit/page';
import { tenantReturnTo } from '../app/lib/platform-api';
const { session, missing } = vi.hoisted(() => ({ session: vi.fn(), missing: vi.fn(() => { throw new Error('not found'); }) }));
vi.mock('../app/session', () => ({ getSession: session }));
vi.mock('../app/lib/page-context', async () => {
  // Pages resolve the session and the company context through one helper now; the session
  // mock above still decides what that helper returns.
  const { getSession } = await import('../app/session');
  return { pageContext: async () => ({ session: await getSession(),
    context: { companies: [], companiesNote: null, fiscalYears: [], fiscalYear: null, fiscalNote: null } }) };
});
vi.mock('next/navigation', () => ({ notFound: missing }));
vi.mock('../app/providers', () => ({ Providers: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/components/ConsoleShell', () => ({ ConsoleShell: ({ children }: { children: React.ReactNode }) => <div data-testid="console-shell">{children}</div> }));
vi.mock('../app/platform/details/PlatformDetailsForm', () => ({ PlatformDetailsForm: () => <p>Details editor</p> }));
vi.mock('../app/platform/pricing/PricingDirectory', () => ({ PricingDirectory: () => <p>Pricing editor</p> }));
vi.mock('../app/platform/tenants/TenantForm', () => ({ TenantForm: ({ tenantId, returnTo }: { tenantId?: string; returnTo?: string }) => <p>Tenant editor {tenantId ?? 'new'} {returnTo}</p> }));
const id = '01900000-0000-7000-8000-000000000001';
beforeEach(() => { session.mockResolvedValue({ permissions: ['platform.tenant.read', 'platform.tenant.create', 'platform.config.manage'], organisation: { id: 'operator' } }); });
it('renders a protected platform editor', async () => { render(await DetailsPage()); expect(screen.getByText('Details editor')).toBeInTheDocument(); });
it('renders pricing only with platform configuration permission', async () => {
  const view = render(await PricingPage()); expect(screen.getByText('Pricing editor')).toBeInTheDocument(); view.unmount();
  session.mockResolvedValue({ permissions: ['platform.tenant.read'], organisation: { id: 'operator' } });
  render(await PricingPage()); expect(screen.getByRole('alert')).toHaveTextContent('permission is required');
  expect(screen.queryByText('Pricing editor')).not.toBeInTheDocument();
});
it('renders dedicated create and edit routes and passes their return state', async () => {
  const create = render(await NewPage({ searchParams: Promise.resolve({ returnTo: '/platform/tenants?status=active' }) }));
  expect(screen.getByText(/Tenant editor new/)).toHaveTextContent('status=active'); create.unmount();
  render(await EditPage({ params: Promise.resolve({ tenantId: id }), searchParams: Promise.resolve({}) })); expect(screen.getByText(new RegExp(id))).toBeInTheDocument();
});
it('uses the standalone wizard layout for creation and retains the shell for editing', async () => {
  const create = render(await NewPage({ searchParams: Promise.resolve({}) }));
  expect(screen.queryByTestId('console-shell')).not.toBeInTheDocument();
  expect(screen.getByText(/Tenant editor new/)).toBeInTheDocument();
  create.unmount();
  render(await EditPage({ params: Promise.resolve({ tenantId: id }), searchParams: Promise.resolve({}) }));
  expect(screen.getByTestId('console-shell')).toContainElement(screen.getByText(new RegExp(id)));
});
it.each(['details', 'new', 'edit'])('denies the %s editor without permission', async route => {
  session.mockResolvedValue({ permissions: ['platform.tenant.read'], organisation: { id: 'operator' } });
  render(await (route === 'details' ? DetailsPage() : route === 'new' ? NewPage({ searchParams: Promise.resolve({}) }) : EditPage({ params: Promise.resolve({ tenantId: id }), searchParams: Promise.resolve({}) })));
  expect(screen.getByRole('alert')).toHaveTextContent('permission is required'); expect(screen.queryByText(/editor/)).not.toBeInTheDocument();
});
it('rejects malformed object identifiers before rendering an editor', async () => { await expect(EditPage({ params: Promise.resolve({ tenantId: '../details' }), searchParams: Promise.resolve({}) })).rejects.toThrow('not found'); });
it.each(['https://evil.invalid/', '//evil.invalid/platform/tenants', '/platform/tenants/new', '/platform/tenants?email=private', '/platform/tenants#bad', '/platform/tenants\\evil'])('rejects an unsafe directory return path %s', path => { expect(tenantReturnTo(path)).toBe('/platform/tenants'); });
it('preserves allowlisted search, filters, sorting and cursor state', () => { const path = '/platform/tenants?q=Books&status=active&sort=name&limit=50&cursor=opaque'; expect(tenantReturnTo(path)).toBe(path); });
