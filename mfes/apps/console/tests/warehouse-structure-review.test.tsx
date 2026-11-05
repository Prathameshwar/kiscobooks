import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { DisplayConfigProvider, PermissionProvider } from '@janso/ui';
import { WarehouseStructureChange } from '../app/components/WarehouseStructureChange';
import { WarehouseStructureDirectory } from '../app/components/WarehouseStructureDirectory';
import { CatalogMasterDetail } from '../app/components/CatalogMasterDetail';
import { masterConfig } from '../app/lib/catalog-masters';
import { serviceCall } from '../app/lib/service-call';
import { access, COMPANY, GROUP, WAREHOUSE, BIN, fixtureResponse } from './warehouse-structure-fixtures';

vi.mock('../app/lib/service-call', async original => ({ ...await original<typeof import('../app/lib/service-call')>(), serviceCall: vi.fn() }));
vi.mock('../app/lib/navigate', () => ({ goTo: vi.fn(), signInUrl: () => '/sign-in' }));
vi.mock('../app/components/WarehouseOperationPolicy', () => ({ WarehouseOperationPolicy: () => null }));
beforeEach(() => { vi.clearAllMocks(); vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => fixtureResponse(request) as never); });
async function review() {
  render(<PermissionProvider permissions={[]}><DisplayConfigProvider config={{ timezone: 'Asia/Kolkata' }}><WarehouseStructureChange company={COMPANY} id={GROUP} canChange access={access} /></DisplayConfigProvider></PermissionProvider>);
  await userEvent.click(await screen.findByRole('combobox', { name: 'Parent group' })); await userEvent.click(await screen.findByRole('option', { name: /South region/ })); await userEvent.click(screen.getByRole('button', { name: 'Review dated change' }));
}
it('names the exact target in the dated-change review', async () => {
  await review(); const heading = screen.getByRole('heading', { name: 'Review dated change' }), card = heading.closest('.janso-card')!;
  expect(await within(card as HTMLElement).findByText('South region')).toBeVisible();
});
it('maps native effective-date validation to the displayed date control', async () => {
  vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => { if (request.method === 'POST') throw { status: 422, message: 'Invalid dated change', fields: { effective_from: 'Choose a later effective date.' } }; return fixtureResponse(request) as never; });
  await review(); await userEvent.click(screen.getByRole('button', { name: 'Confirm dated change' }));
  expect(await screen.findByText('Choose a later effective date.')).toBeVisible(); await waitFor(() => expect(screen.getByLabelText('Effective from')).toHaveFocus());
});
it('shows native command validation that has no editable control', async () => {
  vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => { if (request.method === 'POST') throw { status: 422, message: 'Invalid dated change', fields: { expected_generation: 'Reload the current warehouse policy.' } }; return fixtureResponse(request) as never; });
  await review(); await userEvent.click(screen.getByRole('button', { name: 'Confirm dated change' })); expect(await screen.findByText('Reload the current warehouse policy.')).toBeVisible();
});
function wrap(node: React.ReactNode) { return render(<PermissionProvider permissions={[]}><DisplayConfigProvider config={{ timezone: 'Asia/Kolkata' }}>{node}</DisplayConfigProvider></PermissionProvider>); }
it('returns a filtered bin directory to its originating warehouse', async () => {
  const back = '/masters/warehouses/' + WAREHOUSE;
  wrap(<WarehouseStructureDirectory company={COMPANY} config={masterConfig('warehouse-bins')!} canManage access={access} initialQuery={new URLSearchParams({ warehouse_id: WAREHOUSE, returnTo: back }).toString()} />);
  expect(await screen.findByRole('link', { name: 'Back to warehouses' })).toHaveAttribute('href', back);
});
it.each(['/masters/warehouse-groups/' + GROUP, '/masters/warehouse-bins/' + BIN])('returns warehouse details to the originating structure page %s', async back => {
  wrap(<CatalogMasterDetail company={COMPANY} config={masterConfig('warehouses')!} id={WAREHOUSE} returnTo={back} canManage={false} />);
  await screen.findByRole('heading', { name: 'Main warehouse' });
  expect(document.querySelector('a[href="' + back + '"]')).not.toBeNull();
});
it('includes warehouse return navigation in its bins link', async () => {
  wrap(<CatalogMasterDetail company={COMPANY} config={masterConfig('warehouses')!} id={WAREHOUSE} canManage={false} canReadWarehouseBins />);
  const link = await screen.findByRole('link', { name: 'Bins / racks in this warehouse' });
  expect(new URL(link.getAttribute('href')!, 'https://console.invalid').searchParams.get('returnTo')).toBe('/masters/warehouses/' + WAREHOUSE);
});
it('keeps the warehouse return link when clearing directory filters', async () => {
  const back = '/masters/warehouses/' + WAREHOUSE;
  wrap(<WarehouseStructureDirectory company={COMPANY} config={masterConfig('warehouse-bins')!} canManage access={access} initialQuery={new URLSearchParams({ warehouse_id: WAREHOUSE, q: 'Rack', returnTo: back }).toString()} />);
  await userEvent.click(await screen.findByRole('button', { name: 'Clear all' }));
  expect(screen.getByRole('link', { name: 'Back to warehouses' })).toHaveAttribute('href', back);
});
