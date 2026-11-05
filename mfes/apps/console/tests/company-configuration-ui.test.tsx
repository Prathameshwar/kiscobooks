import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { CompanyConfiguration } from '../app/components/CompanyConfiguration';
import { companyCall } from '../app/lib/company-api';
import { BEFORE_COMPANY_CHANGE } from '../app/lib/use-unsaved-changes';
import { goTo } from '../app/lib/navigate';
import { renderWithProviders, sessionFor } from './helpers';
import { companyId } from './access-fixtures';
vi.mock('../app/lib/company-api', () => ({ companyCall: vi.fn(), companyFailure: (error: unknown) => error }));
vi.mock('../app/lib/navigate', () => ({ goTo: vi.fn(), stepUpUrl: () => '/verify', signInUrl: () => '/login' }));
const stamp = '2026-10-24T10:00:00Z';
const catalogue = { items: [
  { key: 'inventory', label: 'Stock and inventory', description: 'Track stock', requires: [], tax_systems: [], locks: true },
  { key: 'batch_tracking', label: 'Batches', description: 'Track batches', requires: ['inventory'], tax_systems: [], locks: true },
  { key: 'budgets', label: 'Budgets', description: 'Plan budgets', requires: [], tax_systems: [], locks: false },
  { key: 'multi_currency', label: 'Foreign currency', description: 'Foreign documents', requires: [], tax_systems: [], locks: true },
  { key: 'e_invoicing', label: 'GST e-invoicing', description: 'GST invoices', requires: [], tax_systems: ['gst_in'], locks: true },
] };
const feature = (feature_key: string, state = 'DISABLED', extra = {}) => ({ feature_key, state, required_features: feature_key === 'batch_tracking' ? ['inventory'] : [], missing_prerequisites: [], tax_system_supported: true, locked_at: null, lock_reason: null, source_updated_at: stamp, ...extra });
let profile: Record<string, unknown>, setup: Record<string, unknown> & { features: ReturnType<typeof feature>[] };
async function mount(keys = ['company.read', 'company.update']) {
  const session = await sessionFor({ permissions: keys }); session.company = { id: companyId, name: 'Retail' };
  session.grants = [{ scope_type: 'company', scope_id: companyId, permissions: keys, valid_from: '2000-01-01', valid_to: null }];
  return renderWithProviders(<CompanyConfiguration session={session} companyId={companyId} returnTo="/companies/manage?q=Re" />);
}
beforeEach(() => {
  vi.clearAllMocks(); profile = { id: companyId, display_name: 'Retail', code: 'RT', status: 'active', updated_at: stamp, default_tax_system: 'gst_in', base_currency: 'INR', timezone: 'Asia/Kolkata' };
  setup = { company_id: companyId, company_status: 'active', company_updated_at: stamp, frozen_company_fields: [], features: [feature('inventory'), feature('batch_tracking'), feature('budgets', 'ENABLED'), feature('multi_currency', 'ENABLED', { locked_at: stamp, lock_reason: 'foreign_currency_posting' }), feature('e_invoicing', 'DISABLED', { tax_system_supported: false })] };
  vi.mocked(companyCall).mockImplementation(async (_service, path, request) => {
    if (request?.method === 'POST') {
      const key = path.split('/').at(-2)!, on = path.endsWith('/enable');
      setup.features.find(row => row.feature_key === key)!.state = on ? 'ENABLED' : 'DISABLED';
      if (key === 'batch_tracking' && on) setup.features[0].state = 'ENABLED';
      profile.updated_at = setup.company_updated_at = '2026-10-24T11:00:00Z';
      return { feature_key: key, is_enabled: on, locked: false, locked_at: null } as never;
    }
    return structuredClone(path === '/v1/company-features' ? catalogue : path.endsWith('/setup-readiness') ? setup : profile) as never;
  });
});
async function open(name = 'Batches', action = 'Enable') {
  const user = userEvent.setup(); await user.click(await screen.findByRole('button', { name: 'Actions for ' + name }));
  await user.click(screen.getByRole('menuitem', { name: new RegExp('^' + action + ' ' + name) }));
  return user;
}
it('shows server labels, use locks and configuration edit/back context', async () => {
  await mount(); expect(await screen.findByText('Track batches')).toBeVisible();
  expect(screen.getByText('foreign_currency_posting')).toBeVisible();
  expect(screen.getByRole('link', { name: 'Back to companies' })).toHaveAttribute('href', '/companies/manage?q=Re');
  const edit = new URL(screen.getByRole('link', { name: 'Edit company settings' }).getAttribute('href')!, 'https://console.invalid');
  expect(edit.searchParams.get('returnTo')).toContain('/configuration?returnTo=');
});
it('reviews enable dependencies and requires a reason before sending one versioned command', async () => {
  await mount(); const user = await open(), dialog = within(screen.getByRole('dialog'));
  expect(dialog.getByText('Stock and inventory')).toBeVisible();
  await user.click(dialog.getByRole('button', { name: 'Enable feature' }));
  expect(dialog.getByRole('textbox', { name: 'Reason for change' })).toHaveFocus();
  expect(vi.mocked(companyCall).mock.calls.filter(call => call[2]?.method === 'POST')).toHaveLength(0);
  await user.type(dialog.getByRole('textbox', { name: 'Reason for change' }), ' Track lots '); await user.click(dialog.getByRole('button', { name: 'Enable feature' }));
  await screen.findByText(/Batches enabled/);
  const writes = vi.mocked(companyCall).mock.calls.filter(call => call[2]?.method === 'POST');
  expect(writes).toHaveLength(1); expect(writes[0][1]).toBe('/v1/companies/' + companyId + '/features/batch_tracking/enable');
  expect(writes[0][2]?.body).toEqual({ reason: 'Track lots', expected_updated_at: stamp });
  expect(await screen.findByRole('button', { name: 'Refresh configuration' })).toBeEnabled();
});
it('reviews and disables a reversible feature without erasing history', async () => {
  await mount(); const user = await open('Budgets', 'Disable'), dialog = within(screen.getByRole('dialog'));
  await user.type(dialog.getByRole('textbox', { name: 'Reason for change' }), 'No budget control'); await user.click(dialog.getByRole('button', { name: 'Disable feature' }));
  await screen.findByText(/Budgets disabled/); expect(vi.mocked(companyCall).mock.calls.some(call => call[1].endsWith('/budgets/disable'))).toBe(true);
});
it.each([['Foreign currency', 'Disable', /Permanently enabled/], ['GST e-invoicing', 'Enable', /Unavailable/]])('explains why %s cannot change', async (name, action, explanation) => {
  await mount(); await userEvent.click(await screen.findByRole('button', { name: 'Actions for ' + name }));
  expect(screen.getByRole('menuitem', { name: new RegExp('^' + action + ' ' + name) })).toHaveAttribute('aria-disabled', 'true');
  expect(within(screen.getByRole('menuitem', { name: new RegExp('^' + action + ' ' + name) })).getByText(explanation)).toBeVisible();
});
it('refuses disabling a prerequisite while dependents remain enabled', async () => {
  setup.features[0].state = setup.features[1].state = 'ENABLED'; await mount();
  await userEvent.click(await screen.findByRole('button', { name: 'Actions for Stock and inventory' }));
  expect(screen.getByRole('menuitem', { name: /^Disable Stock and inventory/ })).toHaveAttribute('aria-disabled', 'true');
  expect(screen.getByText(/Disable those features first/)).toBeVisible();
});
it.each(['suspended', 'closed'])('keeps %s company configuration read-only', async status => {
  setup.company_status = profile.status = status; await mount(); await screen.findByText('Track batches');
  expect(screen.queryByRole('link', { name: 'Edit company settings' })).not.toBeInTheDocument(); expect(screen.queryByRole('button', { name: /Actions for/ })).not.toBeInTheDocument();
});
it('lets readers inspect settings but does not offer write actions', async () => {
  await mount(['company.read']); await screen.findByText('Track batches');
  expect(screen.queryByRole('button', { name: /Actions for/ })).not.toBeInTheDocument(); expect(screen.getByText(/Read-only access/)).toBeVisible();
});
it('does not fetch configuration without scoped read permission', async () => {
  await mount([]); expect(screen.getByText(/Company read access is required/)).toBeVisible(); expect(companyCall).not.toHaveBeenCalled();
});
it('blocks changes for inconsistent feature state', async () => {
  setup.features[0].state = 'INCONSISTENT'; await mount(); expect(await screen.findByText(/Feature configuration needs repair/)).toBeVisible(); expect(screen.queryByRole('button', { name: /Actions for/ })).not.toBeInTheDocument();
});
it.each(['missing', 'duplicate', 'invalid'])('refuses a %s feature snapshot instead of offering incomplete changes', async problem => {
  if (problem === 'missing') setup.features.pop();
  if (problem === 'duplicate') setup.features.push(structuredClone(setup.features[0]));
  if (problem === 'invalid') setup.features[0].state = 'UNRECOGNIZED';
  await mount(); expect(await screen.findByText('The feature catalogue and configuration do not agree. Reload configuration.')).toBeVisible();
  expect(screen.queryByRole('button', { name: /Actions for/ })).not.toBeInTheDocument();
});
it('filters the fixed server catalogue and clears an empty result', async () => {
  await mount(); await screen.findByText('Track batches'); const user = userEvent.setup();
  await user.type(screen.getByRole('searchbox', { name: 'Search features' }), 'missing'); await screen.findByText('No matching features');
  await user.click(screen.getByRole('button', { name: 'Clear filters' })); expect(screen.getByText('Track batches')).toBeVisible();
});
it('guards reviewed changes before context switches and back navigation', async () => {
  await mount(); const user = await open(); expect(window.dispatchEvent(new Event(BEFORE_COMPANY_CHANGE, { cancelable: true }))).toBe(false);
  await user.keyboard('{Escape}'); expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  await user.click(screen.getByRole('link', { name: 'Back to companies' })); expect(goTo).not.toHaveBeenCalled();
});
it.each([409, 503])('retains and freezes a %s result until explicit reload', async status => {
  const answer = vi.mocked(companyCall).getMockImplementation()!;
  vi.mocked(companyCall).mockImplementation((service, path, request) => request?.method === 'POST' ? Promise.reject({ status, message: 'Review latest configuration.' }) : answer(service, path, request));
  await mount(); const user = await open(), dialog = within(screen.getByRole('dialog'));
  await user.type(dialog.getByRole('textbox', { name: 'Reason for change' }), 'Reviewed lots'); await user.click(dialog.getByRole('button', { name: 'Enable feature' }));
  await dialog.findByRole('button', { name: 'Reload and review' }); expect(dialog.getByRole('textbox', { name: 'Reason for change' })).toHaveValue('Reviewed lots');
  expect(dialog.getByRole('textbox', { name: 'Reason for change' })).toBeDisabled();
  await user.click(dialog.getByRole('button', { name: 'Reload and review' })); await screen.findByText('Track batches');
  await open(); expect(screen.getByRole('textbox', { name: 'Reason for change' })).toHaveValue('Reviewed lots');
  expect(vi.mocked(companyCall).mock.calls.filter(call => call[2]?.method === 'POST')).toHaveLength(1);
});
it('keeps field validation editable and focuses a rejected reason', async () => {
  const answer = vi.mocked(companyCall).getMockImplementation()!;
  vi.mocked(companyCall).mockImplementation((service, path, request) => request?.method === 'POST' ? Promise.reject({ status: 422, message: 'Invalid reason', fields: { reason: 'Choose a reason' } }) : answer(service, path, request));
  await mount(); const user = await open(); await user.type(screen.getByRole('textbox', { name: 'Reason for change' }), 'Reviewed'); await user.click(screen.getByRole('button', { name: 'Enable feature' }));
  await screen.findByText('Choose a reason'); expect(screen.getByRole('textbox', { name: 'Reason for change' })).toBeEnabled(); expect(screen.getByRole('textbox', { name: 'Reason for change' })).toHaveFocus();
});
it('rejects a configuration response for another company', async () => {
  setup.company_id = '01990000-0000-7000-8000-000000000099'; await mount(); expect(await screen.findByText(/configuration response could not be verified/)).toBeVisible(); expect(screen.queryByText('Track batches')).not.toBeInTheDocument();
});
it('clears an old enable reason when an unconfirmed change was applied and the next action is disable', async () => {
  const answer = vi.mocked(companyCall).getMockImplementation()!;
  vi.mocked(companyCall).mockImplementation(async (service, path, request) => {
    const value = await answer(service, path, request);
    if (request?.method === 'POST') throw { status: 503, message: 'Response lost' };
    return value;
  });
  await mount(); const user = await open(); await user.type(screen.getByRole('textbox', { name: 'Reason for change' }), 'Enable tracking');
  await user.click(screen.getByRole('button', { name: 'Enable feature' })); await user.click(await screen.findByRole('button', { name: 'Reload and review' }));
  await screen.findByText('Track batches'); await open('Batches', 'Disable'); expect(screen.getByRole('textbox', { name: 'Reason for change' })).toHaveValue('');
});
it('prevents duplicate submission and context changes while a feature action is pending', async () => {
  const answer = vi.mocked(companyCall).getMockImplementation()!; let finish!: (value: unknown) => void;
  vi.mocked(companyCall).mockImplementation((service, path, request) => request?.method === 'POST' ? new Promise(resolve => { finish = resolve; }) : answer(service, path, request));
  await mount(); const user = await open(); await user.type(screen.getByRole('textbox', { name: 'Reason for change' }), 'Track lots');
  await user.dblClick(screen.getByRole('button', { name: 'Enable feature' }));
  expect(vi.mocked(companyCall).mock.calls.filter(call => call[2]?.method === 'POST')).toHaveLength(1);
  expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled(); expect(window.dispatchEvent(new Event(BEFORE_COMPANY_CHANGE, { cancelable: true }))).toBe(false);
  setup.features[0].state = setup.features[1].state = 'ENABLED'; finish({ feature_key: 'batch_tracking', is_enabled: true });
  await screen.findByText(/Batches enabled/);
});
it('treats a mismatched successful response as unconfirmed instead of claiming a save', async () => {
  const answer = vi.mocked(companyCall).getMockImplementation()!;
  vi.mocked(companyCall).mockImplementation((service, path, request) => request?.method === 'POST' ? Promise.resolve({ feature_key: 'budgets', is_enabled: true }) : answer(service, path, request));
  await mount(); const user = await open(); await user.type(screen.getByRole('textbox', { name: 'Reason for change' }), 'Track lots'); await user.click(screen.getByRole('button', { name: 'Enable feature' }));
  await screen.findByText(/The result is unconfirmed/); expect(screen.queryByText(/Batches enabled/)).not.toBeInTheDocument();
});
it('refuses a torn profile/readiness snapshot and retries its read without a write', async () => {
  profile.updated_at = '2026-10-24T09:00:00Z'; await mount(); expect(await screen.findByText(/Configuration changed while loading/)).toBeVisible();
  profile.updated_at = stamp; await userEvent.click(screen.getByRole('button', { name: 'Reload configuration' })); await screen.findByText('Track batches');
  expect(vi.mocked(companyCall).mock.calls.filter(call => call[2]?.method === 'POST')).toHaveLength(0);
});
it.each([401, 403, 422, 503])('renders a %s load failure as a recoverable or permission error', async status => {
  vi.mocked(companyCall).mockRejectedValue({ status, message: 'Configuration unavailable' }); await mount(); expect(await screen.findByText('Configuration unavailable')).toBeVisible();
  expect(screen.queryByRole('button', { name: 'Reload configuration' }) !== null).toBe(![401, 403].includes(status));
});
it('offers sign-in with the current configuration return after session expiry', async () => {
  vi.mocked(companyCall).mockRejectedValue({ status: 401, message: 'Session expired' }); await mount();
  const link = await screen.findByRole('link', { name: 'Sign in again' });
  expect(new URL(link.getAttribute('href')!, 'https://console.invalid').searchParams.get('returnTo')).toContain('/configuration?returnTo=');
});

