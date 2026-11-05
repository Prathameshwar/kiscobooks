import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { CompanyGstSettings } from '../app/components/CompanyGstSettings';
import { companyCall } from '../app/lib/company-api';
import { BEFORE_COMPANY_CHANGE } from '../app/lib/use-unsaved-changes';
import { goTo } from '../app/lib/navigate';
import { renderWithProviders, sessionFor } from './helpers';

vi.mock('../app/lib/company-api', () => ({ companyCall: vi.fn(), companyFailure: (value: unknown) => value }));
vi.mock('../app/lib/navigate', async importOriginal => ({ ...await importOriginal<typeof import('../app/lib/navigate')>(), goTo: vi.fn() }));
const company = '01990000-0000-7000-8000-000000000001';
const other = '01990000-0000-7000-8000-000000000002';
const configuration = '/companies/' + company + '/configuration?returnTo=%2Fsettings';
let profile: Record<string, unknown>, manage: boolean;
beforeEach(() => {
  vi.clearAllMocks(); manage = true;
  profile = { id: company, display_name: 'Acme Manufacturing', country_code: 'IN', default_tax_system: 'gst_in', status: 'active' };
  vi.mocked(companyCall).mockImplementation(async (_service, path) => {
    if (path.endsWith('/gst-registration-setup')) return { country_code: 'IN', default_tax_system: 'gst_in', can_manage: manage, states: [{ code: 'MH', name: 'Maharashtra' }], regimes: { regular: 'Regular taxpayer' }, create_schema: { properties: {} } } as never;
    if (path.endsWith('/gst-outward-profile-setup')) return { can_manage: manage, create_schema: { properties: {} } } as never;
    if (path.includes('?')) return { items: [], page: { next_cursor: null } } as never;
    return profile as never;
  });
});
async function mount(permissions = ['company.read', 'company.tax_registration.manage', 'report.read'], selected = company, returnTo = configuration) {
  const session = await sessionFor({ permissions }); session.company = { id: selected, name: 'Company' };
  session.grants = [{ scope_type: 'company', scope_id: company, permissions, valid_from: '2020-01-01', valid_to: null }];
  return renderWithProviders(<CompanyGstSettings session={session} companyId={company} returnTo={returnTo} />);
}
it('opens the two GST histories and returns to the originating configuration', async () => {
  await mount();
  await screen.findByRole('table', { name: 'Dated GST outward reporting profiles' });
  expect(screen.getByRole('heading', { level: 1, name: 'GST settings' })).toBeVisible();
  expect(screen.getByText('Acme Manufacturing', { selector: '.janso-page-header__meta *' })).toBeVisible();
  expect(screen.getByRole('table', { name: 'Company GST registrations' })).toBeVisible();
  expect(screen.getByRole('link', { name: 'Back to company configuration' })).toHaveAttribute('href', configuration);
  expect(screen.queryByRole('table', { name: 'Company features' })).not.toBeInTheDocument();
});
it.each(['vat_gb', 'none', undefined])('explains unavailable GST setup for %s without fetching GST histories', async tax => {
  profile.default_tax_system = tax;
  await mount(); await screen.findByText(/GST settings are available for companies using GST/);
  expect(companyCall).not.toHaveBeenCalledWith('identity', expect.stringContaining('/gst-registration-setup'), expect.anything());
});
it('does not read when the named company is not permitted', async () => {
  await mount([]); expect(screen.getByText('Company read access is required for this company.')).toBeVisible();
  expect(companyCall).not.toHaveBeenCalled();
});
it('rejects a mismatched company response before loading statutory records', async () => {
  profile.id = other; await mount(); await screen.findByText('The company response could not be verified. Reload GST settings.');
  expect(screen.queryByRole('table')).not.toBeInTheDocument();
});
it.each([401, 403, 422, 500])('shows company load failure %s and its recovery action', async status => {
  vi.mocked(companyCall).mockRejectedValue({ status, message: 'Company unavailable' });
  await mount(); await screen.findByText('Company unavailable');
  if (status === 401) expect(screen.getByRole('link', { name: 'Sign in again' }).getAttribute('href')).toContain('returnTo=');
  else if (status === 403) expect(screen.queryByRole('button', { name: 'Reload GST settings' })).not.toBeInTheDocument();
  else expect(screen.getByRole('button', { name: 'Reload GST settings' })).toBeEnabled();
});
it('keeps reports hidden for a different selected company and management hidden for readers', async () => {
  manage = false; await mount(['company.read', 'report.read'], other);
  await screen.findByRole('table', { name: 'Dated GST outward reporting profiles' });
  expect(screen.queryByRole('button', { name: 'Add GST registration' })).not.toBeInTheDocument();
  expect(screen.queryByRole('link', { name: 'GST filing preferences and GSTR-3B' })).not.toBeInTheDocument();
});
it('protects drafts when refreshing, leaving through reports, or changing company', async () => {
  await mount(); fireEvent.click(await screen.findByRole('button', { name: 'Add GST registration' }));
  fireEvent.change(screen.getByLabelText('GSTIN'), { target: { value: '27AAAPA1234A1ZT' } });
  expect(screen.getByRole('button', { name: 'Refresh GST settings' })).toBeDisabled();
  expect(window.dispatchEvent(new Event(BEFORE_COMPANY_CHANGE, { cancelable: true }))).toBe(false);
  fireEvent.click(screen.getByRole('link', { name: 'GST filing preferences and GSTR-3B' }));
  const dialog = screen.getByRole('dialog', { name: 'Discard unsaved changes?' });
  expect(dialog).toBeVisible(); fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));
  expect(screen.getByLabelText('GSTIN')).toHaveValue('27AAAPA1234A1ZT');
});
it('preserves an accounting origin and rejects an external return', async () => {
  const view = await mount(undefined, company, '/companies/' + company + '/configuration?returnTo=%2Faccounting%2Fwithholding-sections%3Fstatus%3DACTIVE');
  await screen.findByRole('table', { name: 'Dated GST outward reporting profiles' });
  expect(screen.getByRole('link', { name: 'Back to company configuration' }).getAttribute('href')).toContain('returnTo=%2Faccounting%2Fwithholding-sections');
  view.unmount(); await mount(undefined, company, 'https://outside.invalid/');
  expect(screen.getByRole('link', { name: 'Back to company configuration' }).getAttribute('href')).toMatch(/^\/companies\//);
});

it('reloads after a recoverable company read failure', async () => {
  const answer = vi.mocked(companyCall).getMockImplementation()!;
  vi.mocked(companyCall).mockRejectedValueOnce({ status: 500, message: 'Temporary read failure' });
  await mount(); fireEvent.click(await screen.findByRole('button', { name: 'Reload GST settings' }));
  vi.mocked(companyCall).mockImplementation(answer);
  await screen.findByRole('table', { name: 'Dated GST outward reporting profiles' });
});

it('blocks navigation and refresh during a registration save and releases them after success', async () => {
  const answer = vi.mocked(companyCall).getMockImplementation()!; let finish!: (value: unknown) => void;
  vi.mocked(companyCall).mockImplementation((service, path, request) => request?.method === 'POST' ? new Promise(resolve => { finish = resolve; }) : answer(service, path, request));
  await mount(); fireEvent.click(await screen.findByRole('button', { name: 'Add GST registration' }));
  fireEvent.change(screen.getByLabelText('GSTIN'), { target: { value: '27AAAPA1234A1ZT' } });
  fireEvent.change(screen.getByLabelText('GST registration state / UT'), { target: { value: 'MH' } });
  fireEvent.change(screen.getByLabelText('GST regime'), { target: { value: 'regular' } });
  fireEvent.change(screen.getByLabelText('GST registration valid from'), { target: { value: '2026-04-01' } });
  fireEvent.submit(screen.getByRole('form', { name: 'Add GST registration' }));
  expect(screen.getByRole('button', { name: 'Refresh GST settings' })).toBeDisabled();
  fireEvent.click(screen.getByRole('link', { name: 'Back to company configuration' }));
  expect(screen.queryByRole('dialog', { name: 'Discard unsaved changes?' })).not.toBeInTheDocument();
  expect(window.dispatchEvent(new Event(BEFORE_COMPANY_CHANGE, { cancelable: true }))).toBe(false);
  finish({ id: company }); await screen.findByText(/GST registration saved/);
  await waitFor(() => expect(screen.getByRole('button', { name: 'Refresh GST settings' })).toBeEnabled());
});

it('leaves after confirming a discard without another browser unload warning', async () => {
  await mount(); fireEvent.click(await screen.findByRole('button', { name: 'Add GST registration' }));
  fireEvent.change(screen.getByLabelText('GSTIN'), { target: { value: '27AAAPA1234A1ZT' } });
  fireEvent.click(screen.getByRole('link', { name: 'Back to company configuration' }));
  fireEvent.click(within(screen.getByRole('dialog', { name: 'Discard unsaved changes?' })).getByRole('button', { name: 'Discard and leave' }));
  expect(goTo).toHaveBeenCalled();
  expect(window.dispatchEvent(new Event('beforeunload', { cancelable: true }))).toBe(true);
});
