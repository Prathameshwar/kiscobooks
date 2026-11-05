/**
 * The company creation wizard.
 *
 * What is asserted: that the jurisdiction's conventions arrive as suggestions the operator can
 * see and change, that a step cannot be left with a required field empty, that the preview
 * formats from the *draft* rather than from the open company, and — above all — that the finish
 * is a retryable sequence which never creates a second company on a retry.
 */
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ThemeProvider } from '@janso/ui';
import { CompanyWizard } from '../app/components/CompanyWizard';
import { companyCall, openCompany } from '../app/lib/company-api';
import { companyPricingDefaults } from '../app/lib/company-pricing-defaults';
import { goTo } from '../app/lib/navigate';
import type { Session } from '../app/session';
import { BEFORE_COMPANY_CHANGE } from '../app/lib/use-unsaved-changes';

vi.mock('../app/lib/company-api', () => ({
  companyCall: vi.fn(),
  openCompany: vi.fn(),
  companyFailure: (value: unknown) =>
    value && typeof value === 'object' && 'status' in value ? value : { status: 503, message: 'The company service is unavailable. Try again.' },
}));
vi.mock('../app/lib/navigate', () => ({ goTo: vi.fn() }));
vi.mock('../app/lib/company-pricing-defaults', () => ({ companyPricingDefaults: vi.fn(async () => undefined) }));

/*
 * Six steps of typing and clicking per path, and the whole file runs again under coverage
 * instrumentation. The default 5s is not a meaningful signal here — a slow machine is not a
 * broken wizard — so the budget is stated rather than inherited.
 */
vi.setConfig({ testTimeout: 20000 });

it('allows its own final company switch after setup has saved all changes', async () => {
  const user = userEvent.setup({ delay: null });
  mount();
  await screen.findByRole('textbox', { name: /Legal name/ });
  await reachReview(user);
  expect(window.dispatchEvent(new Event(BEFORE_COMPANY_CHANGE, { cancelable: true }))).toBe(false);
  vi.mocked(openCompany).mockImplementation(async () => window.dispatchEvent(new Event(BEFORE_COMPANY_CHANGE, { cancelable: true }))
    ? null : { status: 409, message: 'Save or discard unsaved changes before changing company or financial year.' });
  await user.click(screen.getByRole('button', { name: 'Create this company' }));
  await waitFor(() => expect(openCompany).toHaveBeenCalled());
  await expect(vi.mocked(openCompany).mock.results[0].value).resolves.toBeNull();
});

