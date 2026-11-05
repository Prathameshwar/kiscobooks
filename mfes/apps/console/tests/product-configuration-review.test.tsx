import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { DisplayConfigProvider } from '@janso/ui';
import { ProductConfigurationDetail } from '../app/components/ProductConfigurationDetail';
import { ProductConfigurationEditor } from '../app/components/ProductConfigurationEditor';
import { ProductConfigurationDirectory, ProductConfigurationScope } from '../app/components/ProductConfigurationDirectory';
import { ProductConfigurationEffective } from '../app/components/ProductConfigurationInspect';
import { ProductConfigurationAdoption } from '../app/components/ProductConfigurationInspect';
import { ConfigurationEffectiveValues, ConfigurationFailure, ConfigurationReference, ConfigurationValues } from '../app/components/ProductConfigurationCommon';
import { serviceCall } from '../app/lib/service-call';
import { goTo } from '../app/lib/navigate';
import { COMPANY, DRAFT, ITEM, SCOPE, REVISION, effective, metadata, response } from './product-configuration-fixtures';
vi.mock('../app/lib/service-call', async original => ({ ...await original<typeof import('../app/lib/service-call')>(), serviceCall: vi.fn() }));
vi.mock('../app/lib/navigate', () => ({ goTo: vi.fn(), signInUrl: () => '/signin' }));
const writes = () => vi.mocked(serviceCall).mock.calls.filter(([, request]) => request.method === 'POST' || request.method === 'PATCH');
function wrap(node: React.ReactNode) { return render(<DisplayConfigProvider config={{ timezone: 'Asia/Kolkata' }}>{node}</DisplayConfigProvider>); }
beforeEach(() => { vi.clearAllMocks(); vi.mocked(serviceCall).mockImplementation(async (_, request) => response(request.path, request.method) as never); });
it('keeps inspection navigation and the leave guard when opening a source revision', async () => {
  const leave = vi.fn(event => event.preventDefault()), here = '/products/configuration/effective?returnTo=%2Fsettings';
  wrap(<ConfigurationEffectiveValues value={{ ...effective, sources: [{ scope_kind: 'COMPANY', revision: 1, revision_id: REVISION, effective_from: '2028-01-01' }] as typeof effective.sources }} returnTo={here} onLeave={leave} />);
  const link = screen.getByRole('link', { name: /View revision effective/ });
  expect(new URL(link.getAttribute('href')!, 'https://console.invalid').searchParams.get('returnTo')).toBe(here);
  await userEvent.click(link); expect(leave).toHaveBeenCalled();
});
it('uses company date formatting for readable configuration dates', () => {
  wrap(<ConfigurationValues title="Draft dates" fields={metadata.details} values={{ effective_from: '2028-01-01' }} />);
  expect(screen.getByText('01 Jan 2028')).toBeVisible();
});
it('retains the directory and settings origin when creating a scope draft', async () => {
  const directory = '/products/configuration?returnTo=%2Fsettings';
  wrap(<ProductConfigurationScope company={COMPANY} id={SCOPE} canManage returnTo={directory} />);
  const link = await screen.findByRole('link', { name: 'New draft' });
  expect(new URL(link.getAttribute('href')!, 'https://console.invalid').searchParams.get('returnTo')).toBe('/products/configuration/scopes/' + SCOPE + '?returnTo=' + encodeURIComponent(directory));
});
it('marks and focuses the invalid inspection date without sending a read', async () => {
  wrap(<ProductConfigurationEffective company={COMPANY} timezone="Asia/Kolkata" />);
  const date = screen.getByLabelText('As of date'); await userEvent.clear(date);
  await userEvent.click(screen.getByRole('button', { name: 'Inspect settings' }));
  expect(date).toHaveAttribute('aria-invalid', 'true'); expect(date).toHaveFocus();
  expect(vi.mocked(serviceCall).mock.calls.some(([, request]) => request.path.includes('/product-configuration/effective'))).toBe(false);
});
it('inspects company defaults without requesting an owner selection', async () => {
  wrap(<ProductConfigurationEffective company={COMPANY} timezone="Asia/Kolkata" />);
  await userEvent.click(screen.getByRole('button', { name: 'Inspect settings' }));
  expect(await screen.findByText('Inheritance and protection')).toBeVisible();
  expect(screen.queryByRole('combobox', { name: 'Inspect context' })).not.toBeInTheDocument();
  expect(writes()).toHaveLength(0);
});
it('marks and focuses a missing product before adoption review', async () => {
  wrap(<ProductConfigurationAdoption company={COMPANY} timezone="Asia/Kolkata" canAdopt />);
  await userEvent.click(screen.getByRole('button', { name: 'Review adoption' }));
  const item = screen.getByRole('combobox', { name: 'Product / SKU' });
  expect(item).toHaveAttribute('aria-invalid', 'true'); expect(item).toHaveFocus();
  expect(writes()).toHaveLength(0);
});
it('offers the first company configuration directly while preserving the settings destination', async () => {
  const answer = vi.mocked(serviceCall).getMockImplementation()!;
  vi.mocked(serviceCall).mockImplementation((...args) => args[1].path.includes('/product-configuration-scopes?')
    ? Promise.resolve({ items: [], page: { limit: 2, has_more: false, next_cursor: null } }) : answer(...args));
  wrap(<ProductConfigurationDirectory company={COMPANY} canManage initialQuery="scope_kind=GROUP&returnTo=%2Fsettings" />);
  expect(await screen.findByRole('link', { name: 'Create company configuration' })).toHaveAttribute('href', expect.stringContaining('/new'));
  expect(screen.queryByRole('combobox', { name: 'Scope filter' })).not.toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Back to company settings' })).toHaveAttribute('href', '/settings');
});
it('lets a user close and reopen an uncertain publication without losing its exact replay identity', async () => {
  const implementation = vi.mocked(serviceCall).getMockImplementation()!; let attempts = 0;
  vi.mocked(serviceCall).mockImplementation(async (...args) => { if (args[1].path.endsWith('/publish') && attempts++ === 0) throw { status: 503, message: 'Unconfirmed publication' }; return implementation(...args); });
  wrap(<ProductConfigurationDetail company={COMPANY} id={DRAFT} canManage canPublish timezone="Asia/Kolkata" />); await userEvent.click(await screen.findByRole('button', { name: 'Review publication' })); await userEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Publish revision' })); await screen.findByRole('button', { name: 'Retry same publication' }); await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancel' })); await userEvent.click(screen.getByRole('button', { name: 'Recover publication' })); await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Retry same publication' })); await waitFor(() => expect(goTo).toHaveBeenCalled()); expect(writes()[0][1].key).toBe(writes()[1][1].key); expect(writes()[0][1].body).toEqual(writes()[1][1].body);
});
it('locks an aggregate numeric editor when any collection field is not writable', async () => {
  const implementation = vi.mocked(serviceCall).getMockImplementation()!;
  vi.mocked(serviceCall).mockImplementation(async (...args) => { const value = structuredClone(await implementation(...args)) as { fields?: { key: string; writable: boolean }[] }; if (args[1].path.includes('catalog.product_numeric_default')) value.fields!.find(field => field.key === 'price_increment')!.writable = false; return value as never; });
  wrap(<ProductConfigurationEditor company={COMPANY} scopeId={SCOPE} timezone="Asia/Kolkata" />); expect(await screen.findByRole('button', { name: 'Add dimension defaults' })).toBeDisabled(); expect(screen.getByText(/Numeric defaults are read-only/)).toBeVisible();
});
it('does not offer a mode change that would clear a protected paired value', async () => {
  const implementation = vi.mocked(serviceCall).getMockImplementation()!;
  vi.mocked(serviceCall).mockImplementation(async (...args) => { const value = structuredClone(await implementation(...args)) as { fields?: { key: string; writable: boolean }[] }; if (args[1].path.includes('catalog.product_entry_option_policy')) value.fields!.find(field => field.key === 'barcode_default')!.writable = false; return value as never; });
  wrap(<ProductConfigurationEditor company={COMPANY} id={DRAFT} timezone="Asia/Kolkata" />); const mode = await screen.findByRole('combobox', { name: 'Barcode' }); expect(within(mode).getByRole('option', { name: 'Disabled' })).toBeDisabled(); expect(screen.getByRole('combobox', { name: 'Enable barcode by default' })).toBeDisabled();
});
it('recovers an uncertain first company draft without enabling a different request', async () => {
  const implementation = vi.mocked(serviceCall).getMockImplementation()!; let attempts = 0;
  vi.mocked(serviceCall).mockImplementation(async (...args) => { if (args[1].method === 'POST' && attempts++ === 0) throw { status: 503, message: 'Unknown result' }; return implementation(...args); });
  wrap(<ProductConfigurationEditor company={COMPANY} timezone="Asia/Kolkata" />);
  const reason = await screen.findByRole('textbox', { name: 'Reason for change' });
  await userEvent.type(reason, 'Initial company settings');
  await userEvent.click(screen.getByRole('button', { name: 'Save draft' }));
  const retry = await screen.findByRole('button', { name: 'Retry same draft save' });
  expect(reason).toBeDisabled(); await userEvent.click(retry);
  await waitFor(() => expect(goTo).toHaveBeenCalled());
  expect(writes()[0][1].key).toBe(writes()[1][1].key);
  expect(writes()[0][1].body).toEqual(writes()[1][1].body);
});
it('reports an unavailable retained reference instead of inventing an option label', async () => {
  vi.mocked(serviceCall).mockResolvedValue({ items: [], page: { limit: 1, has_more: false, next_cursor: null } });
  wrap(<ConfigurationReference company={COMPANY} source="items" value={ITEM} label="Product / SKU" onChange={() => {}} />); expect(await screen.findByText(/This reference is unavailable/)).toBeVisible(); expect(screen.getByRole('combobox', { name: 'Product / SKU' })).not.toHaveValue(ITEM);
});
it('offers authentication recovery for an expired session and respects a denied scope', () => {
  const view = wrap(<ConfigurationFailure failure={{ status: 401, message: 'Session expired' }} />); expect(screen.getByRole('link', { name: 'Sign in again' })).toHaveAttribute('href', expect.stringContaining('/signin?returnTo=')); view.rerender(<ConfigurationFailure failure={{ status: 403, message: 'Scope denied' }} retry={() => {}} />); expect(screen.getByText('Scope denied')).toBeVisible(); expect(screen.queryByRole('button')).not.toBeInTheDocument();
});
it('links the company draft and publication history with the settings destination', async () => {
  wrap(<ProductConfigurationDirectory company={COMPANY} canManage initialQuery="returnTo=%2Fsettings" />);
  expect(await screen.findByRole('link', { name: 'Edit company configuration' })).toHaveAttribute('href', expect.stringContaining('/drafts/' + DRAFT + '/edit'));
  const history = screen.getByRole('link', { name: 'Publication history' });
  expect(history).toHaveAttribute('href', expect.stringContaining('/scopes/' + SCOPE));
  expect(new URL(history.getAttribute('href')!, 'https://console.invalid').searchParams.get('returnTo')).toBe('/products/configuration?returnTo=%2Fsettings');
});
