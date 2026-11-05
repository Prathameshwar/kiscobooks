import { act, fireEvent, render, screen, within, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { CompanyMasters } from '../app/components/CompanyMasters';
import { useProductMode } from '../app/components/ProductModeProvider';
import MastersPage from '../app/masters/page';
import { companyMasterGroups, companyMastersFor } from '../app/lib/company-masters';
import { flattenNavigation, navigationFor, navSections, sidebarCurrentHref } from '../app/nav';
import { masterReturn } from '../app/lib/master-navigation';
import { accountingBack, accountingBackLabel } from '../app/lib/accounting-configuration-resources';
import { taxReturn } from '../app/lib/tax-masters';
import { structureReturn } from '../app/lib/warehouse-structure';
import { attributeReturn } from '../app/lib/attribute-masters';
import { pricingReturn } from '../app/lib/pricing-masters';
import { pageContext } from '../app/lib/page-context';
import { companyContextFor, sessionFor } from './helpers';
import { masterRequest } from '../app/lib/catalog-master-api';
import { taxRequest } from '../app/lib/tax-api';
import { companyCall } from '../app/lib/company-api';
vi.mock('../app/lib/company-api', () => ({ companyCall: vi.fn() }));
vi.mock('../app/components/ProductModeProvider', async (original) => ({
  ...(await original<typeof import('../app/components/ProductModeProvider')>()),
  useProductMode: vi.fn(),
}));

vi.mock('../app/lib/page-context', () => ({ pageContext: vi.fn() }));
vi.mock('../app/lib/catalog-master-api', () => ({ masterRequest: vi.fn() }));
vi.mock('../app/lib/tax-api', () => ({ taxRequest: vi.fn() }));
vi.mock('../app/providers', () => ({ Providers: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/components/ConsoleShell', () => ({ ConsoleShell: ({ children }: { children: React.ReactNode }) => children }));
const id = '01990000-0000-7000-8000-000000000001';
const cards = companyMasterGroups.flatMap(group => group.items);
const productMode = (advanced: boolean) => ({
  company: id,
  data: { company_id: id, product_family_sku_enabled: advanced, row_version: 1, policy_generation: 8 },
  loading: false,
  failure: null,
  refresh: vi.fn(),
});
beforeEach(() => vi.mocked(useProductMode).mockReturnValue(productMode(true)));
beforeEach(() => { vi.mocked(companyCall).mockResolvedValue({ company_id: id, features: ['inventory', 'batch_tracking', 'serial_tracking'].map(feature_key => ({ feature_key, state: 'ENABLED' })) }); vi.mocked(masterRequest).mockReset(); vi.mocked(masterRequest).mockResolvedValue({ company_id: id, enabled: true, operational_ready: false }); vi.mocked(taxRequest).mockReset(); vi.mocked(taxRequest).mockResolvedValue({ company_id: id, country_code: 'IN', default_tax_system: 'gst_in' }); });
async function reader(keys = ['company.read', ...new Set(cards.map(item => item.permission))]) {
  const session = await sessionFor({ permissions: keys });
  session.company = { id, name: 'Company A' };
  session.grants = [{ scope_type: 'company', scope_id: id, permissions: keys, valid_from: '2000-01-01', valid_to: null }];
  return session;
}
it('defines core, manufacturing and stock masters without retired tracking pages', () => {
  expect(cards).toHaveLength(50); expect(new Set(cards.map(item => item.href)).size).toBe(50);
  expect(cards.find(item => item.href === '/accounting/opening')).toMatchObject({ permission: 'accounting.finance.read', label: 'Account and party openings' });
  for (const item of cards) expect(item.href).toMatch(/^\/(masters\/[a-z-]+|accounting\/[a-z-]+|tax\/[a-z-]+|inventory\/stock)$/);
  expect(cards.some(item => /departments|years|configuration|custom-fields/.test(item.href))).toBe(false);
});
it('renders all readable cards in shared responsive groups with a return to Masters', async () => {
  render(<CompanyMasters session={await reader()} context={companyContextFor()} />);
  expect(screen.getByRole('heading', { level: 1, name: 'Masters' })).toBeVisible();
  for (const card of cards) expect(await screen.findByRole('link', { name: card.label })).toHaveAttribute('href', card.href + '?returnTo=%2Fmasters');
  expect(document.querySelectorAll(".janso-action-card-grid")).toHaveLength(12);
  expect(document.querySelectorAll(".janso-action-card-grid--compact")).toHaveLength(12);
  expect(within(screen.getByRole('link', { name: 'Account heads' })).getByText('View account heads')).toBeVisible();
});
it('shows simple product cards according to the saved company product structure', async () => {
  vi.mocked(useProductMode).mockReturnValue(productMode(false));
  render(<CompanyMasters session={await reader()} context={companyContextFor()} />);
  await screen.findByRole('link', { name: 'Tax rates' });
  expect(screen.queryByRole('link', { name: 'Product families' })).not.toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Products' })).toHaveAttribute('href', '/masters/items?returnTo=%2Fmasters');
  expect(screen.queryByRole('link', { name: 'Products / SKUs' })).not.toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Product types' })).toBeVisible();
  expect(screen.getByRole('link', { name: 'Item groups' })).toBeVisible();
});
it.each(['loading', 'unavailable', 'no-provider', 'other-company'])(
  'hides family cards until selected-company settings are verified (%s)',
  async (state) => {
    const mode = productMode(true);
    vi.mocked(useProductMode).mockReturnValue(
      state === 'no-provider' ? null : state === 'other-company'
        ? { ...mode, company: 'other', data: { ...mode.data, company_id: 'other' } }
        : { ...mode, data: null, loading: state === 'loading',
            failure: state === 'unavailable' ? { status: 503, message: 'Settings unavailable' } : null },
    );
    render(<CompanyMasters session={await reader()} context={companyContextFor()} />);
    await screen.findByRole('link', { name: 'Tax rates' });
    expect(screen.queryByRole('link', { name: 'Product families' })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Brands' })).toBeVisible();
  },
);
it('updates family cards after a configuration change while retaining the master search', async () => {
  const session = await reader();
  const view = render(<CompanyMasters session={session} context={companyContextFor()} />);
  await screen.findByRole('link', { name: 'Tax rates' });
  fireEvent.change(screen.getByRole('searchbox', { name: 'Search masters' }), { target: { value: 'product' } });
  expect(screen.getByRole('link', { name: 'Product families' })).toBeVisible();
  vi.mocked(useProductMode).mockReturnValue(productMode(false));
  view.rerender(<CompanyMasters session={session} context={companyContextFor()} />);
  expect(screen.queryByRole('link', { name: 'Product families' })).not.toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Products' })).toBeVisible();
  expect(screen.getByRole('searchbox', { name: 'Search masters' })).toHaveValue('product');
  vi.mocked(useProductMode).mockReturnValue(productMode(true));
  view.rerender(<CompanyMasters session={session} context={companyContextFor()} />);
  expect(screen.getByRole('link', { name: 'Product families' })).toBeVisible();
});
it('filters cards by name or purpose, hides empty groups, and recovers after no matches', async () => {
  render(<CompanyMasters session={await reader()} context={companyContextFor()} />);
  fireEvent.change(screen.getByRole('searchbox', { name: 'Search masters' }), { target: { value: 'withholding' } });
  expect(screen.getByRole('link', { name: 'Withholding rates' })).toBeVisible();
  await waitFor(() => expect(screen.queryByRole('region', { name: 'Products and classification' })).not.toBeInTheDocument());
  fireEvent.change(screen.getByRole('searchbox', { name: 'Search masters' }), { target: { value: 'no master has this name' } });
  expect(await screen.findByText(/No masters match/)).toBeVisible();
  fireEvent.change(screen.getByRole('searchbox', { name: 'Search masters' }), { target: { value: '' } });
  expect(await screen.findByRole('link', { name: 'Brands' })).toBeVisible();
});
it.each(['company', 'tenant'] as const)('shows only readable masters with %s scope', async scope => {
  const session = await reader(['brand.read', 'accounting.party.read']); session.grants![0].scope_type = scope;
  render(<CompanyMasters session={session} context={companyContextFor()} />);
  expect(screen.getByRole('link', { name: 'Brands' })).toBeVisible();
  expect(screen.getByRole('link', { name: 'Parties / customers / suppliers' })).toBeVisible();
  expect(screen.queryByRole('link', { name: 'Ledger accounts' })).not.toBeInTheDocument();
  expect(screen.queryByRole('region', { name: 'Tax' })).not.toBeInTheDocument();
});
it.each(['expired', 'future', 'other-company', 'department', 'platform', 'missing'] as const)('denies master cards and menu for %s authority even with an admin role label', async reason => {
  const session = await reader(); session.role = 'Company Admin';
  if (reason === 'expired') session.grants![0].valid_to = '2000-01-01';
  if (reason === 'future') session.grants![0].valid_from = '2099-01-01';
  if (reason === 'other-company') session.grants![0].scope_id = 'other';
  if (reason === 'department' || reason === 'platform') session.grants![0].scope_type = reason;
  if (reason === 'missing') session.grants = [];
  render(<CompanyMasters session={session} context={companyContextFor()} />);
  expect(screen.getByRole('alert')).toHaveTextContent('No master read permissions');
  expect(companyMastersFor(session)).toEqual([]);
  expect(flattenNavigation(navigationFor(session).flatMap(section => section.items)).some(item => item.href === '/masters')).toBe(false);
});
it('asks for company selection instead of showing cards for an absent company', async () => {
  vi.mocked(useProductMode).mockReturnValue(null);
  const session = await reader(); session.company = { name: 'Select company' };
  render(<CompanyMasters session={session} context={companyContextFor()} />);
  expect(screen.getByRole('link', { name: 'See the companies you can open' })).toHaveAttribute('href', '/companies');
  expect(screen.queryByRole('link', { name: 'Brands' })).not.toBeInTheDocument();
});
it('places one Masters menu inside Administer without any submenu', async () => {
  const items = flattenNavigation(navigationFor(await reader()).flatMap(section => section.items));
  expect(items.filter(item => item.label === 'Masters')).toHaveLength(1);
  expect(items.find(item => item.href === '/masters')?.children).toBeUndefined();
  expect(items.some(item => item.href === '/inventory' || item.href === '/accounting' || item.href === '/tax')).toBe(false);
  expect(navSections.find(section => section.label === 'Books and Reports')!.items.some(item => item.href === '/masters')).toBe(false);
  expect(navSections.find(section => section.label === 'Administer')!.items[0]?.href).toBe('/masters');
});
it.each(['/masters', '/masters/brands/' + id, '/accounting/accounts', '/accounting/suppliers/' + id, '/tax/rates', '/inventory/products'])('keeps Masters selected on %s', async path => {
  expect(sidebarCurrentHref(navigationFor(await reader()).flatMap(section => section.items), path)).toBe('/masters');
});
it('preserves a safe Masters return through every existing master workflow', () => {
  for (const check of [masterReturn, accountingBack, taxReturn, structureReturn, attributeReturn, pricingReturn]) {
    expect(check('/masters')).toBe('/masters');
    expect(check('//outside.invalid/masters')).not.toBe('//outside.invalid/masters');
    expect(check('/masters?redirect=bad')).not.toBe('/masters?redirect=bad');
  }
  expect(accountingBackLabel('/masters')).toBe('masters');
});
it('resolves the protected page per request and propagates authentication failure', async () => {
  vi.mocked(pageContext).mockResolvedValue({ session: await reader(['unit.read']), context: companyContextFor() });
  render(await MastersPage()); expect(screen.getByRole('link', { name: 'Units' })).toBeVisible();
  vi.mocked(pageContext).mockRejectedValueOnce(new Error('Sign in required'));
  await expect(MastersPage()).rejects.toThrow('Sign in required');
});
it('hides India-specific tax cards and their section for a non-Indian company', async () => {
  vi.mocked(taxRequest).mockResolvedValue({ company_id: id, country_code: 'US', default_tax_system: 'none' });
  render(<CompanyMasters session={await reader()} context={companyContextFor()} />);
  await waitFor(() => expect(screen.queryByRole('region', { name: 'Tax' })).not.toBeInTheDocument());
  expect(screen.queryByRole('link', { name: 'Tax rates' })).not.toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Brands' })).toBeVisible();
});

it('hides GST masters when an Indian company has taxation disabled', async () => {
  vi.mocked(taxRequest).mockResolvedValue({ company_id: id, country_code: 'IN', default_tax_system: 'none' });
  render(<CompanyMasters session={await reader()} context={companyContextFor()} />);
  await waitFor(() => expect(screen.queryByRole('region', { name: 'Tax' })).not.toBeInTheDocument());
  expect(screen.queryByRole('link', { name: 'Tax rates' })).not.toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Brands' })).toBeVisible();
});
it('explains when a country-specific reader has no applicable masters', async () => {
  vi.mocked(taxRequest).mockResolvedValue({ company_id: id, country_code: 'US', default_tax_system: 'none' });
  render(<CompanyMasters session={await reader(['tax_rule.read'])} context={companyContextFor()} />);
  expect(await screen.findByText('No masters are applicable for this company.')).toBeVisible();
  expect(screen.queryByRole('searchbox', { name: 'Search masters' })).toBeVisible();
  expect(document.querySelector('.janso-action-card')).toBeNull();
});
it('keeps tax cards disabled on configuration failure and supports retry', async () => {
  vi.mocked(taxRequest).mockRejectedValueOnce({ status: 503, message: 'Unavailable' });
  render(<CompanyMasters session={await reader()} context={companyContextFor()} />);
  fireEvent.click(await screen.findByRole('button', { name: 'Retry tax configuration' }));
  expect(await screen.findByRole('link', { name: 'Tax rates' })).toBeVisible();
});
it('rejects configuration from a different company and does not infer country from tenant defaults', async () => {
  vi.mocked(taxRequest).mockResolvedValue({ company_id: 'other', country_code: 'IN' });
  render(<CompanyMasters session={await reader()} context={companyContextFor()} />);
  expect(await screen.findByRole('button', { name: 'Retry tax configuration' })).toBeVisible();
  expect(screen.queryByRole('link', { name: 'Tax rates' })).not.toBeInTheDocument();
});

it('hides the BOM card when its verified company capability is off', async () => {
  vi.mocked(masterRequest).mockResolvedValue({ company_id: id, enabled: false, operational_ready: false });
  render(<CompanyMasters session={await reader()} context={companyContextFor()} />);
  await waitFor(() => expect(screen.queryByText('Checking BOM configuration')).not.toBeInTheDocument());
  expect(screen.queryByRole('link', { name: 'Bills of materials' })).not.toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Manufacturing operations' })).toBeVisible();
});
it('keeps a BOM configuration failure disabled and supports retry', async () => {
  vi.mocked(masterRequest).mockRejectedValueOnce({ status: 503, message: 'Unavailable' });
  render(<CompanyMasters session={await reader()} context={companyContextFor()} />);
  fireEvent.click(await screen.findByRole('button', { name: 'Retry BOM configuration' }));
  expect(await screen.findByRole('link', { name: 'Bills of materials' })).toBeVisible();
});

it.each(['loading', 'disabled', 'unavailable', 'wrong-company'])('hides promotion cards when configuration is %s', async state => {
  vi.mocked(masterRequest).mockImplementation(async request => {
    if (request.path?.endsWith('/promotion-stack-policies/authoring-context')) {
      if (state === 'loading') return new Promise(() => {});
      if (state === 'unavailable') throw { status: 503, message: 'Unavailable' };
      return { company_id: state === 'wrong-company' ? 'other' : id, enabled: state !== 'disabled', operational_ready: false } as never;
    }
    return { company_id: id, enabled: true, operational_ready: false } as never;
  });
  const session = await reader();
  await act(async () => { render(<CompanyMasters session={session} context={companyContextFor()} />); });
  expect(screen.queryByRole('region', { name: 'Sales promotion definitions' })).not.toBeInTheDocument();
  expect(screen.queryByText('Promotion stacking policies')).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Retry promotion configuration' })).not.toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Brands' })).toBeVisible();
});