it('retries only the final switch after another editor releases its unsaved-change guard', async () => {
  const user = userEvent.setup({ delay: null });
  mount();
  await screen.findByRole('textbox', { name: /Legal name/ });
  await reachReview(user);
  const otherEditor = (event: Event) => event.preventDefault();
  window.addEventListener(BEFORE_COMPANY_CHANGE, otherEditor);
  vi.mocked(openCompany).mockImplementation(async () => window.dispatchEvent(new Event(BEFORE_COMPANY_CHANGE, { cancelable: true }))
    ? null : { status: 409, message: 'Another editor has unsaved changes.' });
  try {
    await user.click(screen.getByRole('button', { name: 'Create this company' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Retry the remaining steps' })).toBeEnabled());
    expect(screen.getAllByText('Another editor has unsaved changes.').length).toBeGreaterThan(0);
  } finally { window.removeEventListener(BEFORE_COMPANY_CHANGE, otherEditor); }
  await user.click(screen.getByRole('button', { name: 'Retry the remaining steps' }));
  await waitFor(() => expect(openCompany).toHaveBeenCalledTimes(2));
  await expect(vi.mocked(openCompany).mock.results[1].value).resolves.toBeNull();
  expect(vi.mocked(companyCall).mock.calls.filter(([, path, options]) => path === '/v1/companies' && options?.method === 'POST')).toHaveLength(1);
});

const COMPANY = '01990000-0000-7000-8000-000000000001';
const YEAR = '01990000-0000-7000-8000-00000000000a';
const PERIOD = '01990000-0000-7000-8000-00000000000b';

/** The neutral set every country's suggestions start from, as the endpoint sends it. */
const NEUTRAL = {
  fiscal_year_start_month: 1,
  fiscal_year_start_day: 1,
  timezone: 'UTC',
  locale: 'en',
  date_format: 'dd MMM yyyy',
  datetime_format: 'dd MMM yyyy HH:mm',
  digit_grouping: 'western',
  decimal_separator: '.',
  thousands_separator: ',',
  negative_format: 'minus',
  currency_symbol_position: 'prefix',
  amount_precision: 2,
  quantity_precision: 3,
  rounding_mode: 'half_up',
  tax_treatment_default: 'exclusive',
  default_payment_terms_days: 30,
};
const COUNTRIES = [
  {
    code: 'IN', name: 'India', default_currency_code: 'INR', subdivision_label: 'State', jurisdiction_supported: true, tax_systems: ['gst_in'],
    tax_registration_options: [{ tax_system: 'gst_in', number_label: 'GSTIN', jurisdiction_scope: 'state', regimes: [{ value: 'regular', label: 'Regular taxpayer' }, { value: 'composition', label: 'Composition scheme' }] }],
    // What the jurisdiction profile suggests, pre-selected on the capability step.
    default_features: ['inventory', 'credit_limits', 'e_waybill'],
    setup_defaults: { ...NEUTRAL, fiscal_year_start_month: 4, timezone: 'Asia/Kolkata', date_format: 'dd-MM-yyyy', datetime_format: 'dd-MM-yyyy HH:mm', digit_grouping: 'indian' },
  },
  {
    code: 'GB', name: 'United Kingdom', default_currency_code: 'GBP', subdivision_label: 'Country', jurisdiction_supported: true, tax_systems: ['vat_gb'],
    tax_registration_options: [{ tax_system: 'vat_gb', number_label: 'VAT registration number', jurisdiction_scope: 'country', regimes: [{ value: 'standard', label: 'Normal accrual VAT' }, { value: 'cash_accounting', label: 'Cash accounting' }] }],
    default_features: ['inventory', 'credit_limits'],
    setup_defaults: { ...NEUTRAL, fiscal_year_start_month: 4, fiscal_year_start_day: 6, timezone: 'Europe/London', date_format: 'dd/MM/yyyy', datetime_format: 'dd/MM/yyyy HH:mm', tax_treatment_default: 'inclusive' },
  },
  { code: 'ZZ', name: 'Nowhere', default_currency_code: 'USD', subdivision_label: 'Region', jurisdiction_supported: false, tax_systems: [], default_features: [], setup_defaults: NEUTRAL },
];
/** The capability catalogue, as `GET /v1/company-features` carries it. */
const FEATURE_CATALOGUE = {
  items: [
    { key: 'inventory', label: 'Stock and inventory', description: 'Track item quantities, and value them on every movement.', requires: [], tax_systems: [], locks: true },
    { key: 'multi_godown', label: 'Multiple warehouses', description: 'Hold and move stock across more than one location.', requires: ['inventory'], tax_systems: [], locks: true },
    { key: 'batch_tracking', label: 'Batches', description: 'Record a batch on every movement of a tracked item.', requires: ['inventory'], tax_systems: [], locks: true },
    { key: 'expiry_tracking', label: 'Expiry dates', description: 'Record and report expiry against each batch.', requires: ['batch_tracking'], tax_systems: [], locks: true },
    { key: 'budgets', label: 'Budgets', description: 'Set budgets and report against them.', requires: [], tax_systems: [], locks: false },
    { key: 'credit_limits', label: 'Credit limits', description: 'Hold a credit limit against each customer.', requires: [], tax_systems: [], locks: false },
    { key: 'e_invoicing', label: 'GST e-invoicing', description: 'Register invoices with the IRP and carry the IRN.', requires: [], tax_systems: ['gst_in'], locks: false },
    { key: 'e_waybill', label: 'E-way bills', description: 'Generate e-way bills for goods movements.', requires: ['inventory'], tax_systems: ['gst_in'], locks: false },
  ],
};
const CURRENCIES = [
  { code: 'INR', name: 'Indian Rupee', symbol: '₹', minor_unit: 2 },
  { code: 'GBP', name: 'Pound Sterling', symbol: '£', minor_unit: 2 },
];
const STATES = [
  { code: 'MH', name: 'Maharashtra', country_code: 'IN' },
  { code: 'KA', name: 'Karnataka', country_code: 'IN' },
];
const GB_STATES = [{ code: 'ENG', name: 'England', country_code: 'GB' }];

function session(withFeatures = true): Session {
  const permissions = ['company.create', 'company.read', ...(withFeatures ? ['company.update'] : [])];
  return {
    user: { name: 'Admin', secondary: 'Tenant', theme: null, defaultCompanyId: null },
    organisation: { name: 'Tenant', code: 'TENANT' },
    company: { name: 'Select a company' },
    companySource: 'none',
    stepUpCompanyId: null,
    companyScopes: [],
    role: 'tenant admin',
    permissions,
    grants: [{ scope_type: 'tenant', scope_id: null, valid_from: '2020-01-01', valid_to: null, permissions }],
    display: { timezone: 'Asia/Kolkata' },
  };
}

/** Routes every call the wizard makes, so the order of its requests is not baked into a queue. */
function answer(overrides: Record<string, unknown> = {}) {
  const enabled = new Set<string>();
  vi.mocked(companyCall).mockImplementation(async (_service, path, request = {}) => {
    const method = request.method ?? 'GET';
    if (path === '/v1/reference/countries') return COUNTRIES as never;
    if (path === '/v1/reference/currencies') return CURRENCIES as never;
    if (path === '/v1/company-features') return FEATURE_CATALOGUE as never;
    if (path === '/v1/entities/identity.company/field-set') return (overrides.metadata ?? { fields: [] }) as never;
    if (path.endsWith('/states')) return (path.includes('/GB/') ? GB_STATES : STATES) as never;
    if (path === '/v1/companies' && method === 'POST') return (overrides.create ?? { id: COMPANY }) as never;
    if (path === `/v1/companies/${COMPANY}/setup`) return { company_id: COMPANY, status: 'COMPLETE', steps: [{ key: 'opening', status: 'AWAITING_OPENING' }] } as never;
    if (path.includes('/features/')) { enabled.add(path.split('/features/')[1].split('/')[0]); return {} as never; }
    if (path.includes('financial-setup/initialize')) return {} as never;
    if (path.includes('accounting-setup/initialize')) return {} as never;
    if (path.endsWith('/voucher-type-defaults/bootstrap')) return {
      company_id: COMPANY, status: 'READY', created_count: enabled.has('inventory') ? 38 : 20,
      preserved_count: 0, review_count: 0,
      features: [...enabled].filter(key => ['inventory', 'bom_definitions', 'approval_workflow', 'multi_currency'].includes(key)).sort(),
    } as never;
    if (path.endsWith('/unit-defaults/bootstrap')) return { company_id: COMPANY, status: 'READY', inventory_enabled: enabled.has('inventory'), notices: [] } as never;
    if (path.endsWith('/tax-defaults/bootstrap')) return { company_id: COMPANY, status: 'READY', notices: [] } as never;
    if (path.endsWith('/bootstrap')) return { id: COMPANY } as never;
    if (path.endsWith('/item-groups?code=DEFAULT&limit=1')) return { items: [overrides.defaultGroup ?? { id: COMPANY, code: 'DEFAULT', name: 'Default', allowed_kind: 'BOTH', is_active: true }] } as never;
    if (path.endsWith('/product-types?code=DEFAULT&limit=1')) return { items: [overrides.defaultType ?? { id: COMPANY, code: 'DEFAULT', name: 'Default', kind: 'BOTH', is_active: true }] } as never;
    if (path.includes('/revisions?published=true&limit=1')) return { items: [{ id: YEAR, product_type_id: COMPANY, kind: 'BOTH', published_at: '2026-10-30T00:00:00Z' }] } as never;
    if (path.includes('fiscal-years/generate')) return { id: YEAR } as never;
    if (path.includes('fiscal-periods')) return (overrides.periods ?? { items: [{ id: PERIOD, sequence: 1, start_date: '1900-01-01', end_date: '9998-12-31', status: 'FUTURE', row_version: 1 }] }) as never;
    if (path.includes('/transition')) return {} as never;
    throw new Error('unexpected call ' + path);
  });
}

async function fillBusiness(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByRole('textbox', { name: /Legal name/ }), 'Acme Manufacturing Private Limited');
  await user.click(screen.getByRole('button', { name: 'Next' }));
}

async function fillLocation(user: ReturnType<typeof userEvent.setup>) {
  await user.selectOptions(screen.getByRole('combobox', { name: 'Country' }), 'IN');
  await waitFor(() => expect(screen.getByRole('combobox', { name: 'State' })).toBeEnabled());
  await user.selectOptions(screen.getByRole('combobox', { name: 'State' }), 'MH');
  await user.click(screen.getByRole('switch', { name: 'Add registration later' }));
  await user.click(screen.getByRole('button', { name: 'Next' }));
}

async function reachReview(user: ReturnType<typeof userEvent.setup>) {
  await fillBusiness(user);
  await fillLocation(user);
  await user.click(screen.getByRole('button', { name: 'Next' })); // money and calendar
  await user.click(screen.getByRole('button', { name: 'Next' })); // what you track
  await user.click(screen.getByRole('button', { name: 'Next' })); // presentation
}

/** Mirrors the page, which mounts the wizard inside the console's own providers. */
function mount(canBootstrapBooks = true, withFeatures = true, organisation: Record<string, unknown> = {}, extraPermissions: string[] = []) {
  const current = session(withFeatures);
  Object.assign(current.organisation, organisation);
  current.permissions.push(...extraPermissions);
  return render(
    <ThemeProvider initial="light">
      <CompanyWizard session={current} canBootstrapBooks={canBootstrapBooks} />
    </ThemeProvider>,
  );
}

beforeEach(() => {
  answer();
  vi.mocked(openCompany).mockResolvedValue(null);
});
afterEach(() => vi.clearAllMocks());

it('opens on the first step with the whole route visible', async () => {
  mount();
  await waitFor(() => expect(screen.getByRole('textbox', { name: /Legal name/ })).toBeInTheDocument());

  expect(screen.getByRole('heading', { level: 1, name: 'Business' })).toBeInTheDocument();
  expect(screen.getByText('Step 1 of 6')).toBeInTheDocument();
  const progress = screen.getByRole('navigation', { name: 'Setup progress' });
  expect(within(progress).getByRole('button', { name: /Review and create/ })).toBeDisabled();
});

it('starts with the tenant location and submits the user-selected replacement state', async () => {
  const user = userEvent.setup({ delay: null });
  mount(true, true, { defaultCountryCode: 'IN', defaultStateCode: 'MH' });
  await screen.findByRole('textbox', { name: /Legal name/ });
  await fillBusiness(user);
  expect(screen.getByRole('combobox', { name: 'Country' })).toHaveValue('IN');
  await waitFor(() => expect(screen.getByRole('combobox', { name: 'State' })).toHaveValue('MH'));
  expect(screen.getByRole('switch', { name: 'Add registration later' })).not.toBeChecked();
  await user.click(screen.getByRole('switch', { name: 'Add registration later' }));
  await user.selectOptions(screen.getByRole('combobox', { name: 'State' }), 'KA');
  expect(screen.getByRole('switch', { name: 'Add registration later' })).toBeChecked();
  await user.click(screen.getByRole('button', { name: 'Next' }));
  await user.click(screen.getByRole('button', { name: 'Next' }));
  await user.click(screen.getByRole('button', { name: 'Next' }));
  await user.click(screen.getByRole('button', { name: 'Next' }));
  await user.click(screen.getByRole('button', { name: 'Create this company' }));
  await waitFor(() => expect(companyCall).toHaveBeenCalledWith('identity', '/v1/companies', expect.objectContaining({
    method: 'POST', body: expect.objectContaining({ country_code: 'IN', state_code: 'KA' }),
  })));
});

it('preserves the selected state when the current country is selected again', async () => {
  const user = userEvent.setup({ delay: null });
  mount(true, true, { defaultCountryCode: 'IN', defaultStateCode: 'MH' });
  await screen.findByRole('textbox', { name: /Legal name/ });
  await fillBusiness(user);
  await waitFor(() => expect(screen.getByRole('combobox', { name: 'State' })).toHaveValue('MH'));
  await user.selectOptions(screen.getByRole('combobox', { name: 'State' }), 'KA');
  fireEvent.change(screen.getByRole('combobox', { name: 'Country' }), { target: { value: 'IN' } });
  expect(screen.getByRole('combobox', { name: 'State' })).toBeEnabled();
  expect(screen.getByRole('combobox', { name: 'State' })).toHaveValue('KA');
});

it.each([null, 'unavailable'])('leaves the state editable when the tenant state is %s', async defaultStateCode => {
  const user = userEvent.setup({ delay: null });
  mount(true, true, { defaultCountryCode: 'IN', defaultStateCode });
  await screen.findByRole('textbox', { name: /Legal name/ });
  await fillBusiness(user);
  await waitFor(() => expect(screen.getByRole('combobox', { name: 'State' })).toBeEnabled());
  expect(screen.getByRole('combobox', { name: 'Country' })).toHaveValue('IN');
  expect(screen.getByRole('combobox', { name: 'State' })).toHaveValue('');
  await user.selectOptions(screen.getByRole('combobox', { name: 'State' }), 'KA');
  expect(screen.getByRole('combobox', { name: 'State' })).toHaveValue('KA');
});

it('requires a manual country when the tenant jurisdiction is unavailable', async () => {
  const user = userEvent.setup({ delay: null });
  mount(true, true, { defaultCountryCode: 'ZZ', defaultStateCode: 'MH' });
  await screen.findByRole('textbox', { name: /Legal name/ });
  await fillBusiness(user);
  expect(screen.getByRole('combobox', { name: 'Country' })).toHaveValue('');
  expect(screen.getByRole('combobox', { name: 'State' })).toBeDisabled();
  expect(companyCall).not.toHaveBeenCalledWith('identity', '/v1/reference/countries/ZZ/states', expect.anything());
});

it('preserves a changed country and state when the tenant state request finishes late', async () => {
  const standard = vi.mocked(companyCall).getMockImplementation()!;
  let finish!: (value: unknown) => void;
  vi.mocked(companyCall).mockImplementation((service, path, request) => path === '/v1/reference/countries/IN/states'
    ? new Promise(resolve => { finish = resolve; }) : standard(service, path, request));
  const user = userEvent.setup({ delay: null });
  mount(true, true, { defaultCountryCode: 'IN', defaultStateCode: 'MH' });
  await screen.findByRole('textbox', { name: /Legal name/ });
  await fillBusiness(user);
  await waitFor(() => expect(finish).toBeDefined());
  await user.selectOptions(screen.getByRole('combobox', { name: 'Country' }), 'GB');
  await waitFor(() => expect(screen.getAllByRole('combobox', { name: 'Country' })[1]).toBeEnabled());
  expect(screen.getAllByRole('combobox', { name: 'Country' })[1]).toHaveValue('');
  await user.selectOptions(screen.getAllByRole('combobox', { name: 'Country' })[1], 'ENG');
  await act(async () => { finish(STATES); });
  expect(screen.getAllByRole('combobox', { name: 'Country' })[0]).toHaveValue('GB');
  expect(screen.getAllByRole('combobox', { name: 'Country' })[1]).toHaveValue('ENG');
});

it('keeps the trading name in sync until the user edits or clears it', async () => {
  const user = userEvent.setup({ delay: null });
  mount();
  const legal = await screen.findByRole('textbox', { name: /Legal name/ });
  const trading = screen.getByRole('textbox', { name: /Trading name/ });
  await user.type(legal, 'Acme');
  expect(trading).toHaveValue('Acme');
  await user.type(legal, ' Limited');
  expect(trading).toHaveValue('Acme Limited');
  await user.clear(legal);
  expect(trading).toHaveValue('');
  await user.type(legal, 'Acme Limited');
  await user.clear(trading);
  await user.type(trading, 'Acme Stores');
  await user.type(legal, ' UK');
  expect(trading).toHaveValue('Acme Stores');
  await user.clear(trading);
  await user.type(legal, ' Branch');
  expect(trading).toHaveValue('');
});

it('suggests an editable short name from the legal name', async () => {
  const user = userEvent.setup({ delay: null });
  mount();
  await waitFor(() => expect(screen.getByRole('textbox', { name: /Legal name/ })).toBeInTheDocument());

  await user.type(screen.getByRole('textbox', { name: /Legal name/ }), 'Acme Manufacturing Private Limited');
  expect(screen.getByRole('textbox', { name: /Short name/ })).toHaveValue('AMPL');

  await user.clear(screen.getByRole('textbox', { name: /Short name/ }));
  await user.type(screen.getByRole('textbox', { name: /Short name/ }), 'Acme');
  await user.type(screen.getByRole('textbox', { name: /Legal name/ }), ' India');
  expect(screen.getByRole('textbox', { name: /Short name/ })).toHaveValue('Acme');
  await user.clear(screen.getByRole('textbox', { name: /Short name/ }));
  await user.type(screen.getByRole('textbox', { name: /Legal name/ }), ' Branch');
  expect(screen.getByRole('textbox', { name: /Short name/ })).toHaveValue('');
});

/*
 * The company code is generated, not asked for: the operator cannot know what is already
 * taken inside the tenant, so a typed code either duplicates one or is unique by luck.
 */
describe('the generated company code', () => {
  /** The stem, then four characters of the unambiguous suffix alphabet. */
  const GENERATED = /^ACME-[2-9A-HJ-NP-Z]{4}$/;

  it('is not a field on the first step, and the step completes without one', async () => {
    const user = userEvent.setup({ delay: null });
    mount();
    await screen.findByRole('textbox', { name: /Legal name/ });

    expect(screen.queryByRole('textbox', { name: /Company code/ })).toBeNull();
    await fillBusiness(user);
    expect(screen.getByRole('heading', { level: 1, name: 'Location and tax' })).toBeInTheDocument();
  });

  it('is shown on the review step, with what it costs to have one', async () => {
    const user = userEvent.setup({ delay: null });
    mount();
    await screen.findByRole('textbox', { name: /Legal name/ });
    await reachReview(user);

    const row = screen.getByText('Company code').parentElement as HTMLElement;
    expect(within(row).getByText(GENERATED)).toBeInTheDocument();
    expect(row).toHaveTextContent('cannot be changed once anything is posted');
    // No way back to a field that does not exist.
    expect(within(row).queryByRole('button', { name: /Edit/ })).toBeNull();
  });

  it('is what the create call carries', async () => {
    const user = userEvent.setup({ delay: null });
    mount();
    await screen.findByRole('textbox', { name: /Legal name/ });
    await reachReview(user);
    await user.click(screen.getByRole('button', { name: 'Create this company' }));

    await waitFor(() => expect(companyCall).toHaveBeenCalledWith('identity', '/v1/companies', expect.objectContaining({
      method: 'POST', body: expect.objectContaining({ code: expect.stringMatching(GENERATED) }),
    })));
  });

  it('rolls a new suffix on a 409 and still creates exactly one company', async () => {
    const user = userEvent.setup({ delay: null });
    let attempts = 0;
    answer();
    const routed = vi.mocked(companyCall).getMockImplementation();
    vi.mocked(companyCall).mockImplementation(async (service, path, request = {}) => {
      if (path === '/v1/companies' && request.method === 'POST') {
        attempts += 1;
        // Identity names the field in conflict, which is what tells a taken code apart from
        // this route's other 409 — and is exactly why the operator need not be asked to fix it.
        if (attempts === 1) throw { status: 409, message: 'a company with this code already exists.', fields: { code: 'already in use' } };
        return { id: COMPANY } as never;
      }
      return (await routed!(service, path, request)) as never;
    });

    mount();
    await screen.findByRole('textbox', { name: /Legal name/ });
    await reachReview(user);
    await user.click(screen.getByRole('button', { name: 'Create this company' }));

    await waitFor(() => expect(screen.getByText('Open this company')).toBeInTheDocument());
    const creates = vi.mocked(companyCall).mock.calls.filter(([, path, request]) => path === '/v1/companies' && request?.method === 'POST');
    expect(creates).toHaveLength(2);
    const codes = creates.map(([, , request]) => (request?.body as { code: string }).code);
    expect(codes[0]).toMatch(GENERATED);
    expect(codes[1]).toMatch(GENERATED);
    expect(codes[1]).not.toBe(codes[0]);
    // One company, not two: the 409 created nothing, and nothing else re-ran.
    expect(screen.queryByText('Failed')).toBeNull();
  });

  it('does not re-roll the code for a conflict that is not about the code', async () => {
    const user = userEvent.setup({ delay: null });
    answer();
    const routed = vi.mocked(companyCall).getMockImplementation();
    vi.mocked(companyCall).mockImplementation(async (service, path, request = {}) => {
      if (path === '/v1/companies' && request.method === 'POST') {
        // This route's other 409: `grant_company_creator` refusing an unseeded role
        // catalogue. Retrying it would fire three creates and change the code twice before
        // showing a message that was already final on the first attempt.
        throw { status: 409, message: 'seed active system roles before creating a company' };
      }
      return (await routed!(service, path, request)) as never;
    });

    mount();
    await screen.findByRole('textbox', { name: /Legal name/ });
    await reachReview(user);
    await user.click(screen.getByRole('button', { name: 'Create this company' }));

    await waitFor(() => expect(screen.getAllByText('seed active system roles before creating a company').length).toBeGreaterThan(0));
    expect(vi.mocked(companyCall).mock.calls.filter(([, path, request]) => path === '/v1/companies' && request?.method === 'POST')).toHaveLength(1);
  });
});

it('refuses to leave a step with a required field empty, and says which', async () => {
  const user = userEvent.setup({ delay: null });
  mount();
  await waitFor(() => expect(screen.getByRole('textbox', { name: /Legal name/ })).toBeInTheDocument());

  await user.click(screen.getByRole('button', { name: 'Next' }));
  expect(screen.getByRole('heading', { level: 1, name: 'Business' })).toBeInTheDocument();
  expect(screen.getByText('Fill in the highlighted fields to continue.')).toBeInTheDocument();
  expect(screen.getAllByText('Required').length).toBeGreaterThan(0);
});

it('offers only jurisdictions with a tax profile, and adopts the one tax system', async () => {
  const user = userEvent.setup({ delay: null });
  mount();
  await waitFor(() => expect(screen.getByRole('textbox', { name: /Legal name/ })).toBeInTheDocument());
  await fillBusiness(user);

  const countries = screen.getByRole('combobox', { name: 'Country' });
  expect(within(countries).getByRole('option', { name: /India/ })).toBeInTheDocument();
  expect(within(countries).queryByRole('option', { name: /Nowhere/ })).not.toBeInTheDocument();

  await user.selectOptions(countries, 'IN');
  await waitFor(() => expect(screen.getByRole('combobox', { name: /Tax system/ })).toHaveValue('gst_in'));
  // India's subdivision label, from the jurisdiction, not a hardcoded "State".
  await waitFor(() => expect(screen.getByRole('combobox', { name: 'State' })).toBeEnabled());
});

it('previews amounts, dates and the first year from the draft, not from the open company', async () => {
  const user = userEvent.setup({ delay: null });
  mount();
  await waitFor(() => expect(screen.getByRole('textbox', { name: /Legal name/ })).toBeInTheDocument());
  await fillBusiness(user);
  await fillLocation(user);

  // India: ₹ prefix, Indian grouping, dd-MM-yyyy, April–March year.
  expect(screen.getByText('₹12,34,567.89')).toBeInTheDocument();
  expect(screen.getByText(/FY\d{4}-\d{4} · \d{2}-\d{2}-\d{4} → \d{2}-\d{2}-\d{4}/)).toBeInTheDocument();

  // Changing the convention changes the preview — it is the draft being formatted.
  await user.selectOptions(screen.getByRole('combobox', { name: /Amount decimals/ }), '0');
  expect(screen.getByText('₹12,34,568')).toBeInTheDocument();
});

it('closes feature dependencies upward, and back down again', async () => {
  const user = userEvent.setup({ delay: null });
  mount();
  await waitFor(() => expect(screen.getByRole('textbox', { name: /Legal name/ })).toBeInTheDocument());
  await fillBusiness(user);
  await fillLocation(user);
  await user.click(screen.getByRole('button', { name: 'Next' }));

  await user.click(screen.getByRole('checkbox', { name: 'Expiry dates' }));
  expect(screen.getByRole('checkbox', { name: 'Batches' })).toBeChecked();
  expect(screen.getByRole('checkbox', { name: 'Stock and inventory' })).toBeChecked();

  await user.click(screen.getByRole('checkbox', { name: 'Stock and inventory' }));
  expect(screen.getByRole('checkbox', { name: 'Batches' })).not.toBeChecked();
  expect(screen.getByRole('checkbox', { name: 'Expiry dates' })).not.toBeChecked();
});

/*
 * The jurisdiction's own suggestions, pre-selected. The list is the server's
 * (`CountryChoice.default_features`, from the profile in `billing_platform.jurisdiction`) —
 * a client-side list would be a fourth opinion about what a company in India does.
 */
describe('the capabilities a jurisdiction suggests', () => {
  async function reachCapabilities(user: ReturnType<typeof userEvent.setup>, country = 'IN') {
    await screen.findByRole('textbox', { name: /Legal name/ });
    await fillBusiness(user);
    await user.selectOptions(screen.getByRole('combobox', { name: 'Country' }), country);
    await waitFor(() => expect(screen.getByRole('combobox', { name: /Tax system/ })).not.toHaveValue(''));
    await user.selectOptions(screen.getAllByRole('combobox', { name: country === 'GB' ? 'Country' : 'State' })[country === 'GB' ? 1 : 0], country === 'GB' ? 'ENG' : 'MH');
    await user.click(screen.getByRole('switch', { name: 'Add registration later' }));
    await user.click(screen.getByRole('button', { name: 'Next' }));
    await user.click(screen.getByRole('button', { name: 'Next' }));
  }

  it('arrives selected for India, including the GST document and what it depends on', async () => {
    const user = userEvent.setup({ delay: null });
    mount();
    await reachCapabilities(user);

    expect(screen.getByRole('checkbox', { name: 'Stock and inventory' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'Credit limits' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'E-way bills' })).toBeChecked();
    // Offered, not assumed: a turnover threshold and IRP credentials decide this one.
    expect(screen.getByRole('checkbox', { name: 'GST e-invoicing' })).not.toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'Batches' })).not.toBeChecked();
    expect(screen.getByText(/already selected/)).toBeInTheDocument();
  });

  it('suggests the UK set for a UK company, which has no GST documents to suggest', async () => {
    const user = userEvent.setup({ delay: null });
    mount();
    await reachCapabilities(user, 'GB');

    expect(screen.getByRole('checkbox', { name: 'Stock and inventory' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'Credit limits' })).toBeChecked();
    expect(screen.queryByRole('checkbox', { name: 'E-way bills' })).toBeNull();
  });

  it('is a suggestion: clearing one holds, and a later country change does not undo it', async () => {
    const user = userEvent.setup({ delay: null });
    mount();
    await reachCapabilities(user);
    await user.click(screen.getByRole('checkbox', { name: 'Stock and inventory' }));
    expect(screen.getByRole('checkbox', { name: 'Stock and inventory' })).not.toBeChecked();
    // Dropping stock drops what needed it, as any other clearing does.
    expect(screen.getByRole('checkbox', { name: 'E-way bills' })).not.toBeChecked();

    // Back to the jurisdiction step and change it: the conventions re-suggest, the
    // capability decision stands.
    await user.click(screen.getByRole('button', { name: 'Back' }));
    await user.click(screen.getByRole('button', { name: 'Back' }));
    await user.selectOptions(screen.getByRole('combobox', { name: 'Country' }), 'GB');
    await waitFor(() => expect(screen.getByRole('combobox', { name: /Tax system/ })).toHaveValue('vat_gb'));
    await user.selectOptions(screen.getAllByRole('combobox', { name: 'Country' })[1], 'ENG');
    await user.click(screen.getByRole('switch', { name: 'Add registration later' }));
    await user.click(screen.getByRole('button', { name: 'Next' }));
    await user.click(screen.getByRole('button', { name: 'Next' }));
    expect(screen.getByRole('checkbox', { name: 'Stock and inventory' })).not.toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'Credit limits' })).toBeChecked();
  });

  it('stops claiming a selection once every suggested card is cleared', async () => {
    const user = userEvent.setup({ delay: null });
    mount();
    await reachCapabilities(user);
    expect(screen.getByText(/already selected/)).toBeInTheDocument();

    // Stock takes the e-way bill with it, so two clicks clear all three.
    await user.click(screen.getByRole('checkbox', { name: 'Stock and inventory' }));
    await user.click(screen.getByRole('checkbox', { name: 'Credit limits' }));

    // The sentence is the only thing on the step that says who chose, so it has to follow
    // the selection rather than the jurisdiction.
    expect(screen.queryByText(/already selected/)).toBeNull();
  });

  it('drops a chosen capability the new jurisdiction cannot offer', async () => {
    const user = userEvent.setup({ delay: null });
    mount();
    await reachCapabilities(user);
    // Touch the step, so the selection is now the operator's and is carried forward.
    await user.click(screen.getByRole('checkbox', { name: 'Budgets' }));
    await user.click(screen.getByRole('button', { name: 'Back' }));
    await user.click(screen.getByRole('button', { name: 'Back' }));
    await user.selectOptions(screen.getByRole('combobox', { name: 'Country' }), 'GB');
    await waitFor(() => expect(screen.getByRole('combobox', { name: /Tax system/ })).toHaveValue('vat_gb'));
    await user.selectOptions(screen.getAllByRole('combobox', { name: 'Country' })[1], 'ENG');
    // Money, capabilities, presentation, review.
    await user.click(screen.getByRole('switch', { name: 'Add registration later' }));
    for (let step = 0; step < 4; step += 1) await user.click(screen.getByRole('button', { name: 'Next' }));
    await user.click(screen.getByRole('button', { name: 'Create this company' }));

    // Carried forward, and `e_waybill` is not — which would otherwise be a 422 from the
    // enable call after the company already exists.
    await waitFor(() => expect(openCompany).toHaveBeenCalled());
    expect(vi.mocked(companyCall).mock.calls.find(([, path]) => path === '/v1/companies')?.[2]?.body).toEqual(expect.objectContaining({ setup: expect.objectContaining({ features: expect.arrayContaining(['budgets']) }) }));
    expect((vi.mocked(companyCall).mock.calls.find(([, path]) => path === '/v1/companies')?.[2]?.body as { setup: { features: string[] } }).setup.features).not.toContain('e_waybill');
  });

  it('suggests capabilities using the creator access granted on the new company', async () => {
    const user = userEvent.setup({ delay: null });
    mount(true, false);
    await reachCapabilities(user);

    expect(screen.getByRole('checkbox', { name: 'Stock and inventory' })).toBeEnabled();
    expect(screen.getByRole('checkbox', { name: 'Stock and inventory' })).toBeChecked();

    // Presentation, then review.
    for (let step = 0; step < 2; step += 1) await user.click(screen.getByRole('button', { name: 'Next' }));
    await user.click(screen.getByRole('button', { name: 'Create this company' }));
    await waitFor(() => expect(companyCall).toHaveBeenCalledWith('identity', '/v1/companies', expect.objectContaining({ method: 'POST' })));
    expect(vi.mocked(companyCall).mock.calls.find(([, path]) => path === '/v1/companies')?.[2]?.body).toEqual(expect.objectContaining({ setup: expect.objectContaining({ features: expect.arrayContaining(['inventory']) }) }));
  });

  it('adopts the tenant jurisdiction suggestions without the operator opening step 2', async () => {
    const user = userEvent.setup({ delay: null });
    mount(true, true, { defaultCountryCode: 'IN', defaultStateCode: 'MH' });
    await screen.findByRole('textbox', { name: /Legal name/ });
    await fillBusiness(user);
    await waitFor(() => expect(screen.getByRole('combobox', { name: 'State' })).toHaveValue('MH'));
    await user.click(screen.getByRole('switch', { name: 'Add registration later' }));
    await user.click(screen.getByRole('button', { name: 'Next' }));
    await user.click(screen.getByRole('button', { name: 'Next' }));

    expect(screen.getByRole('checkbox', { name: 'Stock and inventory' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'E-way bills' })).toBeChecked();
  });
});

