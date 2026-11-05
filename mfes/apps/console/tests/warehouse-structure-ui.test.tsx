import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { DisplayConfigProvider, PermissionProvider } from '@janso/ui';
import { WarehouseStructureDirectory } from '../app/components/WarehouseStructureDirectory';
import { WarehouseStructureEditor } from '../app/components/WarehouseStructureEditor';
import { WarehouseStructureDetail } from '../app/components/WarehouseStructureDetail';
import { WarehouseStructureChange } from '../app/components/WarehouseStructureChange';
import { StructureReference } from '../app/components/WarehouseStructureCommon';
import { masterConfig } from '../app/lib/catalog-masters';
import { serviceCall } from '../app/lib/service-call';
import { BEFORE_COMPANY_CHANGE } from '../app/lib/use-unsaved-changes';
import { COMPANY, GROUP, OTHER, WAREHOUSE, BIN, FRESH, access, context, group, page, fixtureResponse, structureFields } from './warehouse-structure-fixtures';

vi.mock('../app/lib/service-call', async original => ({ ...await original<typeof import('../app/lib/service-call')>(), serviceCall: vi.fn() }));
vi.mock('../app/lib/navigate', () => ({ goTo: vi.fn(), signInUrl: () => '/sign-in' }));
const groups = masterConfig('warehouse-groups')!, bins = masterConfig('warehouse-bins')!;
const wrap = (node: React.ReactNode) => render(<PermissionProvider permissions={[]}><DisplayConfigProvider config={{ timezone: 'Asia/Kolkata', currency: 'INR' }}>{node}</DisplayConfigProvider></PermissionProvider>);
const writes = () => vi.mocked(serviceCall).mock.calls.filter(([, request]) => ['POST', 'PATCH', 'PUT'].includes(request.method ?? 'GET'));
async function fill() { await userEvent.type(await screen.findByRole('textbox', { name: 'Code' }), 'TEST'); await userEvent.type(screen.getByRole('textbox', { name: 'Name' }), 'Test structure'); }
beforeEach(() => { vi.clearAllMocks(); window.history.replaceState(null, '', '/'); vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => fixtureResponse(request) as never); });
describe('warehouse structure directories and forms', () => {
  it.each([groups, bins])('renders $title and navigation with native metadata', async config => {
    wrap(<WarehouseStructureDirectory company={COMPANY} config={config} canManage access={access} />);
    expect(await screen.findByRole('table', { name: config.title + ' directory' })).toBeVisible(); expect(screen.getByRole('link', { name: 'New ' + config.singular })).toHaveAttribute('href', expect.stringContaining('/masters/' + config.resource + '/new'));
    await waitFor(() => expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()); expect(screen.getByRole('navigation', { name: 'Warehouse structure' })).toBeVisible();
  });
  it('preserves the warehouse filter in detail and create navigation', async () => {
    wrap(<WarehouseStructureDirectory company={COMPANY} config={bins} canManage access={access} initialQuery={'warehouse_id=' + WAREHOUSE + '&q=Rack&limit=25'} />);
    const create = await screen.findByRole('link', { name: 'New bin / rack' }); expect(create.getAttribute('href')).toContain('warehouse_id=' + WAREHOUSE);
    await screen.findByRole('link', { name: 'Rack one' }); expect(screen.getByRole('link', { name: 'Rack one' }).getAttribute('href')).toContain('returnTo=');
    expect(vi.mocked(serviceCall).mock.calls.some(([, request]) => request.path.includes('/warehouse-bins?') && request.path.includes('warehouse_id=' + WAREHOUSE))).toBe(true);
  });
  it('creates a dated group and returns to the filtered directory', async () => {
    wrap(<WarehouseStructureEditor company={COMPANY} config={groups} access={access} returnTo="/masters/warehouse-groups?q=North" />); await fill();
    expect(screen.getByLabelText('Effective from')).toHaveValue(context.business_date); await userEvent.click(screen.getByRole('button', { name: 'Create warehouse group' }));
    expect(await screen.findByText('warehouse group created successfully.')).toBeVisible(); expect(writes()[0]?.[1].body).toEqual({ code: 'TEST', name: 'Test structure', parent_group_id: null, valid_from: context.business_date }); expect(screen.getByRole('link', { name: 'View warehouse group' }).getAttribute('href')).toContain(FRESH);
  });
  it('creates a bin with searchable warehouse selection', async () => {
    wrap(<WarehouseStructureEditor company={COMPANY} config={bins} access={access} />); await fill(); await userEvent.click(screen.getByRole('combobox', { name: 'Warehouse' })); await userEvent.click(await screen.findByRole('option', { name: /Main warehouse/ })); await userEvent.click(screen.getByRole('button', { name: 'Create bin / rack' }));
    expect(await screen.findByText('bin / rack created successfully.')).toBeVisible(); expect(writes()[0]?.[1].body).toEqual({ code: 'TEST', name: 'Test structure', warehouse_id: WAREHOUSE });
  });
  it('validates required fields and focuses the first failure', async () => {
    wrap(<WarehouseStructureEditor company={COMPANY} config={groups} access={access} />); await userEvent.click(await screen.findByRole('button', { name: 'Create warehouse group' })); expect(await screen.findByText('Code is required.')).toBeVisible(); await waitFor(() => expect(screen.getByRole('textbox', { name: 'Code' })).toHaveFocus()); expect(writes()).toHaveLength(0);
  });
  it('edits labels without changing warehouse or lifecycle', async () => {
    wrap(<WarehouseStructureEditor company={COMPANY} config={bins} id={BIN} access={access} />); const name = await screen.findByRole('textbox', { name: 'Name' }); expect(screen.getByRole('combobox', { name: 'Warehouse' })).toBeDisabled(); await userEvent.clear(name); await userEvent.type(name, 'Updated rack'); await userEvent.click(screen.getByRole('button', { name: 'Save changes' })); expect(await screen.findByText('bin / rack updated successfully.')).toBeVisible(); expect(writes()[0]?.[1].body).toEqual({ name: 'Updated rack', expected_version: 4 });
  });
  it('does not submit unchanged edits', async () => {
    wrap(<WarehouseStructureEditor company={COMPANY} config={groups} id={GROUP} access={access} />); await userEvent.click(await screen.findByRole('button', { name: 'Save changes' })); expect(await screen.findByText('No changes to save.')).toBeVisible(); expect(writes()).toHaveLength(0);
  });
  it('allows bin label updates without unrelated warehouse read access', async () => {
    wrap(<WarehouseStructureEditor company={COMPANY} config={bins} id={BIN} access={{ ...access, warehouses: false }} />);
    expect(await screen.findByRole('button', { name: 'Save changes' })).toBeEnabled();
    expect(vi.mocked(serviceCall).mock.calls.some(([, request]) => request.path.includes('/warehouses/'))).toBe(false);
  });
  it('blocks create with field denies and unavailable warehouse access', async () => {
    vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => { const result = fixtureResponse(request); if (request.path.includes('warehouse_bin/field-set')) return { ...result as object, fields: structureFields('catalog.warehouse_bin').filter(field => field.key !== 'code') } as never; return result as never; });
    wrap(<WarehouseStructureEditor company={COMPANY} config={bins} access={{ ...access, warehouses: false }} />); const button = await screen.findByRole('button', { name: 'Create bin / rack' }); expect(button).toBeDisabled(); expect(vi.mocked(serviceCall).mock.calls.some(([, request]) => request.path.includes('/warehouses'))).toBe(false);
  });
  it('retains denied-field history without exposing a hidden group reference', async () => {
    vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => request.path.includes('warehouse_group_parent/field-set') ? { company_id: COMPANY, entity_type: 'catalog.warehouse_group_parent', fields: structureFields('catalog.warehouse_group_parent').filter(field => field.key !== 'parent_group_id') } as never : fixtureResponse(request) as never);
    wrap(<WarehouseStructureDetail company={COMPANY} config={groups} id={GROUP} canManage={false} canMove={false} access={{ ...access, warehouses: false }} />); const table = await screen.findByRole('table', { name: 'Parent group history' }); expect(within(table).queryByRole('columnheader', { name: 'Parent group' })).not.toBeInTheDocument(); expect(screen.queryByRole('button', { name: 'Warehouse structure actions' })).not.toBeInTheDocument(); expect(vi.mocked(serviceCall).mock.calls.some(([, request]) => request.path.includes('/members'))).toBe(false);
  });
  it('keeps unconfirmed saves locked and retries the same body and key', async () => {
    let count = 0; vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => { if (request.method === 'POST' && ++count === 1) throw { status: 503, message: 'Temporary outage' }; return fixtureResponse(request) as never; });
    wrap(<WarehouseStructureEditor company={COMPANY} config={groups} access={access} />); await fill(); await userEvent.click(screen.getByRole('button', { name: 'Create warehouse group' })); expect(await screen.findByText(/save is unconfirmed/)).toBeVisible(); expect(screen.getByRole('textbox', { name: 'Name' })).toBeDisabled(); await userEvent.click(screen.getByRole('button', { name: 'Retry same save' })); expect(await screen.findByText('warehouse group created successfully.')).toBeVisible(); expect(writes()).toHaveLength(2); expect(writes()[0]?.[1].key).toBe(writes()[1]?.[1].key); expect(writes()[0]?.[1].body).toEqual(writes()[1]?.[1].body);
  });
  it('retains the draft after 422 and permits corrected resubmission', async () => {
    let count = 0; vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => { if (request.method === 'POST' && ++count === 1) throw { status: 422, message: 'Invalid code', fields: { code: 'Code is reserved.' } }; return fixtureResponse(request) as never; });
    wrap(<WarehouseStructureEditor company={COMPANY} config={groups} access={access} />); await fill(); await userEvent.click(screen.getByRole('button', { name: 'Create warehouse group' })); expect(await screen.findByText('Code is reserved.')).toBeVisible(); const code = screen.getByRole('textbox', { name: 'Code' }); await userEvent.clear(code); await userEvent.type(code, 'VALID'); await userEvent.click(screen.getByRole('button', { name: 'Create warehouse group' })); expect(await screen.findByText('warehouse group created successfully.')).toBeVisible();
  });
  it('requires review before retrying a version conflict', async () => {
    vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => { if (request.method === 'POST') throw { status: 409, message: 'Version changed' }; return fixtureResponse(request) as never; }); wrap(<WarehouseStructureEditor company={COMPANY} config={groups} access={access} />); await fill(); await userEvent.click(screen.getByRole('button', { name: 'Create warehouse group' })); await userEvent.click(await screen.findByRole('button', { name: 'Reload and review' })); expect(screen.getByRole('dialog', { name: 'Reload current warehouse record?' })).toBeVisible(); await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Reload and review' })); await waitFor(() => expect(screen.getByRole('textbox', { name: 'Name' })).toHaveValue('')); expect(writes()).toHaveLength(1);
  });
  it('guards back navigation and company switching when dirty', async () => {
    wrap(<WarehouseStructureEditor company={COMPANY} config={groups} access={access} />); await fill(); const event = new Event(BEFORE_COMPANY_CHANGE, { cancelable: true }); window.dispatchEvent(event); expect(event.defaultPrevented).toBe(true); await userEvent.click(screen.getByRole('link', { name: /Back to/ })); expect(screen.getByRole('dialog', { name: 'Discard unsaved changes?' })).toBeVisible();
  });
  it.each([401, 403, 404, 503])('renders a useful %i load failure', async status => {
    vi.mocked(serviceCall).mockRejectedValue({ status, message: 'Warehouse loading failed' }); wrap(<WarehouseStructureEditor company={COMPANY} config={groups} access={access} />); expect(await screen.findByText('Warehouse loading failed')).toBeVisible(); expect(screen.queryByRole('button', { name: 'Create warehouse group' })).not.toBeInTheDocument();
  });
  it('hydrates selected references and omits internal transit options', async () => {
    vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => { if (request.path.includes('/warehouses?')) return { items: [{ ...group, id: OTHER, kind: 'INTERNAL_TRANSIT', name: 'Internal transit' }, { ...group, id: WAREHOUSE, kind: 'STORE', name: 'Main warehouse' }], page } as never; return fixtureResponse(request) as never; }); wrap(<StructureReference company={COMPANY} resource="warehouses" label="Warehouse" value={WAREHOUSE} onChange={() => {}} />); await waitFor(() => expect(screen.getByRole('combobox', { name: 'Warehouse' })).toHaveValue('Main warehouse')); await userEvent.click(screen.getByRole('combobox', { name: 'Warehouse' })); expect(await screen.findByRole('option', { name: /Main warehouse/ })).toBeVisible(); expect(screen.queryByRole('option', { name: /Internal transit/ })).not.toBeInTheDocument();
  });
});
describe('warehouse dated structure and lifecycle', () => {
  async function chooseSouth(label: string) { await userEvent.click(await screen.findByRole('combobox', { name: label })); await userEvent.click(await screen.findByRole('option', { name: /South region/ })); }
  it.each([false, true])('reviews and saves the dated assignment=%s command', async assignment => {
    wrap(<WarehouseStructureChange company={COMPANY} id={assignment ? WAREHOUSE : GROUP} assignment={assignment} canChange access={access} />); await chooseSouth(assignment ? 'Warehouse group' : 'Parent group'); await userEvent.click(screen.getByRole('button', { name: 'Review dated change' })); expect(writes()).toHaveLength(0); await userEvent.click(screen.getByRole('button', { name: 'Confirm dated change' })); expect(await screen.findByText(/change saved/)).toBeVisible(); expect(writes()[0]?.[1]).toMatchObject({ method: assignment ? 'PUT' : 'POST', body: { expected_version: 4, expected_generation: 10, [assignment ? 'group_id' : 'parent_group_id']: OTHER, effective_from: context.business_date } });
  });
  it('prevents backdated changes and unchanged parent targets', async () => {
    wrap(<WarehouseStructureChange company={COMPANY} id={GROUP} canChange access={access} />); await screen.findByRole('button', { name: 'Review dated change' }); await userEvent.click(screen.getByRole('button', { name: 'Review dated change' })); expect(await screen.findByText(/Choose a different group/)).toBeVisible(); await chooseSouth('Parent group'); await userEvent.clear(screen.getByLabelText('Effective from')); await userEvent.type(screen.getByLabelText('Effective from'), '2020-01-01'); await userEvent.click(screen.getByRole('button', { name: 'Review dated change' })); expect(await screen.findByText(/Existing intervals cannot be rewritten/)).toBeVisible(); expect(writes()).toHaveLength(0);
  });
  it('retries an unconfirmed dated change with the same key and body', async () => {
    let count = 0; vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => { if (request.method === 'PUT' && ++count === 1) throw { status: 503, message: 'Offline' }; return fixtureResponse(request) as never; }); wrap(<WarehouseStructureChange company={COMPANY} id={WAREHOUSE} assignment canChange access={access} />); await chooseSouth('Warehouse group'); await userEvent.click(screen.getByRole('button', { name: 'Review dated change' })); await userEvent.click(screen.getByRole('button', { name: 'Confirm dated change' })); await userEvent.click(await screen.findByRole('button', { name: 'Retry same dated change' })); expect(await screen.findByText(/change saved/)).toBeVisible(); expect(writes()[0]?.[1].key).toBe(writes()[1]?.[1].key); expect(writes()[0]?.[1].body).toEqual(writes()[1]?.[1].body);
  });
  it('presents membership history for read-only users', async () => { wrap(<WarehouseStructureChange company={COMPANY} id={WAREHOUSE} assignment canChange={false} access={access} />); expect(await screen.findByText(/Read-only access/)).toBeVisible(); expect(screen.queryByRole('button', { name: 'Review dated change' })).not.toBeInTheDocument(); expect(screen.getByRole('table', { name: 'Primary group history' })).toBeVisible(); });
  it('uses the shared kebab for versioned lifecycle changes', async () => {
    wrap(<WarehouseStructureDetail company={COMPANY} config={bins} id={BIN} canManage canMove={false} access={access} />); await userEvent.click(await screen.findByRole('button', { name: 'Warehouse structure actions' })); await userEvent.click(screen.getByRole('menuitem', { name: 'Deactivate' })); await userEvent.click(screen.getByRole('button', { name: 'Confirm deactivation' })); expect(await screen.findByText(/deactivated. Existing history/)).toBeVisible(); expect(writes()[0]?.[1].body).toEqual({ expected_version: 4 });
  });
});
