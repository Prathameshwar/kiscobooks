import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DisplayConfigProvider, PermissionProvider } from '@janso/ui';
import { beforeEach, expect, it, vi } from 'vitest';
import { ProductConfigurationDirectory } from '../app/components/ProductConfigurationDirectory';
import { ProductConfigurationEditor } from '../app/components/ProductConfigurationEditor';
import { ProductConfigurationDetail } from '../app/components/ProductConfigurationDetail';
import { ProductConfigurationAdoption } from '../app/components/ProductConfigurationInspect';
import { serviceCall } from '../app/lib/service-call';
import { goTo } from '../app/lib/navigate';
import { COMPANY, DRAFT, SCOPE, ITEM, response, scope, revision, page } from './product-configuration-fixtures';

vi.mock('../app/lib/service-call', async original => ({ ...await original<typeof import('../app/lib/service-call')>(), serviceCall: vi.fn() }));
vi.mock('../app/lib/navigate', () => ({ goTo: vi.fn(), signInUrl: () => '/signin' }));
const writes = () => vi.mocked(serviceCall).mock.calls.filter(([, request]) => ['POST', 'PATCH'].includes(request.method ?? 'GET'));
function wrap(node: React.ReactNode) { return render(<PermissionProvider permissions={[]}><DisplayConfigProvider config={{ timezone: 'Asia/Kolkata', currency: 'INR' }}>{node}</DisplayConfigProvider></PermissionProvider>); }
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => response(request.path, request.method) as never);
});

it('creates the first company draft directly without choosing or writing a scope first', async () => {
  vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => request.path.includes('/product-configuration-scopes?') ? { items: [], page: { has_more: false } } as never : response(request.path, request.method) as never);
  wrap(<ProductConfigurationEditor company={COMPANY} timezone="Asia/Kolkata" />);
  await userEvent.type(await screen.findByRole('textbox', { name: 'Reason for change' }), 'Initial company configuration');
  expect(writes()).toHaveLength(0);
  expect(screen.queryByRole('combobox', { name: /scope|applies to/i })).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Save draft' }));
  await waitFor(() => expect(goTo).toHaveBeenCalled());
  expect(writes()).toHaveLength(1);
  expect(writes()[0][1]).toMatchObject({ path: `/v1/companies/${COMPANY}/product-configurations/company`, method: 'POST' });
  expect(writes()[0][1].body).not.toHaveProperty('scope_id');
  expect(writes()[0][1].body).not.toHaveProperty('scope_kind');
});

it('shows the company draft and direct edit and review actions without an ownership filter', async () => {
  wrap(<ProductConfigurationDirectory company={COMPANY} canManage canPublish initialQuery="scope_kind=GROUP&group_id=retired&returnTo=%2Fsettings" />);
  expect(await screen.findByRole('link', { name: 'Edit company configuration' })).toHaveAttribute('href', expect.stringContaining(`/drafts/${DRAFT}/edit`));
  expect(screen.getByRole('heading', { level: 3, name: 'Company product defaults' })).toBeVisible();
  expect(screen.getByRole('link', { name: 'Review and publish' })).toHaveAttribute('href', expect.stringContaining(`/drafts/${DRAFT}`));
  expect(screen.queryByRole('combobox', { name: 'Scope filter' })).not.toBeInTheDocument();
  expect(vi.mocked(serviceCall).mock.calls.some(([, request]) => /group_id=|scope_kind=GROUP/.test(request.path))).toBe(false);
});

it('keeps a retired configuration readable with no editing or publication controls', async () => {
  vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => request.path.endsWith(`/product-configuration-scopes/${SCOPE}`) ? { ...scope, scope_kind: 'GROUP' } as never : response(request.path, request.method) as never);
  wrap(<ProductConfigurationDetail company={COMPANY} id={DRAFT} canManage canPublish timezone="Asia/Kolkata" />);
  expect(await screen.findByText(/Retired configuration/)).toBeVisible();
  expect(screen.queryByRole('link', { name: 'Edit draft' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Review publication' })).not.toBeInTheDocument();
  expect(writes()).toHaveLength(0);
});

it('copies the published company settings when preparing the next configuration', async () => {
  vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => request.path.includes('/revisions?') ? { items: [revision], page } as never : response(request.path, request.method) as never);
  wrap(<ProductConfigurationEditor company={COMPANY} timezone="Asia/Kolkata" />);
  expect(await screen.findByRole('combobox', { name: 'Barcode' })).toHaveValue('OPTIONAL');
  expect(screen.getByRole('combobox', { name: 'Enable barcode by default' })).toHaveValue('true');
  expect(screen.getByRole('textbox', { name: 'Reason for change' })).toHaveValue('');
  expect(screen.getByLabelText('Effective from')).toHaveValue('2028-01-02');
  expect(writes()).toHaveLength(0);
});

it('shows published history to readers without configuration write actions', async () => {
  vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => request.path.includes('/revisions?') ? { items: [revision], page } as never : request.path.includes('/drafts?') ? { items: [], page } as never : response(request.path, request.method) as never);
  wrap(<ProductConfigurationDirectory company={COMPANY} canManage={false} />);
  expect(await screen.findByRole('link', { name: 'View published revision 1' })).toBeVisible();
  expect(screen.getByRole('link', { name: 'Publication history' })).toBeVisible();
  expect(screen.queryByRole('link', { name: 'Edit company configuration' })).not.toBeInTheDocument();
  expect(screen.queryByRole('link', { name: 'Review and publish' })).not.toBeInTheDocument();
});

it('refuses a protected or wrong-owner company summary instead of offering a fresh configuration', async () => {
  vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => request.path.includes('/product-configuration-scopes?') ? { items: [{ id: SCOPE, scope_kind: 'COMPANY' }], page } as never : response(request.path, request.method) as never);
  wrap(<ProductConfigurationDirectory company={COMPANY} canManage />);
  expect(await screen.findByText('The company configuration is unavailable or protected.')).toBeVisible();
  expect(screen.queryByRole('link', { name: 'Create company configuration' })).not.toBeInTheDocument();
  expect(writes()).toHaveLength(0);
});

it.each([undefined, 1, 3])('rejects adoption previews that cannot confirm Company-only resolution (%s)', async resolutionVersion => {
  vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => request.path.includes('/configuration-adoption/preview') ? { ...response(request.path), resolution_version: resolutionVersion } as never : response(request.path, request.method) as never);
  wrap(<ProductConfigurationAdoption company={COMPANY} canAdopt timezone="Asia/Kolkata" initialItemId={ITEM} />);
  await userEvent.click(screen.getByRole('button', { name: 'Review adoption' }));
  expect(await screen.findByText('The product adoption review could not be verified.')).toBeVisible();
  expect(screen.queryByRole('button', { name: 'Adopt reviewed draft defaults' })).not.toBeInTheDocument();
  expect(writes()).toHaveLength(0);
});