it('offers a statutory feature only under the tax system that has it', async () => {
  const user = userEvent.setup({ delay: null });
  mount();
  await waitFor(() => expect(screen.getByRole('textbox', { name: /Legal name/ })).toBeInTheDocument());
  await fillBusiness(user);
  await user.selectOptions(screen.getByRole('combobox', { name: 'Country' }), 'GB');
  await waitFor(() => expect(screen.getByRole('combobox', { name: /Tax system/ })).toHaveValue('vat_gb'));
  // GB names its own subdivisions "Country" as well, so the selects are matched exactly.
  await user.selectOptions(screen.getAllByRole('combobox', { name: 'Country' })[0], 'IN');
  await waitFor(() => expect(screen.getByRole('combobox', { name: /State/ })).toBeEnabled());
  await user.selectOptions(screen.getByRole('combobox', { name: /State/ }), 'MH');
  await user.click(screen.getByRole('switch', { name: 'Add registration later' }));
  await user.click(screen.getByRole('button', { name: 'Next' }));
  await user.click(screen.getByRole('button', { name: 'Next' }));

  expect(screen.getByRole('checkbox', { name: 'GST e-invoicing' })).toBeInTheDocument();
});

/*
 * A code conflict that no fresh suffix clears. The retry is bounded at three attempts, so a
 * server that keeps rejecting the code still reaches the operator rather than looping.
 */
