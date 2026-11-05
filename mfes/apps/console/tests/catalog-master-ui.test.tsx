import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { DisplayConfigProvider, PermissionProvider } from '@janso/ui';
import { CatalogMasterEditor } from '../app/components/CatalogMasterEditor';
import { CatalogMasterDirectory, masterReturnTo } from '../app/components/CatalogMasterDirectory';
import { CatalogMasterDetail } from '../app/components/CatalogMasterDetail';
import { CatalogMasterPage } from '../app/components/CatalogMasterPage';
import { masterConfig, type MasterConfig, type MasterField, type MasterRow } from '../app/lib/catalog-masters';
import { serviceCall } from '../app/lib/service-call';
import { pageContext } from '../app/lib/page-context';
import { companyContextFor, sessionFor } from './helpers';
import { goTo } from '../app/lib/navigate';
import { flattenNavigation, navigationFor } from '../app/nav';
import { companyMastersFor } from '../app/lib/company-masters';
import { BEFORE_COMPANY_CHANGE } from '../app/lib/use-unsaved-changes';

vi.mock('../app/lib/service-call', async importOriginal => ({ ...await importOriginal<typeof import('../app/lib/service-call')>(), serviceCall: vi.fn() }));
vi.mock('../app/lib/page-context', () => ({ pageContext: vi.fn() }));
vi.mock('../app/lib/navigate', () => ({ goTo: vi.fn() }));
vi.mock('../app/providers', () => ({ Providers: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/components/ConsoleShell', () => ({ ConsoleShell: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('next/navigation', () => ({ notFound: () => { throw new Error('not found'); } }));
const COMPANY = '01990000-0000-7000-8000-000000000001', ID = '01990000-0000-7000-8000-000000000002', OTHER = '01990000-0000-7000-8000-000000000003';
const unit = masterConfig('units')!, maker = masterConfig('manufacturers')!, group = masterConfig('item-groups')!;
const original: MasterRow = { id: ID, company_id: COMPANY, code: 'KG', name: 'Kilogram', symbol: 'kg', dimension: 'MASS', decimal_places: 3, quantity_increment: '0.0010', is_active: true, row_version: 4, policy_generation: 8 };
const page = { limit: 50, has_more: false, next_cursor: null };
function fields(config: MasterConfig): MasterField[] { return [...Object.keys(config.inputs), 'is_active', 'row_version'].map((key, order) => ({ key, label: key, source: 'native', order, visible: true, writable: true, required: key !== 'party_id', conditional_access: false })); }
function wrap(node: React.ReactNode) { return render(<PermissionProvider permissions={[]}><DisplayConfigProvider config={{ timezone: 'Asia/Kolkata', currency: 'INR' }}>{node}</DisplayConfigProvider></PermissionProvider>); }
const writes = () => vi.mocked(serviceCall).mock.calls.filter(([, request]) => ['POST', 'PATCH'].includes(request.method ?? 'GET'));
async function fill(config: MasterConfig) {
  await userEvent.type(await screen.findByRole('textbox', { name: 'Code' }), 'TEST');
  await userEvent.type(screen.getByRole('textbox', { name: 'Name' }), 'Test master');
  if (config.resource === 'units') await userEvent.type(screen.getByRole('textbox', { name: 'Symbol' }), 'pc');
}
beforeEach(async () => {
  vi.clearAllMocks(); window.history.replaceState(null, '', '/');
  const session = await sessionFor(); session.company = { id: COMPANY, name: 'Acme' }; session.grants = [{ scope_type: 'company', scope_id: COMPANY, valid_from: '2020-01-01', valid_to: null, permissions: ['unit.read', 'unit.manage', 'manufacturer.read', 'manufacturer.manage', 'item_group.read', 'item_group.manage', 'item_group.move'] }];
  vi.mocked(pageContext).mockResolvedValue({ session, context: companyContextFor() });
  vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => {
    if (request.path.includes('/entities/')) {
      const config = request.path.includes('unit_of_measure') ? unit : request.path.includes('manufacturer') ? maker : group;
      const metadata = request.path.includes('item_group_parent') ? ['parent_group_id', 'valid_from', 'valid_to'].map((key, order) => ({ key, order, label: key, visible: true, writable: true, required: false, source: 'native', conditional_access: false })) : fields(config);
      return { company_id: COMPANY, entity_type: request.path.split('/entities/')[1]!.split('/')[0], fields: metadata } as never;
    }
    if (request.method === 'PATCH' || request.method === 'POST') return { ...original, ...request.body as object, row_version: 5 } as never;
    if (request.path.split('?')[0].endsWith(ID)) return original as never;
    if (request.path.includes('/parents?')) return { items: [], page } as never;
    return { items: [original], page } as never;
  });
});
describe('company-scoped master workflows', () => {
  it('returns from an edit to details with the original directory instead of a self-return loop', async () => {
    const directory = '/masters/manufacturers?q=Ki&returnTo=%2Finventory%2Fproducts';
    const detail = '/masters/manufacturers/' + ID + '?returnTo=' + encodeURIComponent(directory);
    wrap(<CatalogMasterEditor company={COMPANY} config={maker} id={ID} returnTo={detail} />);
    await screen.findByRole('button', { name: 'Save changes' });
    const link = screen.getByRole('link', { name: 'Back to manufacturer details' });
    const target = new URL(link.getAttribute('href')!, 'https://console.invalid');
    expect(target.pathname).toBe('/masters/manufacturers/' + ID);
    expect(target.searchParams.get('returnTo')).toBe(directory);
    const breadcrumb = within(screen.getByRole('navigation', { name: 'Breadcrumb' })).getByRole('link', { name: 'Manufacturers' });
    expect(new URL(breadcrumb.getAttribute('href')!, 'https://console.invalid').pathname).toBe('/masters/manufacturers');
  });
  it('keeps a detail edit return chain and offers permitted manufacturer sites', async () => {
    wrap(<CatalogMasterDetail company={COMPANY} config={maker} id={ID} canManage canReadManufacturerSites returnTo="/masters/manufacturers?q=Kilogram" />);
    await userEvent.click(await screen.findByRole('button', {name:'Record actions'}));
    const edit = screen.getByRole('menuitem', {name:'Edit manufacturer'});
    const back = new URL(edit.getAttribute('href')!, 'https://console.invalid').searchParams.get('returnTo')!;
    expect(new URL(back, 'https://console.invalid').pathname).toBe('/masters/manufacturers/' + ID);
    expect(new URL(new URL(back, 'https://console.invalid').searchParams.get('returnTo')!, 'https://console.invalid').searchParams.get('q')).toBe('Kilogram');
    expect(screen.getByRole('menuitem', {name:'Manufacturer sites'})).toHaveAttribute('href', expect.stringContaining('manufacturer_id=' + ID));
  });
  it('hides manufacturer setup shortcuts without their read authority', async () => {
    wrap(<CatalogMasterDetail company={COMPANY} config={maker} id={ID} canManage={false} />);
    await screen.findByRole('heading',{name:'Kilogram',level:1});
    expect(screen.queryByRole('link',{name:'Sites for this manufacturer'})).not.toBeInTheDocument();
    expect(screen.queryByRole('button',{name:'Record actions'})).not.toBeInTheDocument();
  });

  it('disables saving when custom visibility leaves no editable manufacturer fields', async () => {
    const implementation = vi.mocked(serviceCall).getMockImplementation()!;
    vi.mocked(serviceCall).mockImplementation(async (...args) => {
      const value = await implementation(...args) as { fields?: MasterField[] };
      if (value.fields) value.fields = [...value.fields.map(field => ({ ...field, writable: false })), { key: 'custom_field:cf_note', label: 'Note', source: 'custom', order: 90, visible: true, writable: true, required: false, conditional_access: false,
        custom: { key: 'cf_note', data_type: 'text', is_active: true, is_immutable_after_create: false, visibility: { field: 'code', cmp: 'eq', value: 'OTHER' }, validation: { required: false, max_length: 20 }, choices: [] } }];
      return value as never;
    });
    wrap(<CatalogMasterEditor company={COMPANY} config={maker} id={ID} />);
    expect(await screen.findByRole('button', { name: 'Save changes' })).toBeDisabled(); expect(screen.queryByRole('textbox', { name: 'Note' })).not.toBeInTheDocument();
  });
  it.each([maker, group])('focuses an invalid integer custom field on the $singular form', async config => {
    const implementation = vi.mocked(serviceCall).getMockImplementation()!;
    vi.mocked(serviceCall).mockImplementation(async (...args) => {
      const value = await implementation(...args) as { fields?: MasterField[] };
      if (value.fields) value.fields.push({ key: 'custom_field:cf_counter', label: 'Counter', order: 90, source: 'custom', visible: true, writable: true, required: false, conditional_access: false,
        custom: { key: 'cf_counter', data_type: 'integer', is_active: true, is_immutable_after_create: false, validation: { required: false, max_length: 20 }, choices: [] } });
      return value as never;
    });
    wrap(<CatalogMasterEditor company={COMPANY} config={config} />); await fill(config);
    const counter = screen.getByRole('textbox', { name: 'Counter' }); await userEvent.type(counter, '1.5');
    await userEvent.click(screen.getByRole('button', { name: 'Create ' + config.singular }));
    await screen.findByText('Enter a whole number within the supported form range.'); expect(writes()).toHaveLength(0);
    await waitFor(() => expect(counter).toHaveFocus());
  });
  it('rejects an empty group move date before making a request and focuses the date', async () => {
    wrap(<CatalogMasterDetail company={COMPANY} config={group} id={ID} canManage={false} canMove />);
    await userEvent.click(await screen.findByRole('button', { name: 'Change parent group' }));
    const date = screen.getByLabelText('Effective from'); await userEvent.clear(date);
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Save parent change' }));
    expect(await screen.findByText('Choose a valid effective date.')).toBeVisible(); await waitFor(() => expect(date).toHaveFocus()); expect(writes()).toHaveLength(0);
  });
  it.each([unit, maker, group])('removes unavailable $singular query settings before fetching records', async config => {
    const implementation = vi.mocked(serviceCall).getMockImplementation()!;
    vi.mocked(serviceCall).mockImplementation(async (...args) => {
      const value = await implementation(...args) as { fields?: MasterField[] };
      if (value.fields) value.fields = value.fields.map(field => ({ ...field, visible: !['code', 'name', 'is_active', 'dimension', 'allowed_kind'].includes(field.key) }));
      return value as never;
    });
    const kind = config.resource === 'units' ? 'dimension=MASS' : config.resource === 'item-groups' ? 'allowed_kind=GOODS' : '';
    wrap(<CatalogMasterDirectory company={COMPANY} config={config} canManage initialQuery={'q=AB&sort=code&is_active=false&' + kind} />);
    expect(await screen.findByText(/Some search, filter or sort settings were removed/)).toBeVisible();
    await waitFor(() => expect(vi.mocked(serviceCall).mock.calls.some(([, request]) => request.path.includes(`/${config.resource}?`))).toBe(true));
    const collections = vi.mocked(serviceCall).mock.calls.filter(([, request]) => request.path.includes(`/${config.resource}?`));
    for (const [, request] of collections) expect(request.path).not.toMatch(/[?&](q|sort|is_active|dimension|allowed_kind)=/);
    expect(screen.queryByRole('searchbox')).not.toBeInTheDocument(); expect(screen.queryByRole('combobox', { name: 'Status' })).not.toBeInTheDocument();
  });
  it.each([unit, maker, group])('gives a reader an actionable empty $singular directory message', async config => {
    const implementation = vi.mocked(serviceCall).getMockImplementation()!;
    vi.mocked(serviceCall).mockImplementation(async (...args) => args[1].path.includes(`/${config.resource}?`) ? { items: [], page } as never : implementation(...args));
    wrap(<CatalogMasterDirectory company={COMPANY} config={config} canManage={false} />);
    expect(await screen.findByText(/Ask a company administrator to add/)).toBeVisible();
    expect(screen.queryByText(new RegExp(`Create a ${config.singular} to start`))).not.toBeInTheDocument();
  });
  it('disables saving when the only writable manufacturer field needs unavailable party access', async () => {
    const implementation = vi.mocked(serviceCall).getMockImplementation()!;
    vi.mocked(serviceCall).mockImplementation(async (...args) => {
      const value = await implementation(...args) as { fields?: MasterField[] };
      if (value.fields) value.fields = value.fields.map(field => ({ ...field, writable: field.key === 'party_id' }));
      return value as never;
    });
    wrap(<CatalogMasterEditor company={COMPANY} config={maker} id={ID} />);
    expect(await screen.findByRole('button', { name: 'Save changes' })).toBeDisabled();
  });
  it('recovers expired parent-history cursors from the first page', async () => {
    const implementation = vi.mocked(serviceCall).getMockImplementation()!;
    vi.mocked(serviceCall).mockImplementation(async (...args) => {
      if (args[1].path.includes('/parents?')) {
        if (args[1].path.includes('cursor=')) throw { status: 422, message: 'History page expired.', fields: { cursor: 'Expired.' } };
        return { items: [], page: { ...page, has_more: true, next_cursor: 'expired-page' } } as never;
      }
      return implementation(...args);
    });
    wrap(<CatalogMasterDetail company={COMPANY} config={group} id={ID} canManage />);
    const next = await screen.findByRole('button', { name: 'Next page of assignments' }); await waitFor(() => expect(next).toBeEnabled());
    await userEvent.click(next); await screen.findByText('History page expired.'); expect(next).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: 'Return to first history page' }));
    await waitFor(() => expect(screen.queryByText('History page expired.')).not.toBeInTheDocument());
    const calls = vi.mocked(serviceCall).mock.calls.filter(([, request]) => request.path.includes('/parents?'));
    expect(calls.at(-1)![1].path).not.toContain('cursor='); expect(screen.getByRole('button', { name: 'Deactivate item group' })).toBeEnabled();
  });
  it('keeps the selected manufacturer party name visible', async () => {
    wrap(<CatalogMasterEditor company={COMPANY} config={maker} canReadParty />);
    const party = await screen.findByRole('combobox', { name: 'Accounting party' });
    await userEvent.click(party); await userEvent.click(await screen.findByRole('option', { name: /Kilogram/ }));
    expect(party).toHaveValue('Kilogram');
  });
  it('shows and focuses a rejected parent selection during group creation', async () => {
    const implementation = vi.mocked(serviceCall).getMockImplementation()!;
    vi.mocked(serviceCall).mockImplementation(async (...args) => args[1].method === 'POST' ? Promise.reject({ status: 422, message: 'Check the hierarchy.', fields: { parent_group_id: 'Choose an active parent group.' } }) : implementation(...args));
    wrap(<CatalogMasterEditor company={COMPANY} config={group} />); await fill(group);
    await userEvent.click(screen.getByRole('button', { name: 'Create item group' }));
    expect(await screen.findByText('Choose an active parent group.')).toBeVisible();
    await waitFor(() => expect(screen.getByRole('combobox', { name: 'Parent group' })).toHaveFocus());
  });
  it.each([unit, maker, group])('avoids a redundant $singular write after normalized edits', async config => {
    wrap(<CatalogMasterEditor company={COMPANY} config={config} id={ID} />);
    const name = await screen.findByRole('textbox', { name: 'Name' }); await waitFor(() => expect(name).toHaveValue('Kilogram'));
    await userEvent.type(name, ' '); await userEvent.click(screen.getByRole('button', { name: 'Save changes' }));
    expect(await screen.findByText('No changes to save.')).toBeVisible(); expect(writes()).toHaveLength(0);
  });
  it.each([unit, maker, group])('guards company changes during a pending $singular lifecycle command', async config => {
    const implementation = vi.mocked(serviceCall).getMockImplementation()!; let resolve!: (row: never) => void;
    vi.mocked(serviceCall).mockImplementation(async (...args) => args[1].method === 'POST' ? new Promise<never>(done => { resolve = done; }) : implementation(...args));
    wrap(<CatalogMasterDetail company={COMPANY} config={config} id={ID} canManage />);
    await userEvent.click(await screen.findByRole('button', { name: `Deactivate ${config.singular}` }));
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Deactivate' }));
    expect(window.dispatchEvent(new Event(BEFORE_COMPANY_CHANGE, { cancelable: true }))).toBe(false);
    resolve({ ...original, is_active: false, row_version: 5 } as never); await screen.findByText(/deactivated. Existing records are retained/);
    expect(window.dispatchEvent(new Event(BEFORE_COMPANY_CHANGE, { cancelable: true }))).toBe(true);
  });
  it('retains group move field errors and guards the open hierarchy draft', async () => {
    const implementation = vi.mocked(serviceCall).getMockImplementation()!;
    vi.mocked(serviceCall).mockImplementation(async (...args) => args[1].method === 'POST' ? Promise.reject({ status: 422, message: 'Check the hierarchy.', fields: { parent_group_id: 'This parent would create a cycle.', effective_from: 'Choose a later date.' } }) : implementation(...args));
    wrap(<CatalogMasterDetail company={COMPANY} config={group} id={ID} canManage={false} canMove />);
    await userEvent.click(await screen.findByRole('button', { name: 'Change parent group' }));
    expect(window.dispatchEvent(new Event(BEFORE_COMPANY_CHANGE, { cancelable: true }))).toBe(false);
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Save parent change' }));
    expect(await screen.findByText('This parent would create a cycle.')).toBeVisible(); expect(screen.getByText('Choose a later date.')).toBeVisible();
    await waitFor(() => expect(screen.getByRole('combobox', { name: 'New parent group' })).toHaveFocus());
  });
  it('explains an uncertain lifecycle result and preserves its retry key', async () => {
    const implementation = vi.mocked(serviceCall).getMockImplementation()!;
    vi.mocked(serviceCall).mockImplementation(async (...args) => args[1].method === 'POST' ? Promise.reject({ status: 503, message: 'Connection lost.' }) : implementation(...args));
    wrap(<CatalogMasterDetail company={COMPANY} config={maker} id={ID} canManage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Deactivate manufacturer' }));
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Deactivate' }));
    expect(await screen.findByText(/change could not be confirmed/)).toBeVisible();
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Deactivate' }));
    await waitFor(() => expect(writes()).toHaveLength(2)); expect(writes()[1]![1].key).toBe(writes()[0]![1].key);
  });
  it.each([unit, maker, group])('creates $singular once with scoped metadata and an idempotency key', async config => {
    wrap(<CatalogMasterEditor company={COMPANY} config={config} />); await fill(config);
    await userEvent.dblClick(screen.getByRole('button', { name: `Create ${config.singular}` }));
    expect(await screen.findByText(new RegExp(config.singular.charAt(0).toUpperCase() + config.singular.slice(1) + ' created[.]'))).toBeVisible();
    expect(writes()).toHaveLength(1);
    expect(writes()[0]![1]).toMatchObject({ service: 'catalog', path: `/v1/companies/${COMPANY}/${config.resource}`, method: 'POST', key: expect.any(String) });
    expect(screen.getByRole('link', { name: `View ${config.singular}` })).toHaveAttribute('href', expect.stringContaining(ID));
    expect(vi.mocked(serviceCall).mock.calls.some(([, request]) => request.path.includes('object_id='))).toBe(false);
  });
  it('validates required fields and focuses the first invalid field without writing', async () => {
    wrap(<CatalogMasterEditor company={COMPANY} config={unit} />); await screen.findByRole('textbox', { name: 'Code' });
    await userEvent.click(screen.getByRole('button', { name: 'Create unit' }));
    expect(screen.getByText('Code is required.')).toBeVisible(); await waitFor(() => expect(screen.getByRole('textbox', { name: 'Code' })).toHaveFocus()); expect(writes()).toHaveLength(0);
  });
  it('patches changed fields with the version and preserves edits on conflict', async () => {
    const implementation = vi.mocked(serviceCall).getMockImplementation()!;
    vi.mocked(serviceCall).mockImplementation(async (...args) => args[1].method === 'PATCH' ? Promise.reject({ status: 409, message: 'Another user changed this record.' }) : implementation(...args));
    wrap(<CatalogMasterEditor company={COMPANY} config={unit} id={ID} />);
    const name = await screen.findByRole('textbox', { name: 'Name' }); await waitFor(() => expect(name).toHaveValue('Kilogram'));
    await userEvent.clear(name); await userEvent.type(name, 'New name'); await userEvent.click(screen.getByRole('button', { name: 'Save changes' }));
    expect(await screen.findByText(/Another user changed/)).toBeVisible(); expect(name).toHaveValue('New name');
    expect(writes()[0]![1].body).toEqual({ expected_version: 4, name: 'New name' });
  });
  it('retains the write key for retries and changes it after edits', async () => {
    const implementation = vi.mocked(serviceCall).getMockImplementation()!;
    vi.mocked(serviceCall).mockImplementation(async (...args) => args[1].method === 'POST' ? Promise.reject({ status: 503, message: 'Try again.' }) : implementation(...args));
    wrap(<CatalogMasterEditor company={COMPANY} config={maker} />); await fill(maker);
    await userEvent.click(screen.getByRole('button', { name: 'Create manufacturer' })); await screen.findByText('Try again.');
    await userEvent.click(screen.getByRole('button', { name: 'Create manufacturer' })); await waitFor(() => expect(writes()).toHaveLength(2));
    expect(writes()[0]![1].key).toBe(writes()[1]![1].key);
    await userEvent.type(screen.getByRole('textbox', { name: 'Name' }), ' changed'); await userEvent.click(screen.getByRole('button', { name: 'Create manufacturer' }));
    await waitFor(() => expect(writes()).toHaveLength(3)); expect(writes()[2]![1].key).not.toBe(writes()[1]![1].key);
  });
  it('explains that a failed connection cannot confirm whether the save completed', async () => {
    const implementation = vi.mocked(serviceCall).getMockImplementation()!;
    vi.mocked(serviceCall).mockImplementation(async (...args) => args[1].method === 'POST' ? Promise.reject({ status: 503, message: 'Connection lost.' }) : implementation(...args));
    wrap(<CatalogMasterEditor company={COMPANY} config={maker} />); await fill(maker); await userEvent.click(screen.getByRole('button', { name: 'Create manufacturer' }));
    expect(await screen.findByText(/save could not be confirmed/)).toBeVisible(); expect(screen.queryByText(/Nothing was changed/)).not.toBeInTheDocument();
  });
  it('shows server field validation and focuses the field', async () => {
    const implementation = vi.mocked(serviceCall).getMockImplementation()!;
    vi.mocked(serviceCall).mockImplementation(async (...args) => args[1].method === 'POST' ? Promise.reject({ status: 422, message: 'Code already exists.', fields: { code: 'Choose a different code.' } }) : implementation(...args));
    wrap(<CatalogMasterEditor company={COMPANY} config={maker} />); await fill(maker); await userEvent.click(screen.getByRole('button', { name: 'Create manufacturer' }));
    expect(await screen.findByText('Choose a different code.')).toBeVisible(); await waitFor(() => expect(screen.getByRole('textbox', { name: 'Code' })).toHaveFocus());
  });
  it('protects dirty navigation and company changes', async () => {
    wrap(<CatalogMasterEditor company={COMPANY} config={maker} />); await fill(maker);
    expect(window.dispatchEvent(new Event(BEFORE_COMPANY_CHANGE, { cancelable: true }))).toBe(false);
    await userEvent.click(screen.getByRole('link', { name: 'Cancel' }));
    expect(screen.getByRole('dialog', { name: 'Discard unsaved changes?' })).toBeVisible(); expect(goTo).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: 'Discard changes' })); expect(goTo).toHaveBeenCalledWith('/masters/manufacturers');
  });
  it('keeps the draft when a navigation discard is cancelled', async () => {
    wrap(<CatalogMasterEditor company={COMPANY} config={maker} />); await fill(maker);
    await userEvent.click(screen.getByRole('link', { name: 'Cancel' })); await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancel' }));
    expect(screen.getByRole('textbox', { name: 'Name' })).toHaveValue('Test master'); expect(goTo).not.toHaveBeenCalled();
  });
  it('changes dimension and precision while preserving an exact quantity increment', async () => {
    wrap(<CatalogMasterEditor company={COMPANY} config={unit} />); await fill(unit);
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Dimension' }), 'MASS'); await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Decimal places' }), '3');
    const increment = screen.getByRole('textbox', { name: 'Quantity increment' }); await userEvent.clear(increment); await userEvent.type(increment, '0.001');
    await userEvent.click(screen.getByRole('button', { name: 'Create unit' })); await screen.findByText('Unit created.'); expect(writes()[0]![1].body).toMatchObject({ dimension: 'MASS', decimal_places: 3, quantity_increment: '0.001' });
  });
  it('creates a dated group under a selected parent', async () => {
    const implementation = vi.mocked(serviceCall).getMockImplementation()!;
    vi.mocked(serviceCall).mockImplementation(async (...args) => args[1].path.includes('/item-groups?') ? { items: [{ ...original, id: OTHER, name: 'Parent group' }], page } as never : implementation(...args));
    wrap(<CatalogMasterEditor company={COMPANY} config={group} />); await fill(group);
    await userEvent.click(screen.getByRole('combobox', { name: 'Parent group' })); await userEvent.click(await screen.findByRole('option', { name: /Parent group/ }));
    const date = screen.getByLabelText('Effective from'); await userEvent.clear(date); await userEvent.type(date, '2026-10-20');
    await userEvent.click(screen.getByRole('button', { name: 'Create item group' })); await screen.findByText('Item group created.'); expect(writes()[0]![1].body).toMatchObject({ parent_group_id: OTHER, valid_from: '2026-10-20' });
  });
  it('links a manufacturer to an existing active Accounting party', async () => {
    wrap(<CatalogMasterEditor company={COMPANY} config={maker} canReadParty />); await fill(maker);
    await userEvent.click(screen.getByRole('combobox', { name: 'Accounting party' })); await userEvent.click(await screen.findByRole('option', { name: /Kilogram/ }));
    await userEvent.click(screen.getByRole('button', { name: 'Create manufacturer' })); await screen.findByText('Manufacturer created.'); expect(writes()[0]![1].body).toMatchObject({ party_id: ID });
  });
  it('resolves a dynamic custom field through its dated company option source', async () => {
    const implementation = vi.mocked(serviceCall).getMockImplementation()!;
    vi.mocked(serviceCall).mockImplementation(async (...args) => {
      if (args[1].path.includes('/option-sources/')) return { items: [{ value: OTHER, label: 'Option group', code: 'PARENT' }], page } as never;
      const value = await implementation(...args) as { fields?: MasterField[] };
      if (value.fields) value.fields.push({ key: 'custom_field:cf_group', label: 'Custom group', order: 90, source: 'custom', visible: true, writable: true, required: false, conditional_access: false, custom: { key: 'cf_group', data_type: 'dynamic_select', option_source_key: 'catalog.item_group', is_active: true, is_immutable_after_create: false, validation: { required: false, max_length: 100 }, choices: [] } });
      return value as never;
    });
    wrap(<CatalogMasterEditor company={COMPANY} config={maker} />); await fill(maker);
    await userEvent.click(screen.getByRole('combobox', { name: 'Custom group' })); await userEvent.type(screen.getByRole('combobox', { name: 'Custom group' }), 'Op');
    await userEvent.click(await screen.findByRole('option', { name: /Option group/ })); await userEvent.click(screen.getByRole('button', { name: 'Create manufacturer' })); await screen.findByText('Manufacturer created.');
    expect(writes()[0]![1].body).toMatchObject({ custom_fields: { cf_group: OTHER } }); expect(vi.mocked(serviceCall).mock.calls.some(([, request]) => request.path.includes('/option-sources/catalog.item_group?') && request.path.includes('as_of='))).toBe(true);
  });
  it('confirms discarding a conflicted edit before loading the latest record', async () => {
    const implementation = vi.mocked(serviceCall).getMockImplementation()!;
    vi.mocked(serviceCall).mockImplementation(async (...args) => args[1].method === 'PATCH' ? Promise.reject({ status: 409, message: 'Version changed.' }) : implementation(...args));
    wrap(<CatalogMasterEditor company={COMPANY} config={unit} id={ID} />);
    const name = await screen.findByRole('textbox', { name: 'Name' }); await waitFor(() => expect(name).toHaveValue('Kilogram'));
    await userEvent.type(name, ' edited'); await userEvent.click(screen.getByRole('button', { name: 'Save changes' }));
    await userEvent.click(await screen.findByRole('button', { name: 'Reload record' })); expect(name).toHaveValue('Kilogram edited');
    await userEvent.click(screen.getByRole('button', { name: 'Discard and reload' }));
    await waitFor(() => expect(screen.getByRole('textbox', { name: 'Name' })).toHaveValue('Kilogram'));
  });
  it('blocks duplicate submissions and navigation while saving', async () => {
    const implementation = vi.mocked(serviceCall).getMockImplementation()!; let resolve!: (row: never) => void;
    vi.mocked(serviceCall).mockImplementation(async (...args) => args[1].method === 'POST' ? new Promise<never>(done => { resolve = done; }) : implementation(...args));
    wrap(<CatalogMasterEditor company={COMPANY} config={maker} />); await fill(maker);
    await userEvent.dblClick(screen.getByRole('button', { name: 'Create manufacturer' })); expect(writes()).toHaveLength(1);
    expect(screen.getByRole('button', { name: 'Saving…' })).toBeDisabled(); await userEvent.click(screen.getByRole('link', { name: 'Cancel' })); expect(goTo).not.toHaveBeenCalled();
    resolve(original as never); await screen.findByText('Manufacturer created.');
  });
  it('queries active Accounting parties with its native status filter', async () => {
    wrap(<CatalogMasterEditor company={COMPANY} config={maker} canReadParty />);
    await userEvent.click(await screen.findByRole('combobox', { name: 'Accounting party' }));
    await waitFor(() => expect(vi.mocked(serviceCall).mock.calls.some(([, request]) => request.service === 'accounting' && request.path.includes('/parties?limit=50&status=ACTIVE'))).toBe(true));
    expect(vi.mocked(serviceCall).mock.calls.filter(([, request]) => request.service === 'accounting').every(([, request]) => !request.path.includes('is_active'))).toBe(true);
  });
  it('renders field access and validates required custom fields before writing', async () => {
    const implementation = vi.mocked(serviceCall).getMockImplementation()!;
    vi.mocked(serviceCall).mockImplementation(async (...args) => {
      const value = await implementation(...args) as { fields?: MasterField[] };
      if (value.fields) value.fields = [...value.fields.filter(field => field.key !== 'party_id'), { key: 'custom_field:cf_registration', label: 'Registration', order: 90, source: 'custom', visible: true, writable: true, required: true, conditional_access: false,
        custom: { key: 'cf_registration', data_type: 'text', is_active: true, is_immutable_after_create: false, validation: { required: true, max_length: 20 }, choices: [] } }];
      return value as never;
    });
    wrap(<CatalogMasterEditor company={COMPANY} config={maker} />); await fill(maker); await userEvent.click(screen.getByRole('button', { name: 'Create manufacturer' }));
    expect(screen.getByText('Registration is required.')).toBeVisible(); expect(writes()).toHaveLength(0);
    await userEvent.type(screen.getByRole('textbox', { name: 'Registration' }), 'REG-1'); await userEvent.click(screen.getByRole('button', { name: 'Create manufacturer' }));
    await screen.findByText('Manufacturer created.'); expect(writes()[0]![1].body).toMatchObject({ custom_fields: { cf_registration: 'REG-1' } });
  });
  it.each([401, 403, 404, 503])('handles failed form reads with status %s', async status => {
    vi.mocked(serviceCall).mockRejectedValue({ status, message: 'Unavailable for this request.' }); wrap(<CatalogMasterEditor company={COMPANY} config={maker} />);
    expect(await screen.findByText(status === 404 ? /record was not found/ : 'Unavailable for this request.')).toBeVisible(); expect(screen.queryByRole('button', { name: 'Create manufacturer' })).not.toBeInTheDocument();
  });
  it('filters and paginates the directory with shared query controls', async () => {
    const implementation = vi.mocked(serviceCall).getMockImplementation()!;
    vi.mocked(serviceCall).mockImplementation(async (...args) => args[1].path.includes('/units?') ? { items: [original], page: { ...page, has_more: true, next_cursor: 'next-page' } } as never : implementation(...args));
    wrap(<CatalogMasterDirectory company={COMPANY} config={unit} canManage />); await screen.findByRole('link', { name: 'Kilogram' });
    await userEvent.click(screen.getByRole('button', { name: 'Next page of units' })); await waitFor(() => expect(vi.mocked(serviceCall).mock.calls.some(([, request]) => request.path.includes('cursor=next-page'))).toBe(true));
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Status' }), 'false');
    await waitFor(() => expect(vi.mocked(serviceCall).mock.calls.filter(([, request]) => request.path.includes('/units?')).at(-1)?.[1].path).toContain('is_active=false'));
    expect(vi.mocked(serviceCall).mock.calls.filter(([, request]) => request.path.includes('/units?')).at(-1)?.[1].path).not.toContain('cursor=');
    expect(screen.getByRole('link', { name: 'New unit' })).toHaveAttribute('href', expect.stringContaining('returnTo='));
  });
  it('refreshes, filters, removes filters, sorts and opens an edit route from the directory', async () => {
    wrap(<CatalogMasterDirectory company={COMPANY} config={unit} canManage />); await screen.findByRole('link', { name: 'Kilogram' });
    await userEvent.click(screen.getByRole('button', { name: 'Refresh' })); await screen.findByRole('link', { name: 'Kilogram' });
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Dimension' }), 'MASS');
    await userEvent.click(await screen.findByRole('button', { name: /Remove filter: dimension/ }));
    await screen.findByRole('link', { name: 'Kilogram' }); await userEvent.click(screen.getByRole('button', { name: /Name/ }));
    await screen.findByRole('link', { name: 'Kilogram' }); await userEvent.click(screen.getByRole('button', { name: 'Actions for Kilogram' }));
    expect(screen.getByRole('menuitem', { name: 'Edit details' })).toHaveAttribute('href', expect.stringContaining(`/masters/units/${ID}/edit?returnTo=`));
  });
  it('offers a useful empty directory and no create action for a reader', async () => {
    const implementation = vi.mocked(serviceCall).getMockImplementation()!;
    vi.mocked(serviceCall).mockImplementation(async (...args) => args[1].path.includes('/manufacturers?') ? { items: [], page } as never : implementation(...args));
    wrap(<CatalogMasterDirectory company={COMPANY} config={maker} canManage={false} />);
    expect(await screen.findByText('No manufacturers yet')).toBeVisible(); expect(screen.queryByRole('link', { name: 'New manufacturer' })).not.toBeInTheDocument();
  });
  it('distinguishes an empty filtered list from a company with no masters', async () => {
    const implementation = vi.mocked(serviceCall).getMockImplementation()!;
    vi.mocked(serviceCall).mockImplementation(async (...args) => args[1].path.includes('/units?') ? { items: [], page } as never : implementation(...args));
    wrap(<CatalogMasterDirectory company={COMPANY} config={unit} canManage initialQuery="is_active=false" />);
    expect(await screen.findByText('No units match these filters')).toBeVisible(); expect(screen.getByRole('button', { name: 'Clear filters' })).toBeVisible();
    expect(screen.queryByText('No units yet')).not.toBeInTheDocument();
  });
  it('confirms lifecycle changes and sends only the concurrency precondition', async () => {
    wrap(<CatalogMasterDetail company={COMPANY} config={unit} id={ID} canManage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Deactivate unit' })); expect(writes()).toHaveLength(0);
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Deactivate' }));
    expect(await screen.findByText('Unit deactivated. Existing records are retained.')).toBeVisible();
    expect(writes()[0]![1]).toMatchObject({ path: `/v1/companies/${COMPANY}/units/${ID}/deactivate`, body: { expected_version: 4 }, key: expect.any(String) });
  });
  it('moves groups with dated history and both version checks', async () => {
    wrap(<CatalogMasterDetail company={COMPANY} config={group} id={ID} canManage={false} canMove />);
    await userEvent.click(await screen.findByRole('button', { name: 'Change parent group' }));
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Save parent change' }));
    expect(await screen.findByText(/Group parent updated/)).toBeVisible();
    expect(writes()[0]![1].body).toMatchObject({ expected_version: 4, expected_generation: 8, parent_group_id: null, effective_from: expect.stringMatching(/^\d{4}-\d\d-\d\d$/) });
  });
  it('loads parent history and distinguishes omitted values from explicit roots', async () => {
    const implementation = vi.mocked(serviceCall).getMockImplementation()!;
    vi.mocked(serviceCall).mockImplementation(async (...args) => args[1].path.includes('/parents?') ? { items: [{ id: 'root', parent_group_id: null, valid_from: '2026-01-01', valid_to: null }, { id: 'hidden', valid_from: '2026-02-01' }, { id: 'parent', parent_group_id: OTHER, valid_from: '2026-03-01' }], page } as never : implementation(...args));
    wrap(<CatalogMasterDetail company={COMPANY} config={group} id={ID} canManage={false} />);
    expect(await screen.findByText('Top-level group')).toBeVisible(); expect(screen.getAllByText('Top-level group')).toHaveLength(1);
    expect(screen.getByRole('link', { name: OTHER })).toHaveAttribute('href', expect.stringContaining('/masters/item-groups/' + OTHER + '?returnTo='));
  });
  it('cancels a lifecycle change and refreshes the saved record', async () => {
    wrap(<CatalogMasterDetail company={COMPANY} config={unit} id={ID} canManage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Deactivate unit' })); await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancel' })); expect(writes()).toHaveLength(0);
    await userEvent.click(screen.getByRole('button', { name: 'Reload record' })); await screen.findByRole('button', { name: 'Deactivate unit' });
  });
  it('changes the selected parent and effective date before moving a group', async () => {
    const implementation = vi.mocked(serviceCall).getMockImplementation()!;
    vi.mocked(serviceCall).mockImplementation(async (...args) => args[1].path.includes('/item-groups?') ? { items: [{ ...original, id: OTHER, name: 'Parent group' }], page } as never : implementation(...args));
    wrap(<CatalogMasterDetail company={COMPANY} config={group} id={ID} canManage={false} canMove />);
    await userEvent.click(await screen.findByRole('button', { name: 'Change parent group' }));
    await userEvent.click(screen.getByRole('combobox', { name: 'New parent group' })); await userEvent.click(await screen.findByRole('option', { name: /Parent group/ }));
    const date = screen.getByLabelText('Effective from'); await userEvent.clear(date); await userEvent.type(date, '2026-10-25');
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Save parent change' })); await screen.findByText(/Group parent updated/); expect(writes()[0]![1].body).toMatchObject({ parent_group_id: OTHER, effective_from: '2026-10-25' });
  });
  it('retries unavailable parent history without blocking group details', async () => {
    const implementation = vi.mocked(serviceCall).getMockImplementation()!; let unavailable = true;
    vi.mocked(serviceCall).mockImplementation(async (...args) => args[1].path.includes('/parents?') && unavailable ? Promise.reject({ status: 503, message: 'History temporarily unavailable.' }) : implementation(...args));
    wrap(<CatalogMasterDetail company={COMPANY} config={group} id={ID} canManage />);
    await screen.findByText('History temporarily unavailable.'); expect(screen.getByRole('button', { name: 'Deactivate item group' })).toBeEnabled(); unavailable = false;
    await userEvent.click(screen.getByRole('button', { name: 'Try again' })); await screen.findByText('No parent history');
  });
  it('rejects a response belonging to another company', async () => {
    const implementation = vi.mocked(serviceCall).getMockImplementation()!;
    vi.mocked(serviceCall).mockImplementation(async (...args) => args[1].path.endsWith(ID) ? { ...original, company_id: OTHER } as never : implementation(...args));
    wrap(<CatalogMasterDetail company={COMPANY} config={unit} id={ID} canManage />); expect(await screen.findByText(/did not match this company/)).toBeVisible(); expect(screen.queryByRole('button', { name: 'Deactivate unit' })).not.toBeInTheDocument();
  });
  it('rejects external return links and preserves supported internal master pages', () => {
    expect(masterReturnTo(unit, '//evil.test/masters/units')).toBe('/masters/units'); expect(masterReturnTo(unit, '/masters/manufacturers')).toBe('/masters/manufacturers');
    expect(masterReturnTo(unit, '/masters/units?cursor=secret&tenant_id=other&is_active=false')).toBe('/masters/units?limit=50&is_active=false');
  });
});
describe('master page and navigation authority', () => {
  it('renders permitted direct detail, edit and directory pages', async () => {
    const view = wrap(await CatalogMasterPage({ resource: 'units', record: [ID] })); await screen.findByRole('button', { name: 'Deactivate unit' }); view.unmount();
    const edit = wrap(await CatalogMasterPage({ resource: 'manufacturers', record: [ID, 'edit'] })); await screen.findByRole('textbox', { name: 'Name' }); edit.unmount();
    wrap(await CatalogMasterPage({ resource: 'item-groups' })); await screen.findByRole('link', { name: 'New item group' });
  });
  it('provides company selection when no company is open', async () => {
    const context = await pageContext(); context.session.company = { name: 'No company' };
    wrap(await CatalogMasterPage({ resource: 'units' })); expect(serviceCall).not.toHaveBeenCalled(); expect(screen.getByRole('link', { name: 'See the companies you can open' })).toHaveAttribute('href', '/companies');
  });
  it('requires active grants for the open company on direct URLs and navigation', async () => {
    const context = await pageContext(); context.session.permissions = ['unit.read', 'unit.manage']; context.session.grants![0]!.scope_id = OTHER;
    wrap(await CatalogMasterPage({ resource: 'units', record: ['new'] })); expect(screen.getByText(/You need unit.read and unit.manage/)).toBeVisible(); expect(serviceCall).not.toHaveBeenCalled();
    expect(navigationFor(context.session).flatMap(section => flattenNavigation(section.items)).some(item => item.href === '/masters/units')).toBe(false);
    context.session.grants![0]!.scope_id = COMPANY;
    expect(navigationFor(context.session).flatMap(section => flattenNavigation(section.items)).some(item => item.href === '/masters')).toBe(true);
    expect(companyMastersFor(context.session).flatMap(section => section.items).some(item => item.href === '/masters/units')).toBe(true);
  });
  it('rejects unknown resources and malformed route segments before service reads', async () => {
    await expect(CatalogMasterPage({ resource: 'anything' })).rejects.toThrow('not found');
    await expect(CatalogMasterPage({ resource: 'units', record: ['invalid'] })).rejects.toThrow('not found');
    await expect(CatalogMasterPage({ resource: 'units', record: ['new', 'edit'] })).rejects.toThrow('not found'); expect(serviceCall).not.toHaveBeenCalled();
  });
});
