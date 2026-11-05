import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { DisplayConfigProvider } from '@janso/ui';
import { CatalogMasterEditor } from '../app/components/CatalogMasterEditor';
import { CatalogMasterDirectory } from '../app/components/CatalogMasterDirectory';
import { CatalogMasterDetail } from '../app/components/CatalogMasterDetail';
import { CatalogMasterPage } from '../app/components/CatalogMasterPage';
import { WarehouseSettings } from '../app/components/WarehouseSettings';
import { WarehouseOperationPolicy } from '../app/components/WarehouseOperationPolicy';
import { WarehouseRegionalField } from '../app/components/WarehouseRegionalField';
import { WarehouseCompanyField } from '../app/components/WarehouseCompanyField';
import { masterBody, masterConfig, type MasterField } from '../app/lib/catalog-masters';
import { operationLabels, defaultLabels } from '../app/lib/warehouse-ui';
import { serviceCall } from '../app/lib/service-call';
import { pageContext } from '../app/lib/page-context';
import { navigationFor } from '../app/nav';
import { allowedProductRequest } from '../app/lib/product-request-policy';
import { companyContextFor, sessionFor } from './helpers';
vi.mock('../app/lib/service-call', async original => ({ ...await original<typeof import('../app/lib/service-call')>(), serviceCall: vi.fn() }));
vi.mock('../app/lib/page-context', () => ({ pageContext: vi.fn() }));
vi.mock('../app/providers', () => ({ Providers: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/components/ConsoleShell', () => ({ ConsoleShell: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('next/navigation', () => ({ notFound: () => { throw new Error('not found'); } }));
const company = '01990000-0000-7000-8000-000000000001', id = '01990000-0000-7000-8000-000000000002', other = '01990000-0000-7000-8000-000000000003', config = masterConfig('warehouses')!;
const row = { id, company_id: company, code: 'STORE1', name: 'Retail store', kind: 'STORE', is_system: false, is_active: true, row_version: 4, country_code: 'IN', state_code: 'IN-MH', timezone: 'Asia/Kolkata' };
const page = { limit: 50, has_more: false, next_cursor: null };
const flags = Object.fromEntries(Object.keys(operationLabels).map(key => [key, true]));
const policy = { warehouse_id: id, policy_generation: 8, source_version: 5, current: { id, revision: 2, effective_from: '2026-10-24T00:00:00Z', delivery_state: 'PENDING', ...flags }, history: [] };
const configuration = { id: other, company_id: company, main_warehouse_id: id, location_mode: 'MULTI_LOCATION', policy_generation: 8, source_version: 5, ...Object.fromEntries(Object.keys(defaultLabels).map(key => [key, id])) };
function fields(keys: string[]): MasterField[] { return keys.map((key, order) => ({ key, label: key, order, source: 'native', visible: true, writable: true, required: ['code', 'name', 'kind'].includes(key), conditional_access: false })); }
const show = (node: React.ReactNode) => render(<DisplayConfigProvider config={{ timezone: 'Asia/Kolkata' }}>{node}</DisplayConfigProvider>);
const writes = () => vi.mocked(serviceCall).mock.calls.filter(([, req]) => ['POST', 'PATCH'].includes(req.method ?? 'GET'));
beforeEach(async () => {
  vi.clearAllMocks(); window.history.replaceState({}, '', '/');
  const session = await sessionFor(); session.company = { id: company, name: 'Acme' }; session.grants = [{ scope_type: 'company', scope_id: company, permissions: ['warehouse.read', 'warehouse.manage', 'warehouse.publish', 'warehouse.deactivate'], valid_from: '2020-01-01', valid_to: null }];
  vi.mocked(pageContext).mockResolvedValue({ session, context: companyContextFor() });
  vi.mocked(serviceCall).mockImplementation(async (_endpoint, req) => {
    if (req.path.includes('/entities/')) { const entity = req.path.split('/entities/')[1]!.split('/')[0]!; return { company_id: company, entity_type: entity, fields: fields(entity.includes('operation_policy') ? Object.keys(operationLabels) : entity.includes('configuration') ? Object.keys(defaultLabels) : [...Object.keys(config.inputs), 'is_active', 'is_system']) } as never; }
    if (req.path.endsWith('/preview')) return { warehouse_id: id, expected_generation: 8, expected_source_version: 5, revision: 3, publishable: true, delivery_state: 'PENDING', changed: ['allow_sale_issue'], issues: [] } as never;
    if (req.method === 'POST' || req.method === 'PATCH') return { ...row, ...req.body as object, row_version: 5 } as never;
    if (req.path.includes('/operation-policy')) return policy as never;
    if (req.path.endsWith('/warehouse-configuration')) return configuration as never;
    if (req.path === '/v1/reference/timezones') return [{ code: 'Asia/Kolkata', name: 'Kolkata' }] as never;
    if (req.path.endsWith('/states')) return [{ code: 'IN-MH', name: 'Maharashtra' }] as never;
    if (req.path === '/v1/reference/countries') return [{ code: 'IN', name: 'India' }, { code: 'US', name: 'United States' }] as never;
    if (req.path.includes('/departments')) return { items: [{ id: other, code: 'OPS', name: 'Operations' }], page } as never;
    if (req.path.includes('/tax-registrations')) return { items: [{ id: other, number: '27AAAPA1234A1ZT', regime: 'regular', jurisdiction_code: 'MH' }], page } as never;
    if (req.path.endsWith('/' + id)) return row as never;
    return { items: [row], page } as never;
  });
});
it('validates optional location fields, immutable identities and reserved codes', () => {
  const metadata = fields(Object.keys(config.inputs));
  expect(masterBody(config, metadata, { ...config.initial, code: 'STORE1', name: 'Store' }).errors).toEqual({});
  expect(masterBody(config, metadata, { ...config.initial, code: 'MAIN', name: 'Store' }).errors.code).toMatch(/system/);
  expect(masterBody(config, metadata, { ...row, country_code: 'US' }).errors.state_code).toMatch(/selected country/);
  expect(masterBody(config, metadata, { ...row, country_code: null }).errors.state_code).toMatch(/country/);
  expect(masterBody(config, metadata, { ...row, name: 'New', code: 'CHANGED', kind: 'GODOWN' }, row).body).toEqual({ expected_version: 4, name: 'New' });
});
it('allows only fixed warehouse actions and regional reference reads at the proxy', () => {
  const base = `/v1/companies/${company}`;
  for (const path of ['/warehouses', '/warehouses/' + id, '/warehouses/' + id + '/operation-policy', '/warehouse-configuration', '/entities/catalog.warehouse/field-set', '/entities/catalog.company_warehouse_configuration/field-set?operation=update']) expect(allowedProductRequest('catalog', 'GET', base + path)).toBe(true);
  for (const suffix of ['/operation-policy/preview', '/operation-policy/publish', '/activate', '/deactivate']) expect(allowedProductRequest('catalog', 'POST', base + '/warehouses/' + id + suffix)).toBe(true);
  for (const path of ['/warehouses/' + id + '/operation-policy/ack', '/warehouse-configuration/defaults?force=true', '/warehouses?is_system=maybe', '/warehouses?kind=FAKE', '/entities/catalog.company_warehouse_configuration/field-set?operation=delete']) expect(allowedProductRequest('catalog', 'POST', base + path)).toBe(false);
  for (const path of ['/v1/reference/countries', '/v1/reference/countries/IN/states', '/v1/reference/timezones']) { expect(allowedProductRequest('identity', 'GET', path)).toBe(true); expect(allowedProductRequest('identity', 'POST', path)).toBe(false); expect(allowedProductRequest('identity', 'GET', path + '?private=1')).toBe(false); }
});
it('renders warehouses and settings using the shared layouts and actions', async () => {
  const view = show(<CatalogMasterDirectory company={company} config={config} canManage />); await screen.findByText('Retail store');
  expect(screen.getByRole('link', { name: 'Warehouse settings' })).toHaveAttribute('href', expect.stringContaining('/masters/warehouses/settings?returnTo='));
  expect(screen.getByRole('link', { name: 'New warehouse' })).toBeInTheDocument(); view.unmount();
  show(await CatalogMasterPage({ resource: 'warehouses', record: ['settings'] })); expect(await screen.findByRole('heading', { name: 'Warehouse settings' })).toBeInTheDocument();
});
it('names the actual Company Settings return destination for warehouse defaults', async () => {
  show(<WarehouseSettings company={company} canManage={false} canPublish={false} returnTo="/settings" />);
  expect(screen.getByRole('link', { name: 'Back to Company settings' })).toHaveAttribute('href', '/settings');
});
it('company scope gates pages, navigation, publication and retirement independently', async () => {
  const { session, context } = await pageContext(); session.grants = [{ scope_type: 'company', scope_id: other, permissions: ['warehouse.read', 'warehouse.manage'], valid_from: '2020-01-01', valid_to: null }];
  vi.mocked(pageContext).mockResolvedValue({ session, context });
  expect(navigationFor(session).flatMap(section => section.items).some(item => item.href === '/masters/warehouses')).toBe(false);
  const view = show(await CatalogMasterPage({ resource: 'warehouses' })); expect(screen.getByRole('alert')).toHaveTextContent('warehouse.read'); view.unmount();
  show(<CatalogMasterDetail company={company} config={config} id={id} canManage canDeactivate={false} />); await screen.findByText('Retail store', { selector: 'h1' });
  expect(screen.queryByRole('button', { name: 'Deactivate warehouse' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Review operation changes' })).not.toBeInTheDocument();
});
it('creates a warehouse with bounded regional selectors and prevents duplicate submissions', async () => {
  show(<CatalogMasterEditor company={company} config={config} />);
  fireEvent.change(await screen.findByRole('textbox', { name: 'Code' }), { target: { value: 'STORE1' } });
  fireEvent.change(screen.getByRole('textbox', { name: 'Name' }), { target: { value: 'Retail store' } });
  await waitFor(() => expect(screen.getByRole('combobox', { name: 'Country' })).toBeEnabled());
  await userEvent.click(screen.getByRole('combobox', { name: 'Country' })); await userEvent.click(screen.getByRole('option', { name: /India/ }));
  await waitFor(() => expect(screen.getByRole('combobox', { name: 'State' })).toBeEnabled());
  await userEvent.click(screen.getByRole('combobox', { name: 'State' })); await userEvent.click(screen.getByRole('option', { name: /Maharashtra/ }));
  await userEvent.click(screen.getByRole('button', { name: 'Create warehouse' })); await screen.findByText('Warehouse created.');
  expect(writes()).toHaveLength(1); expect(writes()[0]![1]).toMatchObject({ key: expect.any(String), body: { country_code: 'IN', state_code: 'IN-MH', kind: 'STORE', address_line1: null } });
});
it('protects system lifecycle and immutable identity in edit forms', async () => {
  const implementation = vi.mocked(serviceCall).getMockImplementation()!;
  vi.mocked(serviceCall).mockImplementation(async (...args) => args[1].path.endsWith('/' + id) ? { ...row, is_system: true, code: 'MAIN' } as never : implementation(...args));
  const view = show(<CatalogMasterDetail company={company} config={config} id={id} canManage canDeactivate />); await screen.findByText(/system locations/);
  expect(screen.queryByRole('button', { name: 'Deactivate warehouse' })).not.toBeInTheDocument(); view.unmount();
  show(<CatalogMasterEditor company={company} config={config} id={id} />); expect(await screen.findByRole('textbox', { name: 'Code' })).toBeDisabled(); expect(screen.getByRole('combobox', { name: 'Location kind' })).toBeDisabled();
});
it('reviews the whole policy and publishes echoed expectations with pending delivery', async () => {
  show(<WarehouseOperationPolicy company={company} id={id} canPublish />);
  await userEvent.click(await screen.findByRole('checkbox', { name: 'Allow sale from this store' }));
  await userEvent.click(screen.getByRole('button', { name: 'Review operation changes' }));
  const dialog = await screen.findByRole('dialog'); expect(within(dialog).getByText('Blocked')).toBeInTheDocument();
  await userEvent.click(within(dialog).getByRole('button', { name: 'Publish reviewed changes' }));
  await screen.findByText(/Operation policy published/);
  expect(writes().find(([, req]) => req.path.endsWith('/publish'))?.[1]).toMatchObject({ key: expect.any(String), body: { allow_sale_issue: false, expected_generation: 8, expected_source_version: 5 } });
  expect(screen.getByText('PENDING')).toBeInTheDocument();
});
it('recovers an unconfirmed publication with the same key and frozen proposal', async () => {
  const implementation = vi.mocked(serviceCall).getMockImplementation()!; let failed = false;
  vi.mocked(serviceCall).mockImplementation(async (...args) => { if (args[1].path.endsWith('/publish') && !failed) { failed = true; throw { status: 503, message: 'Stock service unavailable' }; } return implementation(...args); });
  show(<WarehouseOperationPolicy company={company} id={id} canPublish />);
  await userEvent.click(await screen.findByRole('checkbox', { name: 'Allow sale from this store' })); await userEvent.click(screen.getByRole('button', { name: 'Review operation changes' }));
  await userEvent.click(await screen.findByRole('button', { name: 'Publish reviewed changes' })); await screen.findByText('Stock service unavailable');
  expect(screen.getByRole('checkbox', { name: 'Allow sale from this store' })).toBeDisabled();
  await userEvent.click(screen.getByRole('button', { name: 'Retry same publication' })); await screen.findByText(/Operation policy published/);
  const calls = writes().filter(([, req]) => req.path.endsWith('/publish')); expect(calls).toHaveLength(2); expect(calls[0]![1].key).toBe(calls[1]![1].key);
});
it('does not fabricate missing policy fields for publication', async () => {
  const implementation = vi.mocked(serviceCall).getMockImplementation()!;
  vi.mocked(serviceCall).mockImplementation(async (...args) => args[1].path.endsWith('/operation-policy') ? { ...policy, current: { ...policy.current, allow_sale_issue: undefined } } as never : implementation(...args));
  show(<WarehouseOperationPolicy company={company} id={id} canPublish />); expect(await screen.findByRole('button', { name: 'Review operation changes' })).toBeDisabled(); expect(screen.queryByRole('checkbox', { name: 'Allow sale from this store' })).not.toBeInTheDocument();
});
it('reviews defaults and saves all four pointers with the policy checkpoint', async () => {
  show(<WarehouseSettings company={company} canManage canPublish />);
  await screen.findByRole('combobox', { name: 'Default sale warehouse' });
  await userEvent.click(await screen.findByRole('button', { name: 'Clear Default sale warehouse' }));
  await userEvent.click(screen.getByRole('button', { name: 'Review default changes' }));
  expect(await screen.findByText('Main fallback')).toBeInTheDocument(); await userEvent.click(screen.getByRole('button', { name: 'Save defaults' })); await screen.findByText(/Warehouse defaults saved/);
  expect(writes()[0]![1]).toMatchObject({ key: expect.any(String), body: { default_sale_warehouse_id: null, default_purchase_warehouse_id: id, expected_generation: 8, expected_source_version: 5 } });
});
it('offers an authorized idempotent Main initialization for unprovisioned companies', async () => {
  const implementation = vi.mocked(serviceCall).getMockImplementation()!;
  vi.mocked(serviceCall).mockImplementation(async (...args) => { if (args[1].path.endsWith('/warehouse-configuration') && !writes().length) throw { status: 404, message: 'Not provisioned' }; return implementation(...args); });
  show(<WarehouseSettings company={company} canManage canPublish={false} />); await userEvent.click(await screen.findByRole('button', { name: 'Initialize Main warehouse' }));
  await userEvent.click(screen.getByRole('button', { name: 'Initialize locations' })); await screen.findByText('Company warehouse locations initialized.'); expect(writes()[0]![1]).toMatchObject({ key: expect.any(String), body: {} });
});
it('makes settings read-only and protects edits on reload', async () => {
  const view = show(<WarehouseSettings company={company} canManage={false} canPublish={false} />); expect(await screen.findByRole('combobox', { name: 'Default sale warehouse' })).toBeDisabled(); view.unmount();
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false); show(<WarehouseSettings company={company} canManage canPublish />);
  await screen.findByRole('combobox', { name: 'Default sale warehouse' }); await userEvent.click(await screen.findByRole('button', { name: 'Clear Default sale warehouse' })); const before = vi.mocked(serviceCall).mock.calls.length;
  await userEvent.click(screen.getByRole('button', { name: 'Reload settings' })); expect(confirm).toHaveBeenCalled(); expect(vi.mocked(serviceCall).mock.calls).toHaveLength(before);
});
it('reports regional choice errors and supports a deliberate retry', async () => {
  const implementation = vi.mocked(serviceCall).getMockImplementation()!; let failed = false;
  vi.mocked(serviceCall).mockImplementation(async (...args) => { if (!failed) { failed = true; throw { status: 503, message: 'Choices unavailable' }; } return implementation(...args); });
  show(<WarehouseRegionalField company={company} type="country" country={null} value={null} label="Country" name="country_code" onChange={() => undefined} />);
  await screen.findByText('Choices unavailable'); await userEvent.click(screen.getByRole('button', { name: 'Retry country choices' })); await waitFor(() => expect(screen.getByRole('combobox', { name: 'Country' })).toBeEnabled());
});
it('reports a refused preview without offering a publication action', async () => {
  const implementation = vi.mocked(serviceCall).getMockImplementation()!;
  vi.mocked(serviceCall).mockImplementation(async (...args) => args[1].path.endsWith('/preview') ? { warehouse_id: id, publishable: false, issues: [{ code: 'NO_CHANGE', message: 'No operation changes' }] } as never : implementation(...args));
  show(<WarehouseOperationPolicy company={company} id={id} canPublish />); await userEvent.click(await screen.findByRole('button', { name: 'Review operation changes' }));
  await screen.findByText('No operation changes'); expect(screen.queryByRole('button', { name: 'Publish reviewed changes' })).not.toBeInTheDocument();
});
it('lets users dismiss an uncertain publication while retaining deliberate recovery', async () => {
  const implementation = vi.mocked(serviceCall).getMockImplementation()!;
  vi.mocked(serviceCall).mockImplementation(async (...args) => { if (args[1].path.endsWith('/publish')) throw { status: 503, message: 'Lost publication response' }; return implementation(...args); });
  show(<WarehouseOperationPolicy company={company} id={id} canPublish />); await userEvent.click(await screen.findByRole('button', { name: 'Review operation changes' })); await userEvent.click(await screen.findByRole('button', { name: 'Publish reviewed changes' })); await screen.findByText('Lost publication response');
  await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancel' })); expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Recover publication' })); expect(screen.getByRole('dialog')).toBeInTheDocument();
});
it.each([['department', 'Department', 'Operations'], ['tax-registration', 'Tax registration', '27AAAPA1234A1ZT']] as const)('resolves a saved %s through its scoped list and preserves the saved identity', async (type, label, display) => {
  const change = vi.fn(); show(<WarehouseCompanyField company={company} type={type} label={label} name="link" value={other} canRead onChange={change} />);
  await waitFor(() => expect(screen.getByRole('combobox', { name: label })).toHaveValue(display));
  expect(vi.mocked(serviceCall).mock.calls[0]![1]).toMatchObject({ service: 'identity', path: expect.stringContaining('?id=' + other + '&limit=1') });
  expect(change).not.toHaveBeenCalled();
});
it('preserves optional company links when lookup access is unavailable', async () => {
  const change = vi.fn(); show(<WarehouseCompanyField company={company} type="department" label="Department" name="department_id" value={other} canRead={false} onChange={change} />);
  expect(screen.getByRole('combobox', { name: 'Department' })).toBeDisabled(); expect(screen.getByRole('combobox', { name: 'Department' })).toHaveValue('Saved department'); expect(serviceCall).not.toHaveBeenCalled(); expect(change).not.toHaveBeenCalled();
});
it('supports a paged searchable department lookup and writes the selected identity', async () => {
  const change = vi.fn(); show(<WarehouseCompanyField company={company} type="department" label="Department" name="department_id" value={null} canRead onChange={change} />);
  await userEvent.click(screen.getByRole('combobox', { name: 'Department' })); await userEvent.type(screen.getByRole('combobox', { name: 'Department' }), 'OP');
  await userEvent.click(await screen.findByRole('option', { name: /Operations/ })); expect(change).toHaveBeenCalledWith(other);
});
it.each([false, true])('retains an unavailable saved tax link when a matching read %s fails', async wrongRecord => {
  vi.mocked(serviceCall).mockImplementation(async () => { if (!wrongRecord) throw { status: 403, message: 'Read denied' }; return { items: [], page } as never; });
  show(<WarehouseCompanyField company={company} type="tax-registration" label="Tax registration" name="tax_registration_id" value={other} canRead onChange={() => undefined} />);
  await waitFor(() => expect(screen.getByRole('combobox', { name: 'Tax registration' })).toHaveValue('Saved tax-registration (unavailable)'));
});
it('closes and recovers an unconfirmed default change using the same request key', async () => {
  const implementation = vi.mocked(serviceCall).getMockImplementation()!; let failed = false;
  vi.mocked(serviceCall).mockImplementation(async (...args) => { if (args[1].path.endsWith('/defaults') && !failed) { failed = true; throw { status: 503, message: 'Lost default response' }; } return implementation(...args); });
  show(<WarehouseSettings company={company} canManage canPublish />); await userEvent.click(await screen.findByRole('button', { name: 'Clear Default sale warehouse' })); await userEvent.click(screen.getByRole('button', { name: 'Review default changes' })); await userEvent.click(screen.getByRole('button', { name: 'Save defaults' })); await screen.findByText('Lost default response');
  await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancel' })); expect(screen.queryByRole('dialog')).not.toBeInTheDocument(); await userEvent.click(screen.getByRole('button', { name: 'Recover default change' })); await userEvent.click(screen.getByRole('button', { name: 'Retry same change' })); await screen.findByText(/Warehouse defaults saved/);
  const requests = writes().filter(([, req]) => req.path.endsWith('/defaults')); expect(requests[0]![1].key).toBe(requests[1]![1].key);
});
it('rejects malformed identity lookup parameters and writes', () => {
  for (const endpoint of ['departments', 'tax-registrations']) {
    const base = `/v1/companies/${company}/${endpoint}`;
    expect(allowedProductRequest('identity', 'GET', base + '?limit=50&q=27')).toBe(true); expect(allowedProductRequest('identity', 'GET', base + '?id=' + other)).toBe(true);
    for (const query of ['?id=wrong', '?q=A', '?limit=201', '?limit=1&limit=2', '?private=1']) expect(allowedProductRequest('identity', 'GET', base + query)).toBe(false);
    expect(allowedProductRequest('identity', 'POST', base)).toBe(false);
  }
});
it('disables a warehouse save when only immutable identity and unreadable lookup fields are writable', async () => {
  const implementation = vi.mocked(serviceCall).getMockImplementation()!;
  vi.mocked(serviceCall).mockImplementation(async (...args) => {
    const result = await implementation(...args) as { fields?: MasterField[] };
    if (result.fields) result.fields = result.fields.map(field => ({ ...field, writable: ['code', 'kind', 'department_id', 'tax_registration_id'].includes(field.key) }));
    return result as never;
  });
  show(<CatalogMasterEditor company={company} config={config} id={id} />);
  expect(await screen.findByRole('button', { name: 'Save changes' })).toBeDisabled();
});