it('gives up on a code conflict a new suffix does not clear, and keeps the way back', async () => {
  const user = userEvent.setup({ delay: null });
  vi.mocked(companyCall).mockImplementation(async (_service, path, request = {}) => {
    if (path === '/v1/entities/identity.company/field-set') return { fields: [] } as never;
    if (path === '/v1/reference/countries') return COUNTRIES as never;
    if (path === '/v1/reference/currencies') return CURRENCIES as never;
    if (path === '/v1/company-features') return FEATURE_CATALOGUE as never;
    if (path.endsWith('/states')) return STATES as never;
    if (path === '/v1/companies' && request.method === 'POST') throw { status: 409, message: 'This company code is already in use.', fields: { code: 'already in use' } };
    throw new Error('unexpected call ' + path);
  });
  mount();
  await waitFor(() => expect(screen.getByRole('textbox', { name: /Legal name/ })).toBeInTheDocument());
  await reachReview(user);
  await user.click(screen.getByRole('button', { name: 'Create this company' }));

  await waitFor(() => expect(screen.getAllByText('This company code is already in use.').length).toBeGreaterThan(0));
  expect(screen.getByText('Failed').closest('li')).toHaveTextContent(/Save the company and automatic setup request/);
  expect(vi.mocked(companyCall).mock.calls.filter(([, path, request]) => path === '/v1/companies' && request?.method === 'POST')).toHaveLength(3);
  expect(openCompany).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button', { name: 'Edit company details' }));
  await user.click(screen.getByRole('button', { name: 'Back' }));
  expect(screen.getByRole('heading', { name: 'Presentation' })).toBeVisible();
});

