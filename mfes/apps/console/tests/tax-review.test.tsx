import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { DisplayConfigProvider, PermissionProvider } from '@janso/ui';
import { TaxEditor } from '../app/components/TaxEditor';
import { TaxDetail } from '../app/components/TaxDetail';
import { TaxDirectory } from '../app/components/TaxDirectory';
import { serviceCall } from '../app/lib/service-call';
import { taxConfig } from '../app/lib/tax-masters';
import { CATEGORY, COMPANY, CLASSIFICATION, RATE, SERIES, context, fixtureResponse } from './tax-fixtures';

vi.mock('../app/lib/service-call', async original => ({ ...await original<typeof import('../app/lib/service-call')>(), serviceCall: vi.fn() }));
vi.mock('../app/lib/navigate', () => ({ goTo: vi.fn(), signInUrl: () => '/sign-in' }));
const category = taxConfig('categories')!, rates = taxConfig('rates')!, classification = taxConfig('classifications')!;
const wrap = (node: React.ReactNode) => render(<PermissionProvider permissions={[]}><DisplayConfigProvider config={{ timezone: 'Asia/Kolkata', currency: 'INR' }}>{node}</DisplayConfigProvider></PermissionProvider>);
const writes = () => vi.mocked(serviceCall).mock.calls.filter(([, request]) => ['POST', 'PATCH'].includes(request.method ?? 'GET'));
beforeEach(() => { vi.clearAllMocks(); window.history.replaceState(null, '', '/'); vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => fixtureResponse(request) as never); });
describe('tax review findings and recovery', () => {
  it('keeps a protected status unchanged while an allowed name is saved', async () => {
    vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => { const value = fixtureResponse(request) as { fields?: { key: string; writable: boolean }[] }; if (value.fields) value.fields = value.fields.map(field => ({ ...field, writable: field.writable && field.key !== 'is_active' })); return value as never; });
    wrap(<TaxEditor company={COMPANY} config={category} id={CATEGORY} />);
    const name = await screen.findByRole('textbox', { name: 'Name' }); await userEvent.clear(name); await userEvent.type(name, 'Updated'); expect(screen.getByRole('combobox', { name: 'Active' })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: 'Save changes' })); expect(await screen.findByText('Tax category updated successfully.')).toBeVisible(); expect(writes()[0]?.[1].body).toMatchObject({ name: 'Updated', is_active: true });
  });
  it('does not create an empty revision when nothing changed', async () => {
    wrap(<TaxEditor company={COMPANY} config={category} id={CATEGORY} />); await userEvent.click(await screen.findByRole('button', { name: 'Save changes' })); expect(await screen.findByText('No changes to save.')).toBeVisible(); expect(writes()).toHaveLength(0);
  });
  it('requires discard confirmation before replacing a conflicted draft with current values', async () => {
    vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => { if (request.method === 'PATCH') throw { status: 409, message: 'Version changed' }; return fixtureResponse(request) as never; });
    wrap(<TaxEditor company={COMPANY} config={category} id={CATEGORY} />); const name = await screen.findByRole('textbox', { name: 'Name' }); await userEvent.clear(name); await userEvent.type(name, 'Retained'); await userEvent.click(screen.getByRole('button', { name: 'Save changes' }));
    await userEvent.click(await screen.findByRole('button', { name: 'Reload and review' })); const dialog = screen.getByRole('dialog'); expect(dialog).toHaveTextContent('Your unsaved values will be replaced'); await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel' })); expect(name).toHaveValue('Retained');
  });
  it('blocks creation when a required field is protected', async () => {
    vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => { const value = fixtureResponse(request) as { fields?: { key: string; writable: boolean }[] }; if (value.fields) value.fields = value.fields.map(field => ({ ...field, writable: field.writable && field.key !== 'code' })); return value as never; });
    wrap(<TaxEditor company={COMPANY} config={category} />); expect(await screen.findByRole('button', { name: 'Create tax category' })).toBeDisabled(); expect(screen.getByRole('textbox', { name: 'Code' })).toBeDisabled(); expect(writes()).toHaveLength(0);
  });
  it('enforces paired GST percentages before a preview request', async () => {
    wrap(<TaxEditor company={COMPANY} config={rates} seriesId={SERIES} />); await waitFor(() => expect(screen.getAllByRole('textbox', { name: 'Percentage' })).toHaveLength(2)); const percentages = screen.getAllByRole('textbox', { name: 'Percentage' }); await userEvent.type(percentages[0]!, '2'); await userEvent.type(percentages[1]!, '3'); await userEvent.click(screen.getByRole('button', { name: 'Review publication' })); expect(await screen.findByText('Central and state/territory percentages and rounding must match.')).toBeVisible(); expect(writes()).toHaveLength(0);
  });
  it('does not offer publication from a read-only rate-series filter', async () => {
    wrap(<TaxDirectory company={COMPANY} config={rates} canManage={false} canPublish={false} initialQuery={'series_id=' + SERIES} />); await screen.findByRole('table', { name: 'Tax rates directory' }); expect(screen.queryByRole('link', { name: 'Publish a rate in this series' })).not.toBeInTheDocument();
  });
  it('does not offer mutation actions for an already withdrawn definition', async () => {
    vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => request.path.includes('/tax-history-actions?') ? { items: [{ id: RATE, action: 'WITHDRAW' }], page: { limit: 50, has_more: false, next_cursor: null } } as never : fixtureResponse(request) as never);
    wrap(<TaxDetail company={COMPANY} config={classification} id={CLASSIFICATION} canManage canPublish />); expect(await screen.findByText('This definition is withdrawn. Its details remain available as publication evidence.')).toBeVisible(); expect(screen.queryByRole('button', { name: 'Tax record actions' })).not.toBeInTheDocument();
  });
  it('disables withdrawal when a definition is already effective today', async () => {
    vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => { const value = fixtureResponse(request); return request.path.endsWith('/' + CLASSIFICATION) ? { ...value as object, valid_from: context.business_date } as never : value as never; });
    wrap(<TaxDetail company={COMPANY} config={classification} id={CLASSIFICATION} canManage canPublish />); await userEvent.click(await screen.findByRole('button', { name: 'Tax record actions' })); expect(screen.getByRole('menuitem', { name: /Withdraw future definition/ })).toHaveAttribute('aria-disabled', 'true');
  });
});
