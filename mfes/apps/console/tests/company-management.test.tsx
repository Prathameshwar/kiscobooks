import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { DisplayConfigProvider, PermissionProvider } from '@janso/ui';
import { CompanyProfile } from '../app/components/CompanyProfile';
import { CompanyDirectory } from '../app/components/CompanyDirectory';
import { CompanyManagementPage } from '../app/components/CompanyManagementPage';
import ManageCompaniesPage from '../app/companies/manage/page';
import { companyCall } from '../app/lib/company-api';
import { companyPermission } from '../app/lib/company-permissions';
import { companyPatch, type CompanyField } from '../app/lib/company-form';
import { pageContext } from '../app/lib/page-context';
import { BEFORE_COMPANY_CHANGE } from '../app/lib/use-unsaved-changes';
import { goTo } from '../app/lib/navigate';
import { companyContextFor, sessionFor } from './helpers';

vi.mock('../app/lib/company-api', () => ({ companyCall: vi.fn(), companyFailure: (error: unknown) => error }));
vi.mock('../app/lib/page-context', () => ({ pageContext: vi.fn() }));
vi.mock('../app/lib/navigate', () => ({ goTo: vi.fn(), stepUpUrl: (id: string) => '/verify/' + id }));
vi.mock('../app/providers', () => ({ Providers: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/components/ConsoleShell', () => ({ ConsoleShell: ({ children }: { children: React.ReactNode }) => children }));

const ID = '01990000-0000-7000-8000-000000000001', OTHER = '01990000-0000-7000-8000-000000000002';
const profile = { id: ID, display_name: 'Acme', code: 'ACME', legal_name: 'Acme Limited', status: 'active',
  country_code: 'IN', state_code: 'MH', base_currency: 'INR', amount_precision: 2, first_posted_at: '2026-10-01T00:00:00Z',
  updated_at: '2026-10-01T12:00:00Z', custom_fields: {}, terms_and_conditions: 'Pay in thirty days.' };
function field(key: string, extra: Partial<CompanyField> = {}): CompanyField {
  return { key, label: key, group: 'identity', order: 1, source: 'native', required: true, hideable: false,
    renameable: true, requires_feature: null, is_visible: true, writable: true, data_type: 'string', ...extra };
}
const fields = [field('display_name'), field('legal_name'), field('amount_precision', { writable: false, data_type: 'integer' }),
  field('terms_and_conditions', { required: false, group: 'branding' })];
function wrap(node: React.ReactNode) { return render(<PermissionProvider permissions={['company.read', 'company.update']}><DisplayConfigProvider config={{}}>{node}</DisplayConfigProvider></PermissionProvider>); }
async function tenant(permissions = ['company.read', 'company.update', 'company.create']) {
  const session = await sessionFor({ permissions });
  session.grants = [{ scope_type: 'tenant', scope_id: null, valid_from: '2020-01-01', valid_to: null, permissions }];
  return session;
}
beforeEach(async () => {
  vi.clearAllMocks();
  vi.mocked(pageContext).mockResolvedValue({ session: await tenant(), context: companyContextFor() });
  vi.mocked(companyCall).mockImplementation(async (_service, path, request) => {
    if (path.endsWith('/setup')) return { company_id: ID, status: 'RETRY_WAIT', updated_at: new Date().toISOString(), steps: [{ key: 'catalog', status: 'RETRY_WAIT' }] } as never;
    if (request?.method === 'PATCH') return { ...profile, ...(request.body as object) } as never;
    if (path.includes('/field-set')) return { fields } as never;
    if (path === '/v1/reference/countries') return [{ code: 'IN', name: 'India', jurisdiction_supported: true, tax_systems: ['gst_in'] }] as never;
    if (path === '/v1/reference/currencies') return [{ code: 'INR', name: 'Indian rupee' }] as never;
    if (path.endsWith('/states')) return [{ code: 'MH', name: 'Maharashtra' }] as never;
    if (path === '/v1/company-classifications') return { business_categories: [], business_roles: [], store_formats: [] } as never;
    if (path.startsWith('/v1/companies?')) return { items: [profile], page: { has_more: false, next_cursor: null } } as never;
    return profile as never;
  });
});

it('uses active scoped grants, never account classification or another company authority', async () => {
  const session = await tenant(); session.role = 'platform admin'; session.grants = [];
  expect(companyPermission(session, 'company.read', ID)).toBe(false);
  session.grants = [{ scope_type: 'company', scope_id: ID, permissions: ['company.read', 'company.update', 'company.create'], valid_from: '2020-01-01', valid_to: null }];
  expect(companyPermission(session, 'company.read', ID)).toBe(true);
  expect(companyPermission(session, 'company.update', OTHER)).toBe(false);
  expect(companyPermission(session, 'company.create')).toBe(false);
  session.grants[0].valid_to = '2020-02-01'; expect(companyPermission(session, 'company.read', ID)).toBe(false);
});

it('guards direct view/edit pages and invalid identifiers before fetching business data', async () => {
  const context = await pageContext(); context.session.grants = [];
  wrap(await CompanyManagementPage({ companyId: ID, editing: true }));
  expect(screen.getByText(/Editing needs company.read/)).toBeVisible(); expect(companyCall).not.toHaveBeenCalled();
});
it('does not render a management directory for an unpermitted direct visit', async () => {
  const context = await pageContext(); context.session.grants = [];
  wrap(await ManageCompaniesPage({}));
  expect(screen.getByText(/Company management needs/)).toBeVisible(); expect(companyCall).not.toHaveBeenCalled();
});
it('rejects malformed route identifiers and another company scope without reads', async () => {
  const context = await pageContext();
  const first = wrap(await CompanyManagementPage({ companyId: 'invalid' }));
  expect(screen.getByText(/Company not found/)).toBeVisible(); first.unmount();
  context.session.grants = [{ scope_type: 'company', scope_id: OTHER, valid_from: '2020-01-01', valid_to: null, permissions: ['company.read', 'company.update'] }];
  wrap(await CompanyManagementPage({ companyId: ID }));
  expect(screen.getByText('Company read access is needed for this company.')).toBeVisible();
  expect(companyCall).not.toHaveBeenCalled();
});
it('hides edit controls for readers and refuses a direct edit visit', async () => {
  const context = await pageContext(); context.session = await tenant(['company.read']);
  const first = wrap(await CompanyManagementPage({ companyId: ID }));
  await screen.findByRole('heading', { name: 'Acme' });
  expect(screen.queryByRole('link', { name: 'Edit company' })).not.toBeInTheDocument(); first.unmount();
  wrap(await CompanyManagementPage({ companyId: ID, editing: true }));
  expect(screen.getByText(/Editing needs company.read/)).toBeVisible();
});
it('renders a permitted view page with a separate edit destination and navigation', async () => {
  wrap(await CompanyManagementPage({ companyId: ID }));
  expect(await screen.findByRole('heading', { name: 'Acme' })).toBeVisible();
  expect(screen.getByRole('link', { name: 'Edit company' })).toHaveAttribute('href', '/companies/' + ID + '/edit?returnTo=' + encodeURIComponent('/companies/' + ID + '?returnTo=%2Fcompanies%2Fmanage'));
  expect(screen.getByRole('link', { name: 'Back to companies' })).toHaveAttribute('href', '/companies/manage');
  expect(screen.getByText('Pay in thirty days.')).toBeVisible();
});
it('shows loading, read-only settings and required validation with focus', async () => {
  const user = userEvent.setup(); wrap(<CompanyProfile companyId={ID} editing canEdit />);
  expect(screen.getByRole('status', { name: 'Loading company' })).toBeVisible();
  const name = await screen.findByRole('textbox', { name: 'Display name' });
  expect(screen.getByRole('textbox', { name: 'Amount precision' })).toBeDisabled();
  await user.clear(name); await user.click(screen.getByRole('button', { name: 'Save company' }));
  expect(await screen.findByText('Display name is required.')).toBeVisible();
  await waitFor(() => expect(name).toHaveFocus());
  expect(vi.mocked(companyCall).mock.calls.some(call => call[2]?.method === 'PATCH')).toBe(false);
});

it('uses the shared editor layout with named sections, company context and an attached action footer', async () => {
  const { container } = wrap(<CompanyProfile companyId={ID} editing canEdit />);
  const editor = await screen.findByRole('form', { name: 'Company editor' });
  const layout = editor.closest('.janso-grid--split');
  expect(layout).not.toBeNull();
  expect(within(editor).getByRole('heading', { level: 2, name: 'Business identity' })).toBeVisible();
  expect(within(editor).getByRole('heading', { level: 2, name: 'Branding and document text' })).toBeVisible();
  const context = within(layout as HTMLElement).getByRole('complementary', { name: 'Before you save' });
  expect(context).toHaveTextContent('Acme');
  expect(context).toHaveTextContent('ACME');
  expect(context).toHaveTextContent(/locked after posting/i);
  expect(context.querySelector('.janso-setup__review')).toBeNull();
  const save = within(editor).getByRole('button', { name: 'Save company' });
  const footer = save.closest('.janso-card__footer');
  expect(footer).not.toBeNull();
  expect(within(footer as HTMLElement).getByRole('link', { name: 'Cancel' })).toHaveAttribute('href', '/companies/' + ID);
  expect(container.querySelectorAll('form')).toHaveLength(1);
});

it('connects document text hints and validation errors to its textarea', async () => {
  const original = vi.mocked(companyCall).getMockImplementation()!;
  vi.mocked(companyCall).mockImplementation((service, path, request) => path.includes('/field-set')
    ? Promise.resolve({ fields: fields.map(item => item.key === 'terms_and_conditions'
      ? { ...item, data_type: 'long_text', help_text: 'Printed on company documents.', validation: { max_length: 40 } } : item) } as never)
    : request?.method === 'PATCH' ? Promise.reject({ status: 422, message: 'Check document text.', fields: { terms_and_conditions: 'Document text was refused.' } }) : original(service, path, request));
  const user = userEvent.setup(); wrap(<CompanyProfile companyId={ID} editing canEdit />);
  const text = await screen.findByRole('textbox', { name: 'Terms and conditions' });
  expect(text.tagName).toBe('TEXTAREA');
  expect(text).toHaveAccessibleDescription('Printed on company documents.');
  expect(text).toHaveAttribute('maxlength', '40');
  await user.type(text, ' Updated');
  await user.click(screen.getByRole('button', { name: 'Save company' }));
  expect(await screen.findByText('Document text was refused.')).toBeVisible();
  expect(text).toHaveAccessibleDescription('Document text was refused. Printed on company documents.');
  await waitFor(() => expect(text).toHaveFocus());
});

it('validates field patterns, minimum length and choices before sending a company patch', () => {
  const descriptors = [
    field('code', { validation: { pattern: '^[A-Z0-9-]+$', min_length: 2 } }),
    field('entity_type', { choices: [{ value: 'llp', label: 'LLP' }] }),
  ];
  const invalid = companyPatch(descriptors, { code: 'a', entity_type: 'unknown' }, { code: 'ACME', entity_type: 'llp' });
  expect(invalid.errors.code).toBeTruthy();
  expect(invalid.errors.entity_type).toBe('Choose an available option.');
  expect(invalid.patch).toEqual({});
});
it('formats dates and exact money even when presentation fields are omitted', async () => {
  const original = vi.mocked(companyCall).getMockImplementation()!;
  vi.mocked(companyCall).mockImplementation((service, path, request) => path === '/v1/companies/' + ID
    ? Promise.resolve({ ...profile, books_begin_date: '2026-04-01', cash_receipt_limit: '1234567.8900' } as never)
    : path.includes('/field-set') ? Promise.resolve({ fields: [...fields, field('books_begin_date', { data_type: 'date' }), field('cash_receipt_limit', { data_type: 'decimal' })] } as never)
    : original(service, path, request));
  wrap(<CompanyProfile companyId={ID} />);
  expect(await screen.findByText('01 Apr 2026')).toBeVisible();
  expect(screen.getByText(/12,34,567.89/)).toBeVisible();
});
it('saves only changed writable values with a concurrency precondition and pending state', async () => {
  const user = userEvent.setup(); let finish!: (value: unknown) => void;
  const original = vi.mocked(companyCall).getMockImplementation()!;
  vi.mocked(companyCall).mockImplementation((service, path, request) => request?.method === 'PATCH'
    ? new Promise(resolve => { finish = resolve; }) : original(service, path, request));
  wrap(<CompanyProfile companyId={ID} editing canEdit />);
  await user.type(await screen.findByRole('textbox', { name: 'Display name' }), ' Updated');
  await user.click(screen.getByRole('button', { name: 'Save company' }));
  expect(screen.getByRole('button', { name: 'Saving company…' })).toBeDisabled();
  expect(companyCall).toHaveBeenCalledWith('identity', '/v1/companies/' + ID, { method: 'PATCH', body: {
    display_name: 'Acme Updated', expected_updated_at: profile.updated_at,
  } });
  finish({ ...profile, display_name: 'Acme Updated' });
  expect(await screen.findByText('Company saved.')).toBeVisible();
  expect(screen.getByRole('button', { name: 'Save company' })).toBeDisabled();
});
it('preserves the company server field message and focuses its control', async () => {
  const original = vi.mocked(companyCall).getMockImplementation()!;
  vi.mocked(companyCall).mockImplementation(async (...args) => args[2]?.method === 'PATCH'
    ? Promise.reject({ status: 422, message: 'Check the company name.', fields: { display_name: 'Choose a different display name.' } }) : original(...args));
  wrap(<CompanyProfile companyId={ID} editing canEdit />);
  const name = await screen.findByRole('textbox', { name: 'Display name' }); await userEvent.type(name, ' Updated');
  await userEvent.click(screen.getByRole('button', { name: 'Save company' }));
  expect(await screen.findByText('Choose a different display name.')).toBeVisible(); await waitFor(() => expect(name).toHaveFocus());
});
it('preserves edits on conflict and confirms discarding on navigation', async () => {
  const user = userEvent.setup(), original = vi.mocked(companyCall).getMockImplementation()!;
  vi.mocked(companyCall).mockImplementation((service, path, request) => request?.method === 'PATCH'
    ? Promise.reject({ status: 409, message: 'This company changed. Reload before saving.' }) : original(service, path, request));
  wrap(<CompanyProfile companyId={ID} editing canEdit />);
  const name = await screen.findByRole('textbox', { name: 'Display name' }); await user.type(name, ' Draft');
  expect(window.dispatchEvent(new Event(BEFORE_COMPANY_CHANGE, { cancelable: true }))).toBe(false);
  await user.click(screen.getByRole('button', { name: 'Save company' }));
  expect(await screen.findByText('This company changed. Reload before saving.')).toBeVisible(); expect(name).toHaveValue('Acme Draft');
  await user.click(screen.getByRole('link', { name: 'Back to company details' }));
  expect(screen.getByRole('dialog')).toBeVisible();
  await user.click(screen.getByRole('button', { name: 'Discard changes' })); expect(goTo).toHaveBeenCalledWith('/companies/' + ID);
});
it('keeps the draft when reference reads fail and retries choices without discarding it', async () => {
  const user = userEvent.setup(), original = vi.mocked(companyCall).getMockImplementation()!;
  let unavailable = true;
  vi.mocked(companyCall).mockImplementation((service, path, request) => path === '/v1/reference/currencies' && unavailable
    ? Promise.reject({ status: 503, message: 'Unavailable' }) : original(service, path, request));
  wrap(<CompanyProfile companyId={ID} editing canEdit />);
  const name = await screen.findByRole('textbox', { name: 'Display name' }); await user.type(name, ' Draft');
  expect(screen.getByRole('button', { name: 'Save company' })).toBeDisabled();
  unavailable = false; await user.click(screen.getByRole('button', { name: 'Reload choices' }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Save company' })).toBeEnabled());
  expect(name).toHaveValue('Acme Draft');
});
it('renders hidden and omitted fields safely and locks all controls for inactive companies', async () => {
  const original = vi.mocked(companyCall).getMockImplementation()!;
  vi.mocked(companyCall).mockImplementation((service, path, request) => path === '/v1/companies/' + ID
    ? Promise.resolve({ ...profile, status: 'closed' } as never) : path.includes('/field-set')
      ? Promise.resolve({ fields: [...fields.map(item => item.key === 'legal_name' ? { ...item, is_visible: false } : item), field('trade_name')] } as never)
      : original(service, path, request));
  wrap(<CompanyProfile companyId={ID} editing canEdit />);
  expect(await screen.findByRole('textbox', { name: 'Display name' })).toBeDisabled();
  expect(screen.queryByRole('textbox', { name: 'Legal name' })).not.toBeInTheDocument();
  expect(screen.queryByRole('textbox', { name: 'Trade name' })).not.toBeInTheDocument();
  expect(screen.getByText(/This company is read-only/)).toBeVisible();
});
it.each([403, 404, 503])('renders a clear failed company load (%s)', async status => {
  vi.mocked(companyCall).mockRejectedValue({ status, message: 'Company request refused.' });
  wrap(<CompanyProfile companyId={ID} />);
  expect(await screen.findByText(status === 404 ? /This company was not found/ : 'Company request refused.')).toBeVisible();
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
});
it('offers verification when a company requires fresh authentication', async () => {
  vi.mocked(companyCall).mockRejectedValue({ status: 403, code: 'step_up_required', message: 'Verify sign-in.' });
  wrap(<CompanyProfile companyId={ID} />);
  expect(await screen.findByRole('link', { name: 'Verify sign-in' })).toHaveAttribute('href', '/verify/' + ID);
});
it('paginates and filters the management list through scoped API reads', async () => {
  const user = userEvent.setup(), original = vi.mocked(companyCall).getMockImplementation()!;
  vi.mocked(companyCall).mockImplementation((service, path, request) => path.startsWith('/v1/companies?')
    ? Promise.resolve({ items: [profile], page: { has_more: true, next_cursor: 'next-page' } } as never) : original(service, path, request));
  wrap(<CompanyDirectory session={await tenant()} />);
  expect(await screen.findByRole('link', { name: 'Acme' })).toHaveAttribute('href', '/companies/' + ID + '?returnTo=%2Fcompanies%2Fmanage');
  expect(vi.mocked(companyCall).mock.calls[0][1]).toContain('include_unlisted=true');
  await user.click(screen.getByRole('button', { name: /Next page/ }));
  await waitFor(() => expect(vi.mocked(companyCall).mock.calls.some(call => call[1].includes('cursor=next-page'))).toBe(true));
  await user.selectOptions(screen.getByRole('combobox', { name: 'Status' }), 'closed');
  await waitFor(() => expect(vi.mocked(companyCall).mock.calls.at(-1)?.[1]).toContain('status=closed'));
  expect(vi.mocked(companyCall).mock.calls.at(-1)?.[1]).not.toContain('cursor=');
});
it('lets a create-only actor create without fetching a management list', async () => {
  wrap(<CompanyDirectory session={await tenant(['company.create'])} />);
  expect(screen.getByRole('link', { name: 'Create company' })).toBeVisible();
  expect(companyCall).not.toHaveBeenCalled();
});
it('shows an API list failure with retry and then an empty result', async () => {
  const user = userEvent.setup(); vi.mocked(companyCall).mockRejectedValueOnce({ status: 503, message: 'Directory unavailable.' });
  wrap(<CompanyDirectory session={await tenant()} />);
  expect(await screen.findByText('Directory unavailable.')).toBeVisible();
  vi.mocked(companyCall).mockResolvedValue({ items: [], page: { has_more: false, next_cursor: null } } as never);
  await user.click(screen.getByRole('button', { name: /Try again/ }));
  expect(await screen.findByText('No companies found')).toBeVisible();
});
it('never patches hidden, locked or omitted fields and keeps money exact', () => {
  const previous = { display_name: 'Old', amount_precision: 2, cash_receipt_limit: '1.0000' };
  const result = companyPatch([...fields, field('cash_receipt_limit', { data_type: 'decimal' }), field('secret', { is_visible: false })],
    { ...previous, display_name: 'New', amount_precision: 4, cash_receipt_limit: '999999999999999.9999', secret: 'ignore' }, previous);
  expect(result).toEqual({ patch: { display_name: 'New', cash_receipt_limit: '999999999999999.9999' }, errors: {} });
});

it('shows background setup progress on the company landing page', async () => {
  wrap(<CompanyProfile companyId={ID} canEdit />);
  expect(await screen.findByText('Automatic company setup')).toBeVisible();
  expect(await screen.findByText('Company saved. Setup is waiting and will retry automatically.')).toBeVisible();
});