it('loads and validates required custom fields before creation', async () => {
  answer({ metadata: { fields: [{ key: 'custom_field:cf_segment', label: 'Market segment', source: 'custom', is_visible: true,
    writable: true, required: true, group: 'custom', custom: { key: 'cf_segment', data_type: 'text', validation: { required: true } } }] } });
  const user = userEvent.setup({ delay: null }); mount(false);
  await screen.findByRole('textbox', { name: /Legal name/ }); await reachReview(user);
  await user.click(screen.getByRole('button', { name: 'Create this company' }));
  expect(screen.getByText('Market segment is required.')).toBeVisible();
  expect(vi.mocked(companyCall).mock.calls.some(call => call[1] === '/v1/companies')).toBe(false);
  await user.type(screen.getByRole('textbox', { name: 'Market segment' }), 'Retail');
  await user.click(screen.getByRole('button', { name: 'Create this company' }));
  await waitFor(() => expect(openCompany).toHaveBeenCalledWith(COMPANY, undefined, 'company'));
  const create = vi.mocked(companyCall).mock.calls.find(call => call[1] === '/v1/companies');
  expect(create?.[2]?.body).toMatchObject({ custom_fields: { cf_segment: 'Retail' } });
});

it('allows new-company feature configuration without granting tenant-wide company update', async () => {
  const user = userEvent.setup({ delay: null }); mount(false, false);
  await screen.findByRole('textbox', { name: /Legal name/ }); await fillBusiness(user); await fillLocation(user);
  await user.click(screen.getByRole('button', { name: 'Next' }));
  expect(screen.getByRole('checkbox', { name: 'Stock and inventory' })).toBeEnabled();
  expect(screen.queryByText(/Enabling optional features needs tenant-level company.update/)).not.toBeInTheDocument();
});

