import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { DisplayConfigProvider } from '@janso/ui';
import { ConfigurationOwner, ProductConfigurationDirectory, ProductConfigurationScope } from '../app/components/ProductConfigurationDirectory';
import { ProductConfigurationAdoption, ProductConfigurationEffective } from '../app/components/ProductConfigurationInspect';
import { ProductConfigurationDetail } from '../app/components/ProductConfigurationDetail';
import { ConfigurationFailure } from '../app/components/ProductConfigurationCommon';
import { serviceCall } from '../app/lib/service-call';
import { COMPANY, DRAFT, ITEM, REVISION, SCOPE, draft, page, response, revision, scope } from './product-configuration-fixtures';

vi.mock('../app/lib/service-call', async original => ({ ...await original<typeof import('../app/lib/service-call')>(), serviceCall: vi.fn() }));
vi.mock('../app/lib/navigate', () => ({ goTo: vi.fn(), signInUrl: () => '/signin' }));
const writes = () => vi.mocked(serviceCall).mock.calls.filter(([, request]) => ['POST', 'PATCH'].includes(request.method ?? 'GET'));
function wrap(node: React.ReactNode) { return render(<DisplayConfigProvider config={{ timezone: 'Asia/Kolkata' }}>{node}</DisplayConfigProvider>); }
async function chooseProduct() {
  await userEvent.click(screen.getByRole('combobox', { name: 'Product / SKU' }));
  await userEvent.click(await screen.findByRole('option', { name: /General products/ }));
}
beforeEach(() => {
  vi.clearAllMocks();
  window.history.replaceState(null, '', '/products/configuration');
  vi.mocked(serviceCall).mockImplementation(async (_, request) => response(request.path, request.method) as never);
});

it('offers edit only for mutable drafts and links immutable publication history', async () => {
  const original = vi.mocked(serviceCall).getMockImplementation()!;
  vi.mocked(serviceCall).mockImplementation(async (...args) => {
    if (args[1].path.includes('/drafts?')) return { items: [draft, { ...draft, id: ITEM, status: 'PUBLISHED', effective_from: '2028-02-01' }], page } as never;
    if (args[1].path.includes('/revisions?')) return { items: [revision], page } as never;
    return original(...args);
  });
  wrap(<ProductConfigurationScope company={COMPANY} id={SCOPE} canManage />);
  await userEvent.click(await screen.findByRole('button', { name: 'Actions for Draft effective 2028-01-01' }));
  expect(screen.getByRole('menuitem', { name: 'Edit draft' })).toHaveAttribute('href', expect.stringContaining('/drafts/' + DRAFT + '/edit'));
  await userEvent.keyboard('{Escape}');
  await userEvent.click(screen.getByRole('button', { name: 'Actions for Draft effective 2028-02-01' }));
  expect(screen.queryByRole('menuitem', { name: 'Edit draft' })).not.toBeInTheDocument();
  await userEvent.keyboard('{Escape}');
  await userEvent.click(screen.getByRole('button', { name: 'Actions for Revision 1' }));
  expect(screen.getByRole('menuitem', { name: 'View revision' })).toHaveAttribute('href', expect.stringContaining('/revisions/' + REVISION));
});

it('does not invent labels for masked scope and draft fields', async () => {
  const original = vi.mocked(serviceCall).getMockImplementation()!;
  vi.mocked(serviceCall).mockImplementation(async (...args) => {
    if (args[1].path.includes('/drafts?')) return { items: [{ id: DRAFT, row_version: 3 }], page } as never;
    if (args[1].path.endsWith('/product-configuration-scopes/' + SCOPE)) return { id: SCOPE, company_id: COMPANY } as never;
    return original(...args);
  });
  wrap(<ProductConfigurationScope company={COMPANY} id={SCOPE} canManage={false} />);
  expect(await screen.findByRole('heading', { name: 'Protected scope' })).toBeVisible();
  expect(await screen.findByText('Owner unavailable or protected')).toBeVisible();
  expect(await screen.findByRole('button', { name: 'Actions for Draft effective not readable' })).toBeVisible();
  expect(screen.getAllByText('Not readable').length).toBeGreaterThan(0);
});

