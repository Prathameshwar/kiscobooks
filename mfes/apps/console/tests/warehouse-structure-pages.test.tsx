import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CatalogMasterPage } from '../app/components/CatalogMasterPage';
import { pageContext } from '../app/lib/page-context';
import { navigationFor, flattenNavigation } from '../app/nav';
import { companyMastersFor } from '../app/lib/company-masters';
import { sessionFor, companyContextFor } from './helpers';

const company = '01990000-0000-7000-8000-000000000001', id = '01990000-0000-7000-8000-000000000002';
vi.mock('../app/lib/page-context', () => ({ pageContext: vi.fn() }));
vi.mock('../app/providers', () => ({ Providers: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/components/ConsoleShell', () => ({ ConsoleShell: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/components/NoCompany', () => ({ NoCompany: () => <p>Select a company</p> }));
vi.mock('../app/components/WarehouseStructureDirectory', () => ({ WarehouseStructureDirectory: () => <p>Structure directory</p> }));
vi.mock('../app/components/WarehouseStructureEditor', () => ({ WarehouseStructureEditor: () => <p>Structure editor</p> }));
vi.mock('../app/components/WarehouseStructureDetail', () => ({ WarehouseStructureDetail: () => <p>Structure detail</p> }));
vi.mock('../app/components/WarehouseStructureChange', () => ({ WarehouseStructureChange: ({ assignment, canChange }: { assignment: boolean; canChange: boolean }) => <p>{assignment ? 'Membership' : 'Parent'} {canChange ? 'editor' : 'reader'}</p> }));
vi.mock('next/navigation', () => ({ notFound: () => { throw new Error('not found'); } }));
async function actor(permissions: string[], scope = company) {
  const session = await sessionFor(); session.company = { id: company, name: 'Acme' }; session.permissions = []; session.grants = [{ scope_type: 'company', scope_id: scope, valid_from: '2020-01-01', valid_to: null, permissions }];
  vi.mocked(pageContext).mockResolvedValue({ session, context: companyContextFor() }); return session;
}
beforeEach(async () => { vi.clearAllMocks(); await actor(['warehouse.read', 'warehouse.manage', 'warehouse_group.read', 'warehouse_group.manage', 'warehouse_group.move', 'warehouse_bin.read', 'warehouse_bin.manage']); });
describe('warehouse structure routes and scoped navigation', () => {
  it.each(['warehouse-groups', 'warehouse-bins'])('opens every %s management page', async resource => {
    for (const [record, text] of [[[], 'Structure directory'], [['new'], 'Structure editor'], [[id], 'Structure detail'], [[id, 'edit'], 'Structure editor']] as const) {
      const view = render(await CatalogMasterPage({ resource, record: [...record] })); expect(screen.getByText(text)).toBeVisible(); view.unmount();
    }
  });
  it('keeps group move authority separate from management', async () => {
    await actor(['warehouse_group.read', 'warehouse_group.move']); render(await CatalogMasterPage({ resource: 'warehouse-groups', record: [id, 'reparent'] })); expect(screen.getByText('Parent editor')).toBeVisible();
  });
  it('allows membership history with both read permissions', async () => {
    await actor(['warehouse.read', 'warehouse_group.read']); render(await CatalogMasterPage({ resource: 'warehouses', record: [id, 'group'] })); expect(screen.getByText('Membership reader')).toBeVisible();
  });
  it('requires both manage permissions to change membership', async () => {
    await actor(['warehouse.read', 'warehouse.manage', 'warehouse_group.read']); render(await CatalogMasterPage({ resource: 'warehouses', record: [id, 'group'] })); expect(screen.getByText('Membership reader')).toBeVisible();
  });
  it.each([['warehouse-groups', ['new']], ['warehouse-bins', [id, 'edit']], ['warehouse-groups', [id, 'reparent']], ['warehouses', [id, 'group']]])('denies unauthorized %s actions', async (resource, record) => {
    await actor(['warehouse.read', 'warehouse_group.read', 'warehouse_bin.read'], id); render(await CatalogMasterPage({ resource, record })); expect(screen.getByText(/You need/)).toBeVisible();
  });
  it('shows only permitted company menu links', async () => {
    const session = await actor(['warehouse_bin.read']); const links = flattenNavigation(navigationFor(session).flatMap(section => section.items)).map(item => item.href);
    expect(links).toContain('/masters');
    const cards = companyMastersFor(session).flatMap(section => section.items).map(item => item.href);
    expect(cards).toContain('/masters/warehouse-bins'); expect(cards).not.toContain('/masters/warehouse-groups'); expect(cards).not.toContain('/masters/warehouses');
  });
  it('requires an open company', async () => { const session = await actor(['warehouse_group.read']); session.company = { name: 'Select company' }; render(await CatalogMasterPage({ resource: 'warehouse-groups' })); expect(screen.getByText('Select a company')).toBeVisible(); });
  it.each([['warehouse-bins', [id, 'reparent']], ['warehouse-groups', ['bad']], ['warehouse-bins', [id, 'group']], ['warehouse-groups', [id, 'delete']]])('rejects invalid %s paths', async (resource, record) => expect(CatalogMasterPage({ resource, record })).rejects.toThrow('not found'));
});