it('says so when the reference lists cannot be loaded at all', async () => {
  vi.mocked(companyCall).mockRejectedValue({ status: 503, message: 'Company setup is unavailable. Retry the same action.' });
  mount();

  await waitFor(() => expect(screen.getByRole('heading', { level: 1, name: 'Company setup is unavailable' })).toBeInTheDocument());
  expect(screen.getByText('Company setup is unavailable. Retry the same action.')).toBeInTheDocument();
});

it('collects GST registration in Location and tax and saves it with the company', async () => {
  const user = userEvent.setup({ delay: null }); mount();
  await screen.findByRole('textbox', { name: /Legal name/ }); await fillBusiness(user);
  await user.selectOptions(screen.getByRole('combobox', { name: 'Country' }), 'IN');
  await waitFor(() => expect(screen.getByRole('combobox', { name: 'State' })).toBeEnabled());
  await user.selectOptions(screen.getByRole('combobox', { name: 'State' }), 'MH');
  const group = screen.getByRole('group', { name: 'GST registration' });
  expect(within(group).getByRole('switch', { name: 'Add registration later' }).closest('legend')).toHaveTextContent('GST registration');
  expect(within(group).getByRole('switch', { name: 'Add registration later' })).not.toBeChecked();
  expect(within(group).getByRole('textbox', { name: /GSTIN/ })).toHaveValue('');
  await user.type(within(group).getByRole('textbox', { name: /GSTIN/ }), '27AAAPA1234A1ZT');
  expect(within(group).queryByText(/GST on purchases will remain unavailable/)).not.toBeInTheDocument();
  expect(within(group).getByText('Save GST details to set up tax ledgers. Registration must cover the purchase bill date.')).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Next' }));
  expect(screen.getByRole('heading', { name: 'Location and tax' })).toBeInTheDocument();
  fireEvent.change(within(group).getByLabelText(/Registration effective date/), { target: { value: '2026-04-01' } });
  await user.selectOptions(within(group).getByRole('combobox', { name: /Registration type/ }), 'composition');
  for (let step = 0; step < 4; step++) await user.click(screen.getByRole('button', { name: 'Next' }));
  expect(screen.getByText(/27AAAPA1234A1ZT/)).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Create this company' }));
  await waitFor(() => expect(openCompany).toHaveBeenCalledOnce());
  const writes = vi.mocked(companyCall).mock.calls.filter(([, , options]) => options?.method === 'POST');
  expect(writes).toHaveLength(1);
  expect(writes[0][2]?.body).toEqual(expect.objectContaining({
    trade_name: 'Acme Manufacturing Private Limited',
    initial_tax_registration: { number: '27AAAPA1234A1ZT', regime: 'composition', valid_from: '2026-04-01' },
  }));
});