it('does not label a draft as published when its lifecycle field is protected', async () => {
  const original = vi.mocked(serviceCall).getMockImplementation()!;
  vi.mocked(serviceCall).mockImplementation(async (...args) => {
    if (args[1].path.endsWith('/product-configurations/' + DRAFT)) {
      const { status: _status, ...masked } = draft;
      return masked as never;
    }
    return original(...args);
  });
  wrap(<ProductConfigurationDetail company={COMPANY} id={DRAFT} canManage canPublish timezone="Asia/Kolkata" />);
  expect(await screen.findByText('Reviewed product defaults')).toBeVisible();
  expect(screen.getByText('Not readable')).toBeVisible();
  expect(screen.queryByText('Published')).not.toBeInTheDocument();
  expect(screen.queryByRole('link', { name: 'Edit draft' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Review publication' })).not.toBeInTheDocument();
});

it('rejects a foreign-company scope response and retries an explicit fresh read', async () => {
  const original = vi.mocked(serviceCall).getMockImplementation()!; let reads = 0;
  vi.mocked(serviceCall).mockImplementation(async (...args) => args[1].path.endsWith('/product-configuration-scopes/' + SCOPE) && reads++ === 0 ? { ...scope, company_id: ITEM } as never : original(...args));
  wrap(<ProductConfigurationScope company={COMPANY} id={SCOPE} canManage />);
  expect(await screen.findByText('This configuration scope could not be verified.')).toBeVisible();
  expect(screen.queryByRole('link', { name: 'New draft' })).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Reload configuration' }));
  expect(await screen.findByRole('link', { name: 'New draft' })).toBeVisible();
});

it('shows legacy provenance without offering retired owner lookup', () => {
  const view = wrap(<ConfigurationOwner company={COMPANY} scope={{ ...scope, scope_kind: 'GROUP', owner_id: ITEM }} />);
  expect(screen.getByText('Owner unavailable or protected')).toBeVisible();
  expect(serviceCall).not.toHaveBeenCalled();
  view.rerender(<ConfigurationOwner company={COMPANY} scope={{ ...scope, scope_kind: 'TYPE', owner_label: 'Services type' }} />);
  expect(screen.getByText('Services type')).toBeVisible(); expect(serviceCall).not.toHaveBeenCalled();
});

it('ignores retired owner filters and offers adoption only with its authority', async () => {
  wrap(<ProductConfigurationDirectory company={COMPANY} canManage canAdopt initialQuery={'scope_kind=GROUP&group_id=' + ITEM} />);
  expect(await screen.findByRole('link', { name: 'Edit company configuration' })).toBeVisible();
  expect(screen.getByRole('link', { name: 'Review product adoption' })).toBeVisible();
  expect(vi.mocked(serviceCall).mock.calls.some(([, request]) => request.path.includes('group_id='))).toBe(false);
  expect(screen.queryByRole('combobox', { name: 'Filter by owner' })).not.toBeInTheDocument();
});

it('retains a linked product context and refreshes the same inspection', async () => {
  wrap(<ProductConfigurationEffective company={COMPANY} timezone="Asia/Kolkata" initialFamilyId={ITEM} initialKind="SERVICE" />);
  expect(screen.queryByRole('combobox', { name: 'Inspect context' })).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Inspect settings' }));
  expect(await screen.findByText('Inheritance and protection')).toBeVisible();
  const requests = () => vi.mocked(serviceCall).mock.calls.filter(([, request]) => request.path.includes('/effective?'));
  expect(requests()[0][1].path).toContain('family_id=' + ITEM); expect(requests()[0][1].path).toContain('kind=SERVICE');
  await userEvent.click(screen.getByRole('button', { name: 'Inspect settings' })); await waitFor(() => expect(requests()).toHaveLength(2));
  expect(writes()).toHaveLength(0);
});

it('rejects an unverified effective response without displaying defaults', async () => {
  const original = vi.mocked(serviceCall).getMockImplementation()!;
  vi.mocked(serviceCall).mockImplementation(async (...args) => args[1].path.includes('/effective?') ? { ...response(args[1].path) as object, company_id: ITEM } as never : original(...args));
  wrap(<ProductConfigurationEffective company={COMPANY} timezone="Asia/Kolkata" />);
  await userEvent.click(screen.getByRole('button', { name: 'Inspect settings' }));
  expect(await screen.findByText('The effective settings response could not be verified.')).toBeVisible();
  expect(screen.queryByText('Inheritance and protection')).not.toBeInTheDocument();
});

it('validates adoption before requesting a review and refreshes the same chosen product', async () => {
  wrap(<ProductConfigurationAdoption company={COMPANY} timezone="Asia/Kolkata" canAdopt />);
  await userEvent.click(screen.getByRole('button', { name: 'Review adoption' }));
  expect(screen.getByText('Choose a product and a valid date before reviewing adoption.')).toBeVisible();
  await chooseProduct(); await userEvent.click(screen.getByRole('button', { name: 'Review adoption' }));
  await screen.findByRole('button', { name: 'Adopt reviewed draft defaults' });
  await userEvent.click(screen.getByRole('button', { name: 'Review adoption' }));
  await waitFor(() => expect(vi.mocked(serviceCall).mock.calls.filter(([, request]) => request.path.endsWith('/preview?as_of=' + screen.getByLabelText<HTMLInputElement>('As of date').value))).toHaveLength(2));
  expect(writes()).toHaveLength(0);
});

it('recovers an uncertain adoption with the retained body and idempotency key after closing its review', async () => {
  const original = vi.mocked(serviceCall).getMockImplementation()!; let attempts = 0;
  vi.mocked(serviceCall).mockImplementation(async (...args) => args[1].method === 'POST' && attempts++ === 0 ? Promise.reject({ status: 503, message: 'Unconfirmed adoption' }) : original(...args));
  wrap(<ProductConfigurationAdoption company={COMPANY} timezone="Asia/Kolkata" canAdopt />);
  await chooseProduct(); await userEvent.click(screen.getByRole('button', { name: 'Review adoption' }));
  await userEvent.click(await screen.findByRole('button', { name: 'Adopt reviewed draft defaults' }));
  await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Adopt draft defaults' }));
  await screen.findByRole('button', { name: 'Retry same adoption' });
  expect(screen.getByLabelText('As of date')).toBeDisabled();
  await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancel' }));
  expect(screen.getByText(/Adoption is unconfirmed/)).toBeVisible();
  await userEvent.click(screen.getByRole('button', { name: 'Adopt reviewed draft defaults' }));
  await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Retry same adoption' }));
  expect(await screen.findByText(/Draft product defaults adopted successfully/)).toBeVisible();
  expect(writes()[0][1].body).toEqual(writes()[1][1].body); expect(writes()[0][1].key).toBe(writes()[1][1].key);
});

it('explains incomplete draft requirements and retained source revisions without offering adoption', async () => {
  const original = vi.mocked(serviceCall).getMockImplementation()!;
  vi.mocked(serviceCall).mockImplementation(async (...args) => args[1].path.includes('/configuration-adoption/preview') ? { ...response(args[1].path) as object, eligible: false, missing: ['unit_revision_required'], blocked_reasons: ['family_requirements_missing'], current_revision_ids: [REVISION] } as never : original(...args));
  wrap(<ProductConfigurationAdoption company={COMPANY} timezone="Asia/Kolkata" canAdopt />);
  await chooseProduct(); await userEvent.click(screen.getByRole('button', { name: 'Review adoption' }));
  expect(await screen.findByText(/Complete the product requirements first: unit revision required/)).toBeVisible();
  expect(screen.getByText('family requirements missing')).toBeVisible();
  expect(screen.getAllByRole('link', { name: 'View source revision 1' })).toHaveLength(2);
  expect(screen.queryByRole('button', { name: 'Adopt reviewed draft defaults' })).not.toBeInTheDocument(); expect(writes()).toHaveLength(0);
});

it.each([409, 422, 502])('offers an explicit reload for a %s read failure', async status => {
  const retry = vi.fn(); wrap(<ConfigurationFailure failure={{ status, message: 'Review failed' }} retry={retry} />);
  await userEvent.click(screen.getByRole('button', { name: status === 502 ? 'Reload configuration' : 'Reload and review' }));
  expect(retry).toHaveBeenCalledOnce();
});