it('links the current company to native Accounting configuration with its scoped read grant', async () => {
  await mount(['company.read', 'accounting.party.read']);
  const link = await screen.findByRole('link', { name: 'Account, party and supplier configuration' });
  expect(new URL(link.getAttribute('href')!, 'https://console.invalid').searchParams.get('returnTo')).toBe('/companies/' + companyId + '/configuration?returnTo=%2Fcompanies%2Fmanage%3Fq%3DRe');
});
it('keeps the company configuration origin when opening product configuration', async () => {
  await mount(['company.read', 'product_configuration.read']);
  const link = await screen.findByRole('link', { name: 'Product configuration' });
  expect(new URL(link.getAttribute('href')!, 'https://console.invalid').searchParams.get('returnTo')).toBe('/companies/' + companyId + '/configuration?returnTo=%2Fcompanies%2Fmanage%3Fq%3DRe');
});
it('seats the feature search in the card’s filter bar so it shares the card gutter', async () => {
  await mount(); await screen.findByText('Track batches');
  const bar = screen.getByLabelText('Search features').closest('.janso-filter-bar');
  // Bare in the card it sat hard against the border while the heading above it was indented.
  expect(bar).not.toBeNull(); expect(bar!.parentElement).toHaveClass('janso-card');
});

it('presents business identity and readable regional defaults in separate summary groups', async () => {
  profile.legal_name = 'Retail Private Limited'; profile.country_code = 'IN'; profile.state_code = 'MH';
  await mount(); await screen.findByText('Track batches');
  expect(within(screen.getByRole('region', { name: 'Business identity' })).getByText('Retail Private Limited')).toBeVisible();
  expect(within(screen.getByRole('region', { name: 'Regional and financial defaults' })).getByText('GST (India)')).toBeVisible();
  expect(screen.queryByText('gst_in', { selector: 'dd' })).not.toBeInTheDocument();
});