it('switches to VAT fields and discards the previous jurisdiction registration', async () => {
  const user = userEvent.setup({ delay: null }); mount();
  await screen.findByRole('textbox', { name: /Legal name/ }); await fillBusiness(user);
  await user.selectOptions(screen.getByRole('combobox', { name: 'Country' }), 'IN');
  await user.type(await screen.findByRole('textbox', { name: /GSTIN/ }), '27AAAPA1234A1ZT');
  await user.selectOptions(screen.getByRole('combobox', { name: 'Country' }), 'GB');
  expect(screen.queryByRole('textbox', { name: /GSTIN/ })).not.toBeInTheDocument();
  const vat = screen.getByRole('group', { name: 'VAT registration' });
  expect(within(vat).getByRole('switch', { name: 'Add registration later' }).closest('legend')).toHaveTextContent('VAT registration');
  expect(within(vat).getByRole('switch', { name: 'Add registration later' })).not.toBeChecked();
  expect(within(vat).getByRole('textbox', { name: /VAT registration number/ })).toHaveValue('');
  expect(within(vat).getByRole('combobox', { name: /Registration type/ })).toHaveValue('standard');
  await user.type(within(vat).getByRole('textbox', { name: /VAT registration number/ }), 'GB123456789');
  fireEvent.change(within(vat).getByLabelText(/Registration effective date/), { target: { value: '2026-04-06' } });
  const later = within(vat).getByRole('switch', { name: 'Add registration later' });
  later.focus();
  await user.keyboard('[Space]');
  expect(later).toBeChecked();
  expect(within(vat).queryByRole('textbox')).not.toBeInTheDocument();
  await user.keyboard('[Space]');
  expect(later).not.toBeChecked();
  expect(within(vat).getByRole('textbox', { name: /VAT registration number/ })).toHaveValue('');
  expect(within(vat).getByLabelText(/Registration effective date/)).toHaveValue('');
});

it('discards a GST registration when its state changes, and omits it when explicitly deferred', async () => {
  const user = userEvent.setup({ delay: null }); mount();
  await screen.findByRole('textbox', { name: /Legal name/ }); await fillBusiness(user);
  await user.selectOptions(screen.getByRole('combobox', { name: 'Country' }), 'IN');
  await waitFor(() => expect(screen.getByRole('combobox', { name: 'State' })).toBeEnabled());
  await user.selectOptions(screen.getByRole('combobox', { name: 'State' }), 'MH');
  await user.type(screen.getByRole('textbox', { name: /GSTIN/ }), '27AAAPA1234A1ZT');
  await user.selectOptions(screen.getByRole('combobox', { name: 'State' }), 'KA');
  expect(screen.getByRole('textbox', { name: /GSTIN/ })).toHaveValue('');
  expect(screen.getByRole('switch', { name: 'Add registration later' })).not.toBeChecked();
  await user.type(screen.getByRole('textbox', { name: /GSTIN/ }), '29AAAPA1234A1ZP');
  await user.click(screen.getByRole('switch', { name: 'Add registration later' }));
  for (let step = 0; step < 4; step++) await user.click(screen.getByRole('button', { name: 'Next' }));
  await user.click(screen.getByRole('button', { name: 'Create this company' }));
  await waitFor(() => expect(openCompany).toHaveBeenCalledOnce());
  expect(vi.mocked(companyCall).mock.calls.find(([, path]) => path === '/v1/companies')?.[2]?.body).not.toHaveProperty('initial_tax_registration');
});

it('shows registration validation errors beside the field and allows correction', async () => {
  const original = vi.mocked(companyCall).getMockImplementation()!;
  vi.mocked(companyCall).mockImplementation(async (service, path, options) => {
    if (path === '/v1/companies') throw { status: 422, message: 'Check registration details', fields: { 'body.initial_tax_registration.number': 'Check the GSTIN checksum.' } };
    return original(service, path, options);
  });
  const user = userEvent.setup({ delay: null }); mount();
  await screen.findByRole('textbox', { name: /Legal name/ }); await fillBusiness(user);
  await user.selectOptions(screen.getByRole('combobox', { name: 'Country' }), 'IN');
  await waitFor(() => expect(screen.getByRole('combobox', { name: 'State' })).toBeEnabled());
  await user.selectOptions(screen.getByRole('combobox', { name: 'State' }), 'MH');
  await user.type(screen.getByRole('textbox', { name: /GSTIN/ }), '27AAAPA1234A1Z0');
  fireEvent.change(screen.getByLabelText(/Registration effective date/), { target: { value: '2026-04-01' } });
  for (let step = 0; step < 4; step++) await user.click(screen.getByRole('button', { name: 'Next' }));
  await user.click(screen.getByRole('button', { name: 'Create this company' }));
  await user.click(await screen.findByRole('button', { name: 'Edit company details' }));
  await user.click(screen.getByRole('button', { name: 'Edit gstin' }));
  expect(screen.getByRole('textbox', { name: /GSTIN/ })).toHaveAttribute('aria-invalid', 'true');
  expect(screen.getByText('Check the GSTIN checksum.')).toBeInTheDocument();
  await user.clear(screen.getByRole('textbox', { name: /GSTIN/ }));
  expect(screen.queryByText('Check the GSTIN checksum.')).not.toBeInTheDocument();
  expect(openCompany).not.toHaveBeenCalled();
});

