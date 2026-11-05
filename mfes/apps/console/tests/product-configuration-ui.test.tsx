import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { DisplayConfigProvider, PermissionProvider } from '@janso/ui';
import { ProductConfigurationEditor } from '../app/components/ProductConfigurationEditor';
import { ProductConfigurationDetail } from '../app/components/ProductConfigurationDetail';
import { ProductConfigurationDirectory, ProductConfigurationScope } from '../app/components/ProductConfigurationDirectory';
import { ProductConfigurationAdoption, ProductConfigurationEffective } from '../app/components/ProductConfigurationInspect';
import { ConfigurationReference, ConfigurationValues } from '../app/components/ProductConfigurationCommon';
import { serviceCall } from '../app/lib/service-call';
import { goTo } from '../app/lib/navigate';
import { BEFORE_COMPANY_CHANGE } from '../app/lib/use-unsaved-changes';
import { COMPANY, DRAFT, ITEM, REVISION, SCOPE, draft, metadata, publication, response } from './product-configuration-fixtures';
vi.mock('../app/lib/service-call', async original => ({ ...await original<typeof import('../app/lib/service-call')>(), serviceCall: vi.fn() }));
vi.mock('../app/lib/navigate', () => ({ goTo: vi.fn(), signInUrl: () => '/signin' }));
const writes = () => vi.mocked(serviceCall).mock.calls.filter(([, request]) => ['POST', 'PATCH'].includes(request.method ?? 'GET'));
function wrap(node: React.ReactNode) { return render(<PermissionProvider permissions={[]}><DisplayConfigProvider config={{ timezone: 'Asia/Kolkata', currency: 'INR' }}>{node}</DisplayConfigProvider></PermissionProvider>); }
beforeEach(() => { vi.clearAllMocks(); window.history.replaceState(null, '', '/products/configuration'); vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => response(request.path, request.method) as never); });

