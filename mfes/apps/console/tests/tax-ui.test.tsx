import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { DisplayConfigProvider, PermissionProvider } from '@janso/ui';
import { TaxEditor } from '../app/components/TaxEditor';
import { TaxDetail } from '../app/components/TaxDetail';
import { TaxDirectory, TaxOverview } from '../app/components/TaxDirectory';
import { TaxSetup } from '../app/components/TaxSetup';
import { taxConfig } from '../app/lib/tax-masters';
import { serviceCall } from '../app/lib/service-call';
import { goTo } from '../app/lib/navigate';
import { BEFORE_COMPANY_CHANGE } from '../app/lib/use-unsaved-changes';
import { CATEGORY, CLASSIFICATION, COMPANY, RATE, RULE, SERIES, category, context, evidence, fixtureResponse } from './tax-fixtures';

vi.mock('../app/lib/service-call', async original => ({ ...await original<typeof import('../app/lib/service-call')>(), serviceCall: vi.fn() }));
vi.mock('../app/lib/navigate', () => ({ goTo: vi.fn(), signInUrl: () => '/sign-in' }));
const categories = taxConfig('categories')!, classifications = taxConfig('classifications')!, rules = taxConfig('rules')!, rates = taxConfig('rates')!;
const wrap = (node: React.ReactNode) => render(<PermissionProvider permissions={[]}><DisplayConfigProvider config={{ timezone: 'Asia/Kolkata', currency: 'INR' }}>{node}</DisplayConfigProvider></PermissionProvider>);
const writes = () => vi.mocked(serviceCall).mock.calls.filter(([, request]) => ['POST', 'PATCH'].includes(request.method ?? 'GET'));
async function fillEvidence() {
  await userEvent.type(screen.getByRole('textbox', { name: 'Official source reference' }), evidence.source_reference);
  await userEvent.type(screen.getByRole('textbox', { name: 'Official document URL' }), evidence.source_url);
  await userEvent.type(screen.getByRole('textbox', { name: 'Document SHA-256' }), evidence.source_sha256);
}
async function fillCategory() {
  await userEvent.type(await screen.findByRole('textbox', { name: 'Code' }), 'NEW');
  await userEvent.type(screen.getByRole('textbox', { name: 'Name' }), 'New category');
}
beforeEach(() => {
  vi.clearAllMocks(); window.history.replaceState(null, '', '/');
  vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => fixtureResponse(request) as never);
});
describe('tax directories and forms', () => {
  it('links all four tax masters from the overview', () => {
    wrap(<TaxOverview canManage />);
    for (const key of ['categories', 'classifications', 'rules', 'rates']) expect(document.querySelector('a[href^="/tax/' + key + '"]')).not.toBeNull();
  });
  it.each([categories, classifications, rules, rates])('shows the native $title directory and supports retry', async config => {
    wrap(<TaxDirectory company={COMPANY} config={config} canManage canPublish />);
    expect(await screen.findByRole('table', { name: config.title + ' directory' })).toBeVisible();
    if (config.key === 'rules') {
      expect(screen.getByText(/Nil-rated, exempt and non-GST are separate treatments/)).toBeVisible();
      expect(screen.getByRole('columnheader', { name: 'Classification scope' })).toBeVisible();
      expect(screen.getByText('Specific HSN/SAC codes')).toBeVisible();
    }
    await waitFor(() => expect(screen.queryByRole('progressbar')).not.toBeInTheDocument());
    expect(screen.getByRole('link', { name: (config.dated ? 'Publish ' : 'New ') + config.singular })).toHaveAttribute('href', expect.stringContaining('/tax/' + config.key + '/new'));
  });
  it('creates a category with a verified receipt and a detail link', async () => {
    wrap(<TaxEditor company={COMPANY} config={categories} returnTo="/tax/categories?q=TEST" />); await fillCategory();
    await userEvent.click(screen.getByRole('button', { name: 'Create tax category' }));
    expect(await screen.findByText('Tax category created successfully.')).toBeVisible();
    expect(writes()[0]?.[1].body).toEqual({ code: 'NEW', name: 'New category' });
    expect(screen.getByRole('link', { name: 'View tax category' }).getAttribute('href')).toContain('returnTo=');
  });
  it('validates empty required fields and focuses the first invalid field', async () => {
    wrap(<TaxEditor company={COMPANY} config={categories} />);
    await userEvent.click(await screen.findByRole('button', { name: 'Create tax category' }));
    expect(await screen.findByText('Code is required.')).toBeVisible(); expect(writes()).toHaveLength(0);
    await waitFor(() => expect(screen.getByRole('textbox', { name: 'Code' })).toHaveFocus());
  });
  it('edits only name and status using the saved row version', async () => {
    wrap(<TaxEditor company={COMPANY} config={categories} id={CATEGORY} />);
    const name = await screen.findByRole('textbox', { name: 'Name' }); expect(screen.queryByRole('textbox', { name: 'Code' })).not.toBeInTheDocument();
    await userEvent.clear(name); await userEvent.type(name, 'Updated name');
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Active' }), 'false');
    await userEvent.click(screen.getByRole('button', { name: 'Save changes' }));
    expect(await screen.findByText('Tax category updated successfully.')).toBeVisible();
    expect(writes()[0]?.[1].body).toEqual({ name: 'Updated name', is_active: false, expected_version: category.row_version });
  });
  it('creates a rule with searchable category selection and official evidence', async () => {
    wrap(<TaxEditor company={COMPANY} config={rules} />);
    await userEvent.type(await screen.findByRole('textbox', { name: 'Code' }), 'RULE'); await userEvent.type(screen.getByRole('textbox', { name: 'Name' }), 'New rule');
    await userEvent.click(screen.getByRole('combobox', { name: 'Tax category' }));
    await userEvent.click(await screen.findByRole('option', { name: /Test category/ }));
    await fillEvidence(); await userEvent.click(screen.getByRole('button', { name: 'Create tax rule' }));
    expect(await screen.findByText('Tax rule created successfully.')).toBeVisible();
    expect(writes()[0]?.[1].body).toMatchObject({ tax_category_id: CATEGORY, tax_system: 'gst_in', jurisdiction: 'IN', item_kind: 'GOODS', treatment: 'TAXABLE', classification_scope: 'SPECIFIC' });
  }, 30000);
  it('checks HSN/SAC and evidence before reviewing a classification', async () => {
    wrap(<TaxEditor company={COMPANY} config={classifications} />);
    await userEvent.type(await screen.findByRole('textbox', { name: 'Code' }), '991234'); await userEvent.type(screen.getByRole('textbox', { name: 'Description' }), 'Test service');
    await fillEvidence(); await userEvent.click(screen.getByRole('button', { name: 'Review publication' }));
    expect(await screen.findByText('HSN requires 4, 6 or 8 digits outside chapter 99.')).toBeVisible(); expect(writes()).toHaveLength(0);
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Code system' }), 'SAC'); await userEvent.click(screen.getByRole('button', { name: 'Review publication' }));
    expect(await screen.findByText('Review tax publication')).toBeVisible();
    await userEvent.click(screen.getByRole('button', { name: 'Publish tax classification' }));
    expect(await screen.findByText('Tax classification published successfully.')).toBeVisible();
    expect(writes()[0]?.[1].body).toMatchObject({ code_system: 'SAC', item_kind: 'SERVICE', expected_generation: context.policy_generation, expected_source_version: context.source_version });
  }, 15000);
  it('previews a rate with exact component decimals before publication', async () => {
    wrap(<TaxEditor company={COMPANY} config={rates} seriesId={SERIES} />);
    await waitFor(() => expect(screen.getAllByRole('textbox', { name: 'Percentage' })).toHaveLength(2));
    await fillEvidence(); for (const field of screen.getAllByRole('textbox', { name: 'Percentage' })) await userEvent.type(field, '2.5000');
    await userEvent.click(screen.getByRole('button', { name: 'Review publication' }));
    expect(await screen.findByText('Review tax publication')).toBeVisible();
    expect(writes()[0]?.[1].path).toContain('/tax-rate-previews');
    await userEvent.click(screen.getByRole('button', { name: 'Publish tax rate' }));
    expect(await screen.findByText('Tax rate published successfully.')).toBeVisible();
    const body = writes().find(([, request]) => request.path.endsWith('/tax-rates'))?.[1].body as { components: { percentage: string }[] };
    expect(body.components.map(row => row.percentage)).toEqual(['2.5000', '2.5000']);
  }, 15000);
  it('retains and freezes an unconfirmed category save, then retries the exact key and body', async () => {
    let attempts = 0;
    vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => { if (request.method === 'POST' && request.path.endsWith('/tax-categories') && attempts++ === 0) throw { status: 503, message: 'Temporary failure' }; return fixtureResponse(request) as never; });
    wrap(<TaxEditor company={COMPANY} config={categories} />); await fillCategory(); await userEvent.click(screen.getByRole('button', { name: 'Create tax category' }));
    const retry = await screen.findByRole('button', { name: 'Retry same save' }); expect(screen.getByRole('textbox', { name: 'Name' })).toBeDisabled();
    await userEvent.click(retry); expect(await screen.findByText('Tax category created successfully.')).toBeVisible();
    expect(writes()[0]?.[1].key).toBe(writes()[1]?.[1].key); expect(writes()[0]?.[1].body).toEqual(writes()[1]?.[1].body);
  });
  it('allows correcting a server validation error', async () => {
    vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => { if (request.method === 'POST') throw { status: 422, message: 'Validation failed', fields: { name: 'Choose a different name.' } }; return fixtureResponse(request) as never; });
    wrap(<TaxEditor company={COMPANY} config={categories} />); await fillCategory(); await userEvent.click(screen.getByRole('button', { name: 'Create tax category' }));
    expect(await screen.findByText('Choose a different name.')).toBeVisible(); expect(screen.getByRole('textbox', { name: 'Name' })).toBeEnabled();
  });
  it('blocks company switching and guards breadcrumbs when a draft is unsaved', async () => {
    wrap(<TaxEditor company={COMPANY} config={categories} />); await fillCategory();
    const switching = new Event(BEFORE_COMPANY_CHANGE, { cancelable: true }); window.dispatchEvent(switching); expect(switching.defaultPrevented).toBe(true);
    await userEvent.click(screen.getByRole('link', { name: 'Tax masters' })); expect(await screen.findByRole('dialog')).toHaveTextContent('Discard unsaved changes?'); expect(goTo).not.toHaveBeenCalled();
  });
  it('refuses a wrong-company record response', async () => {
    vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => { const value = fixtureResponse(request); return request.path.endsWith('/' + CATEGORY) ? { ...value as object, company_id: RULE } as never : value as never; });
    wrap(<TaxEditor company={COMPANY} config={categories} id={CATEGORY} />); expect(await screen.findByText(/could not be verified for this company/)).toBeVisible(); expect(screen.queryByRole('button', { name: 'Save changes' })).not.toBeInTheDocument();
  });
  it('creates a rate series for a selected rule', async () => {
    wrap(<TaxSetup company={COMPANY} ruleId={RULE} />); const save = await screen.findByRole('button', { name: 'Create rate series' }); await waitFor(() => expect(save).toBeEnabled());
    await userEvent.click(save); expect(await screen.findByText('Rate series created.')).toBeVisible(); expect(screen.getByRole('link', { name: 'Publish the first rate' })).toHaveAttribute('href', expect.stringContaining('series_id='));
  });
  it('adds a supported classification applicability to a rule', async () => {
    wrap(<TaxSetup company={COMPANY} ruleId={RULE} applicability />);
    await userEvent.type(await screen.findByRole('textbox', { name: 'HSN code' }), '1234');
    const save = screen.getByRole('button', { name: 'Add applicability' }); await waitFor(() => expect(save).toBeEnabled()); await userEvent.click(save);
    expect(await screen.findByText('Classification applicability added.')).toBeVisible(); expect(writes()[0]?.[1].body).toEqual({ rule_id: RULE, code_system: 'HSN', code: '1234', match_kind: 'EXACT' });
  });
});
describe('tax details and future history actions', () => {
  it.each([categories, classifications, rules, rates])('shows $title details and a safe back link', async config => {
    const id = config === categories ? CATEGORY : config === rules ? RULE : config === rates ? RATE : CLASSIFICATION;
    wrap(<TaxDetail company={COMPANY} config={config} id={id} canManage canPublish returnTo={'/tax/' + config.key} />);
    expect(await screen.findByText('Tax record details')).toBeVisible(); expect(screen.getByRole('link', { name: 'Back to ' + config.title.toLowerCase() })).toHaveAttribute('href', '/tax/' + config.key);
  });
  it('withdraws only a future definition with a required reason', async () => {
    wrap(<TaxDetail company={COMPANY} config={classifications} id={CLASSIFICATION} canManage canPublish />);
    await userEvent.click(await screen.findByRole('button', { name: 'Tax record actions' })); await userEvent.click(screen.getByRole('menuitem', { name: /Withdraw future definition/ }));
    const dialog = screen.getByRole('dialog'); await userEvent.click(within(dialog).getByRole('button', { name: 'Withdraw definition' })); expect(await screen.findByText(/Enter a printable reason/)).toBeVisible(); expect(writes()).toHaveLength(0);
    await userEvent.type(screen.getByRole('textbox', { name: 'Reason for withdrawal' }), 'Incorrect future classification'); await userEvent.click(within(dialog).getByRole('button', { name: 'Withdraw definition' }));
    expect(await screen.findByText('Future definition withdrawn. Its publication history is retained.')).toBeVisible(); expect(writes()[0]?.[1].body).toMatchObject({ target_id: CLASSIFICATION, resource: 'tax_classification', expected_version: 4, expected_generation: 10 });
  });
  it('has no mutation actions for a read-only user', async () => {
    wrap(<TaxDetail company={COMPANY} config={classifications} id={CLASSIFICATION} canManage={false} canPublish={false} />); await screen.findByText('Tax record details'); expect(screen.queryByRole('button', { name: 'Tax record actions' })).not.toBeInTheDocument();
  });
});