it.each([['vat_gb', 'GB', 'VAT (United Kingdom)'], ['none', 'IN', 'No indirect tax registration']])('explains %s without India GST controls', async (tax, country, label) => {
  profile.default_tax_system = tax; profile.country_code = country;
  const answer = vi.mocked(companyCall).getMockImplementation()!;
  vi.mocked(companyCall).mockImplementation((service, path, request) => path.includes('/tax-registrations?') ? Promise.resolve({ items: [], page: { next_cursor: null } }) as never : answer(service, path, request));
  await mount();
  const taxSection = await screen.findByRole('region', { name: 'Tax registration and applicability' });
  expect(within(taxSection).getByText(label)).toBeVisible();
  expect(screen.queryByRole('button', { name: 'Add GST registration' })).not.toBeInTheDocument();
  expect(screen.queryByRole('link', { name: 'GST settings' })).not.toBeInTheDocument();
  expect(companyCall).not.toHaveBeenCalledWith('identity', expect.stringContaining('/gst-registration-setup'), expect.anything());
});

it('offers GST settings after editing and keeps configuration free of GST forms and reads', async () => {
  profile.country_code = 'IN';
  const answer = vi.mocked(companyCall).getMockImplementation()!;
  vi.mocked(companyCall).mockImplementation((service, path, request) => {
    if (path.endsWith('/gst-registration-setup')) return Promise.resolve({ country_code: 'IN', default_tax_system: 'gst_in', can_manage: true, regimes: { regular: 'Regular' }, states: [{ code: 'MH', name: 'Maharashtra' }], create_schema: { properties: {} } }) as never;
    if (path.endsWith('/gst-outward-profile-setup')) return Promise.resolve({ can_manage: true, create_schema: { properties: {} } }) as never;
    if (path.includes('/tax-registrations?') || path.includes('/gst-outward-profiles?')) return Promise.resolve({ items: [], page: { next_cursor: null } }) as never;
    return answer(service, path, request);
  });
  await mount(); await screen.findByRole('button', { name: 'Refresh configuration' });
  const edit = screen.getByRole('link', { name: 'Edit company settings' });
  const gst = screen.getByRole('link', { name: 'GST settings' });
  expect(edit.compareDocumentPosition(gst) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  const destination = new URL(gst.getAttribute('href')!, 'https://console.invalid');
  expect(destination.pathname).toBe('/companies/' + companyId + '/gst-settings');
  expect(destination.searchParams.get('returnTo')).toContain('/configuration?returnTo=');
  expect(screen.queryByRole('button', { name: 'Add GST registration' })).not.toBeInTheDocument();
  expect(screen.queryByRole('table', { name: 'Dated GST outward reporting profiles' })).not.toBeInTheDocument();
  expect(companyCall).not.toHaveBeenCalledWith('identity', expect.stringContaining('/gst-registration-setup'), expect.anything());
  expect(companyCall).not.toHaveBeenCalledWith('identity', expect.stringContaining('/tax-registrations?'), expect.anything());
});

it('allows a readable GST company to inspect GST settings without company update permission', async () => {
  profile.country_code = 'IN'; await mount(['company.read']);
  expect(await screen.findByRole('link', { name: 'GST settings' })).toBeVisible();
  expect(screen.queryByRole('link', { name: 'Edit company settings' })).not.toBeInTheDocument();
  expect(screen.queryByRole('table', { name: 'Company GST registrations' })).not.toBeInTheDocument();
});