it('groups configuration draft sections within one form card and keeps actions in its footer', async () => {
  wrap(<ProductConfigurationEditor company={COMPANY} id={DRAFT} timezone="Asia/Kolkata" />);
  const save = await screen.findByRole('button', { name: 'Save draft changes' });
  const form = save.closest('form')!;
  expect(form.closest('.janso-grid--split')).not.toBeNull();
  expect(within(form).getByRole('heading', { level: 2, name: 'Draft details' })).toBeVisible();
  expect(form.querySelectorAll('.janso-card')).toHaveLength(1);
  expect(within(save.closest('.janso-card__footer')!).getByRole('link', { name: 'Cancel' })).toBeVisible();
});
describe('company configuration editor', () => {
  it('validates a retained new draft, renders metadata controls and saves without blocking successful navigation', async () => {
    wrap(<ProductConfigurationEditor company={COMPANY} scopeId={SCOPE} timezone="Asia/Kolkata" returnTo="/settings" />);
    const reason = await screen.findByRole('textbox', { name: 'Reason for change' });
    await userEvent.click(screen.getByRole('button', { name: 'Save draft' })); expect(await screen.findByText(/Enter printable text/)).toBeVisible(); expect(reason).toHaveFocus(); expect(writes()).toHaveLength(0);
    await userEvent.type(reason, 'Initial defaults'); await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Barcode' }), 'OPTIONAL'); expect(screen.getByRole('combobox', { name: 'Enable barcode by default' })).toHaveValue('false');
    await userEvent.click(screen.getByRole('button', { name: 'Save draft' })); await waitFor(() => expect(goTo).toHaveBeenCalledWith('/products/configuration/drafts/' + DRAFT + '?returnTo=%2Fsettings'));
    expect(writes()[0][1]).toMatchObject({ method: 'POST', path: `/v1/companies/${COMPANY}/product-configurations/company`, body: { options: { barcode_mode: 'OPTIONAL', barcode_default: false } }, key: expect.any(String) });
    const event = new Event(BEFORE_COMPANY_CHANGE, { cancelable: true }); act(() => { window.dispatchEvent(event); }); expect(event.defaultPrevented).toBe(false);
  });
  it('clears an obsolete option default atomically and sends only the changed fields', async () => {
    wrap(<ProductConfigurationEditor company={COMPANY} id={DRAFT} timezone="Asia/Kolkata" />); await userEvent.selectOptions(await screen.findByRole('combobox', { name: 'Barcode' }), 'DISABLED'); expect(screen.queryByRole('combobox', { name: 'Enable barcode by default' })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Save draft changes' })); await waitFor(() => expect(writes()).toHaveLength(1)); expect(writes()[0][1].body).toEqual({ expected_version: 3, options: { barcode_mode: 'DISABLED', barcode_default: null } });
  });
  it('keeps exact numeric input and rejects precision mismatch before a save', async () => {
    wrap(<ProductConfigurationEditor company={COMPANY} scopeId={SCOPE} timezone="Asia/Kolkata" />); await userEvent.type(await screen.findByRole('textbox', { name: 'Reason for change' }), 'Numeric defaults'); await userEvent.click(screen.getByRole('button', { name: 'Add dimension defaults' }));
    await userEvent.type(screen.getByRole('textbox', { name: 'quantity decimal places' }), '3'); await userEvent.type(screen.getByRole('textbox', { name: 'quantity increment' }), '0.0011'); await userEvent.click(screen.getByRole('button', { name: 'Save draft' })); expect(await screen.findByText(/Enter a positive exact decimal/)).toBeVisible(); expect(writes()).toHaveLength(0);
    await userEvent.clear(screen.getByRole('textbox', { name: 'quantity increment' })); await userEvent.type(screen.getByRole('textbox', { name: 'quantity increment' }), '0.0010'); await userEvent.click(screen.getByRole('button', { name: 'Save draft' })); await waitFor(() => expect(writes()).toHaveLength(1)); expect(writes()[0][1].body).toMatchObject({ numeric_defaults: [{ dimension: 'COUNT', quantity_increment: '0.0010' }] });
  });
  it('retains and freezes an uncertain save and retries its exact body/key', async () => {
    const original = vi.mocked(serviceCall).getMockImplementation()!; let attempts = 0;
    vi.mocked(serviceCall).mockImplementation(async (...args) => { if (args[1].method === 'PATCH' && attempts++ === 0) throw { status: 503, message: 'Connection interrupted' }; return original(...args); });
    wrap(<ProductConfigurationEditor company={COMPANY} id={DRAFT} timezone="Asia/Kolkata" />); const reason = await screen.findByRole('textbox', { name: 'Reason for change' }); await userEvent.clear(reason); await userEvent.type(reason, 'Retained reason'); await userEvent.click(screen.getByRole('button', { name: 'Save draft changes' }));
    const retry = await screen.findByRole('button', { name: 'Retry same draft save' }); expect(reason).toHaveValue('Retained reason'); expect(reason).toBeDisabled(); await userEvent.click(retry); await waitFor(() => expect(goTo).toHaveBeenCalled()); expect(writes()[0][1].key).toBe(writes()[1][1].key); expect(writes()[0][1].body).toEqual(writes()[1][1].body);
  });
  it('retains unsaved values on a version conflict and requires explicit discard before reloading', async () => {
    const original = vi.mocked(serviceCall).getMockImplementation()!; vi.mocked(serviceCall).mockImplementation(async (...args) => { if (args[1].method === 'PATCH') throw { status: 409, message: 'Draft changed' }; return original(...args); });
    wrap(<ProductConfigurationEditor company={COMPANY} id={DRAFT} timezone="Asia/Kolkata" />); const reason = await screen.findByRole('textbox', { name: 'Reason for change' }); await userEvent.type(reason, ' retained'); await userEvent.click(screen.getByRole('button', { name: 'Save draft changes' })); await userEvent.click(await screen.findByRole('button', { name: 'Reload and review' })); expect(screen.getByRole('dialog', { name: "Discard this draft's unsaved changes?" })).toBeVisible(); await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancel' })); expect(reason).toHaveValue(draft.change_reason + ' retained');
  });
  it('blocks copying masked source settings and offers sign-in after an expired session', async () => {
    const original = vi.mocked(serviceCall).getMockImplementation()!; vi.mocked(serviceCall).mockImplementation(async (...args) => { const value = await original(...args) as { configuration_complete?: boolean }; if (args[1].path.includes('catalog.product_entry_option_policy')) value.configuration_complete = false; return value as never; });
    wrap(<ProductConfigurationEditor company={COMPANY} scopeId={SCOPE} timezone="Asia/Kolkata" />); expect(await screen.findByText(/Some configuration fields are protected/)).toBeVisible(); expect(screen.queryByRole('button', { name: 'Save draft' })).not.toBeInTheDocument();
  });
  it('opens a company draft without a scope selector and keeps settings return navigation', async () => {
    wrap(<ProductConfigurationEditor company={COMPANY} timezone="Asia/Kolkata" returnTo="/settings" />);
    expect(await screen.findByRole('textbox', { name: 'Reason for change' })).toBeVisible();
    expect(screen.queryByRole('combobox', { name: 'Configuration applies to' })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Back to company settings' })).toHaveAttribute('href', '/settings');
    expect(writes()).toHaveLength(0);
  });
});
describe('publication, history and scoped lookup', () => {
  it('requires an explicit server review and publishes its exact checkpoints', async () => {
    wrap(<ProductConfigurationDetail company={COMPANY} id={DRAFT} canManage canPublish timezone="Asia/Kolkata" />); await userEvent.click(await screen.findByRole('button', { name: 'Review publication' })); const dialog = await screen.findByRole('dialog', { name: 'Publish these product defaults?' }); expect(writes()).toHaveLength(0); expect(within(dialog).getByText('Reviewed product defaults')).toBeVisible(); await userEvent.click(within(dialog).getByRole('button', { name: 'Publish revision' })); await waitFor(() => expect(goTo).toHaveBeenCalled()); expect(writes()[0][1].body).toEqual({ expected_version: 3, expected_generation: 4, expected_source_version: 7 });
  });
  it('rejects a stale review before exposing publish confirmation', async () => {
    const original = vi.mocked(serviceCall).getMockImplementation()!; vi.mocked(serviceCall).mockImplementation(async (...args) => args[1].path.endsWith('/preview') ? { ...publication, draft_version: 99 } as never : original(...args));
    wrap(<ProductConfigurationDetail company={COMPANY} id={DRAFT} canManage canPublish timezone="Asia/Kolkata" />); await userEvent.click(await screen.findByRole('button', { name: 'Review publication' })); expect(await screen.findByText(/draft review could not be verified/)).toBeVisible(); expect(screen.queryByRole('dialog')).not.toBeInTheDocument(); expect(writes()).toHaveLength(0);
  });
  it('keeps revisions immutable and readers have no edit or publish actions', async () => {
    wrap(<ProductConfigurationDetail company={COMPANY} id={REVISION} revision canManage canPublish timezone="Asia/Kolkata" />); expect(await screen.findByText('Published configuration revision')).toBeVisible(); expect(await screen.findByText('Reviewed product defaults')).toBeVisible(); expect(screen.queryByRole('link', { name: 'Edit draft' })).not.toBeInTheDocument(); expect(screen.queryByRole('button', { name: 'Review publication' })).not.toBeInTheDocument();
  });
  it('shows current scope history with links and no edit actions for a reader', async () => {
    wrap(<ProductConfigurationScope company={COMPANY} id={SCOPE} canManage={false} />); await userEvent.click(await screen.findByRole('button', { name: /Actions for Draft effective/ })); expect(await screen.findByRole('menuitem', { name: 'View draft' })).toHaveAttribute('href', expect.stringContaining('/drafts/' + DRAFT)); expect(screen.queryByRole('menuitem', { name: 'Edit draft' })).not.toBeInTheDocument();
  });
  it('hides mutation actions in a read-only directory and preserves its back destination', async () => {
    wrap(<ProductConfigurationDirectory company={COMPANY} canManage={false} initialQuery="returnTo=%2Fsettings" />); expect(await screen.findByRole('link', { name: 'Review draft' })).toBeVisible(); expect(screen.queryByRole('link', { name: 'Edit company configuration' })).not.toBeInTheDocument(); expect(screen.getByRole('link', { name: 'Back to company settings' })).toHaveAttribute('href', '/settings');
  });
  it('hydrates a stored reference by exact id and supports search without fabricated values', async () => {
    wrap(<ConfigurationReference company={COMPANY} source="product-type-revisions" kind="GOODS" value={ITEM} label="Goods type" onChange={() => {}} />); const input = await screen.findByRole('combobox', { name: 'Goods type' }); await waitFor(() => expect(input).toHaveValue('General products')); expect(vi.mocked(serviceCall).mock.calls[0][1].path).toContain('value=' + ITEM); await userEvent.click(input); await userEvent.clear(input); await userEvent.type(input, 'General'); expect(await screen.findByRole('option', { name: /General products/ })).toBeVisible();
  });
  it('renders human reference labels for readonly values', async () => { wrap(<ConfigurationValues company={COMPANY} title="Profiles" fields={metadata.profiles} values={{ goods_type_revision_mode: 'VALUE', goods_type_revision_id: ITEM }} />); expect(await screen.findByText('General products')).toBeVisible(); expect(screen.queryByText(ITEM)).not.toBeInTheDocument(); });
});
describe('effective settings and explicit draft adoption', () => {
  it('inspects the selected context without mutating and clears stale results after a date edit', async () => {
    wrap(<ProductConfigurationEffective company={COMPANY} timezone="Asia/Kolkata" />); await userEvent.click(screen.getByRole('button', { name: 'Inspect settings' })); expect(await screen.findByText('Inheritance and protection')).toBeVisible(); expect(writes()).toHaveLength(0); await userEvent.clear(screen.getByLabelText('As of date')); await waitFor(() => expect(screen.queryByText('Inheritance and protection')).not.toBeInTheDocument());
  });
  it('requires adoption authority without issuing a preview or picker request', () => { wrap(<ProductConfigurationAdoption company={COMPANY} timezone="Asia/Kolkata" canAdopt={false} />); expect(screen.getByText(/adopt permission in this company/)).toBeVisible(); expect(serviceCall).not.toHaveBeenCalled(); });
  it('reviews a signed adoption and commits only after explicit confirmation', async () => {
    wrap(<ProductConfigurationAdoption company={COMPANY} timezone="Asia/Kolkata" canAdopt />); const input = screen.getByRole('combobox', { name: 'Product / SKU' }); await userEvent.click(input); await userEvent.click(await screen.findByRole('option', { name: /General products/ })); await userEvent.click(screen.getByRole('button', { name: 'Review adoption' })); await userEvent.click(await screen.findByRole('button', { name: 'Adopt reviewed draft defaults' })); expect(writes()).toHaveLength(0); const dialog = screen.getByRole('dialog'); await userEvent.click(within(dialog).getByRole('button', { name: 'Adopt draft defaults' })); expect(await screen.findByText(/adopted successfully/)).toBeVisible(); expect(writes()[0][1].body).toMatchObject({ expected_version: 2, preview_token: 'opaque-review' }); expect(screen.queryByText('opaque-review')).not.toBeInTheDocument();
  });
  it('explains blocked active products and never offers a commit', async () => {
    const original = vi.mocked(serviceCall).getMockImplementation()!; vi.mocked(serviceCall).mockImplementation(async (...args) => { const value = await original(...args); return args[1].path.includes('/configuration-adoption/preview') ? { ...value as object, eligible: false, blocked_reasons: ['active_structural_adoption_unsupported'] } as never : value; });
    wrap(<ProductConfigurationAdoption company={COMPANY} timezone="Asia/Kolkata" canAdopt />); await userEvent.click(screen.getByRole('combobox', { name: 'Product / SKU' })); await userEvent.click(await screen.findByRole('option', { name: /General products/ })); await userEvent.click(screen.getByRole('button', { name: 'Review adoption' })); expect(await screen.findByText(/Structural adoption is supported only for drafts/)).toBeVisible(); expect(screen.queryByRole('button', { name: 'Adopt reviewed draft defaults' })).not.toBeInTheDocument(); expect(writes()).toHaveLength(0);
  });
});