it.each(['RUNNING', 'NEEDS_ACTION'])('shows live setup and waits for completion before opening: %s', async initial => {
  const original = vi.mocked(companyCall).getMockImplementation()!;
  let complete = false;
  vi.mocked(companyCall).mockImplementation(async (service, path, options) => {
    if (path === `/v1/companies/${COMPANY}/setup`) return { company_id: COMPANY,
      status: complete ? 'COMPLETE' : initial, updated_at: new Date().toISOString(),
      steps: [{ key: 'books', status: complete ? 'READY' : initial }, { key: 'opening', status: 'AWAITING_OPENING' }] } as never;
    if (path.endsWith('/setup/retry')) return {} as never;
    return original(service, path, options);
  });
  const user = userEvent.setup({ delay: null }); mount();
  await screen.findByRole('textbox', { name: /Legal name/ }); await reachReview(user);
  vi.useFakeTimers();
  try {
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Create this company' })); });
    expect(screen.getByText('Automatic company setup')).toBeVisible();
    expect(screen.getByText(initial === 'RUNNING' ? 'Books: Preparing automatically' : 'Books: Needs review')).toBeVisible();
    expect(openCompany).not.toHaveBeenCalled();
    complete = true;
    await act(async () => {
      if (initial === 'NEEDS_ACTION') fireEvent.click(screen.getByRole('button', { name: 'Complete remaining setup' }));
      else await vi.advanceTimersByTimeAsync(5000);
    });
    expect(openCompany).toHaveBeenCalledOnce();
    const creates = vi.mocked(companyCall).mock.calls.filter(([, path, options]) => path === '/v1/companies' && options?.method === 'POST');
    expect(creates).toHaveLength(1);
    expect(creates[0][2]?.body).toMatchObject({ setup: { opening_choice: 'ZERO_CONFIRMED' } });
  } finally { vi.useRealTimers(); }
});

it('submits one durable setup plan and opens only after the server confirms preparation', async () => {
  const user = userEvent.setup({ delay: null }); mount();
  await screen.findByRole('textbox', { name: /Legal name/ }); await reachReview(user);
  await user.click(screen.getByRole('button', { name: 'Create this company' }));
  await waitFor(() => expect(openCompany).toHaveBeenCalledOnce());
  const writes = vi.mocked(companyCall).mock.calls.filter(([, , options]) => options?.method === 'POST');
  expect(writes).toHaveLength(1);
  expect(writes[0][0]).toBe('identity');
  expect(writes[0][1]).toBe('/v1/companies');
  expect(writes[0][2]?.key).toMatch(/^[0-9a-f-]{36}$/);
  expect(writes[0][2]?.body).toEqual(expect.objectContaining({ setup: expect.objectContaining({ opening_choice: 'ZERO_CONFIRMED', features: expect.arrayContaining(['inventory']) }) }));
});

it('lets the user open explicitly while preparation continues without recreating the company', async () => {
  const original = vi.mocked(companyCall).getMockImplementation()!;
  vi.mocked(companyCall).mockImplementation(async (service, path, options) => path.endsWith('/setup')
    ? { company_id: COMPANY, status: 'RUNNING', steps: [{ key: 'books', status: 'RUNNING' }] } as never
    : original(service, path, options));
  const user = userEvent.setup({ delay: null }); mount();
  await screen.findByRole('textbox', { name: /Legal name/ }); await reachReview(user);
  await user.click(screen.getByRole('button', { name: 'Create this company' }));
  expect(await screen.findByText('Books: Preparing automatically')).toBeVisible();
  expect(openCompany).not.toHaveBeenCalled();
  expect(window.dispatchEvent(new Event(BEFORE_COMPANY_CHANGE, { cancelable: true }))).toBe(true);
  await user.click(screen.getByRole('button', { name: 'Open while setup continues' }));
  expect(openCompany).toHaveBeenCalledOnce();
  expect(vi.mocked(companyCall).mock.calls.filter(([, path, options]) => path === '/v1/companies' && options?.method === 'POST')).toHaveLength(1);
});

it('does not reopen the company after the user leaves while preparation continues', async () => {
  const original = vi.mocked(companyCall).getMockImplementation()!;
  let complete = false;
  vi.mocked(companyCall).mockImplementation(async (service, path, options) => path.endsWith('/setup')
    ? { company_id: COMPANY, status: complete ? 'COMPLETE' : 'RUNNING', steps: [{ key: 'books', status: complete ? 'READY' : 'RUNNING' }] } as never
    : original(service, path, options));
  const user = userEvent.setup({ delay: null }); mount();
  await screen.findByRole('textbox', { name: /Legal name/ }); await reachReview(user);
  vi.useFakeTimers();
  try {
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Create this company' })); });
    fireEvent.click(screen.getByRole('button', { name: 'Leave for now' }));
    expect(goTo).toHaveBeenCalled();
    complete = true;
    await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
    expect(openCompany).not.toHaveBeenCalled();
  } finally { vi.useRealTimers(); }
});

it('replays the exact company creation command after a lost response', async () => {
  const original = vi.mocked(companyCall).getMockImplementation()!;
  let attempts = 0;
  vi.mocked(companyCall).mockImplementation(async (service, path, options) => {
    if (path === '/v1/companies' && options?.method === 'POST' && ++attempts === 1) throw { status: 503, message: 'Response lost' };
    return original(service, path, options);
  });
  const user = userEvent.setup({ delay: null }); mount();
  await screen.findByRole('textbox', { name: /Legal name/ }); await reachReview(user);
  await user.click(screen.getByRole('button', { name: 'Create this company' }));
  expect(screen.queryByText('Your setup request is saved with the company and continues automatically.')).not.toBeInTheDocument();
  await user.click(await screen.findByRole('button', { name: 'Retry the remaining steps' }));
  await waitFor(() => expect(openCompany).toHaveBeenCalledOnce());
  const writes = vi.mocked(companyCall).mock.calls.filter(([, path]) => path === '/v1/companies');
  expect(writes).toHaveLength(2); expect(writes[0]).toEqual(writes[1]);
});

it('requires an explicit reason for confirmed zero opening balances', async () => {
  const user = userEvent.setup({ delay: null }); mount();
  await screen.findByRole('textbox', { name: /Legal name/ }); await reachReview(user);
  await user.selectOptions(screen.getByRole('combobox', { name: 'How does this company start?' }), 'ZERO_CONFIRMED');
  await user.clear(screen.getByRole('textbox', { name: /Reason for zero opening balances/ }));
  await user.type(screen.getByRole('textbox', { name: /Reason for zero opening balances/ }), 'New business with no prior balances');
  await user.click(screen.getByRole('button', { name: 'Create this company' }));
  await waitFor(() => expect(openCompany).toHaveBeenCalledOnce());
  expect(vi.mocked(companyCall).mock.calls.find(([, path]) => path === '/v1/companies')?.[2]?.body).toEqual(expect.objectContaining({ setup: expect.objectContaining({ opening_choice: 'ZERO_CONFIRMED', opening_reason: 'New business with no prior balances' }) }));
});
