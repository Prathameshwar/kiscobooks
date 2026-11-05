import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { PricingDirectory } from '../app/platform/pricing/PricingDirectory';
import { PricingEditor } from '../app/platform/pricing/PricingEditor';
import { allowedPlatformRequest } from '../app/lib/platform-request';

const { call } = vi.hoisted(() => ({ call: vi.fn() }));
vi.mock('../app/lib/platform-api', async () => ({ ...await vi.importActual('../app/lib/platform-api'), platformCall: call }));
const id = '0199aabb-0000-7000-8000-000000000001';
const price = { id, version: 1, code: 'platform-1y', name: 'Platform · 1 year', category: 'platform', term_months: 12, unit: 'none', monthly_fee: '449', unit_price: '0', output_unit_price: '0', tax_percent: '18', fx_inr_per_usd: '94.8228', description: 'Annual plan', provider: '', model: '', is_active: true, deleted_at: null,
  prices: [{ currency: 'INR', monthly_fee: '449.00', unit_price: '0', output_unit_price: '0', term_net: '5388', term_tax: '969.84', term_total: '6357.84' }, { currency: 'USD', monthly_fee: '5.69', unit_price: '0', output_unit_price: '0', term_net: '68.28', term_tax: '12.29', term_total: '80.57' }] };
const page = { items: [{ ...price, usd_monthly_fee: '5.69', usd_unit_price: '0' }], page: { has_more: false, next_cursor: null } };
beforeEach(() => { call.mockReset(); sessionStorage.clear(); call.mockImplementation((path: string, method = 'GET') => Promise.resolve(method === 'GET' && path.includes('?') ? page : price)); });

it('shows real INR/USD prices and subscription terms without float conversion', async () => {
  render(<PricingDirectory scope="test" />);
  expect(await screen.findByText('Platform · 1 year')).toBeInTheDocument();
  expect(screen.getByText('449.00 INR')).toBeInTheDocument();
  expect(screen.getByText('5.69 USD')).toBeInTheDocument();
  expect(screen.getByText(/12 months, billed upfront/)).toBeInTheDocument();
  await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Offering type' }), 'sms');
  await waitFor(() => expect(call.mock.lastCall?.[0]).toContain('category=sms'));
});
it('shows loading and clear load failures with a working refresh', async () => {
  call.mockRejectedValueOnce({ status: 503, message: 'Catalog unavailable' }); render(<PricingDirectory scope="test" />);
  expect(await screen.findByRole('alert')).toHaveTextContent('Catalog unavailable');
  await userEvent.click(screen.getByRole('button', { name: 'Refresh prices' }));
  expect(await screen.findByText('Platform · 1 year')).toBeInTheDocument();
});
it('adds an offering with decimal strings and API-derived currencies', async () => {
  render(<PricingEditor id="new" scope="test" onClose={vi.fn()} onSaved={vi.fn()} />);
  await userEvent.type(screen.getByRole('textbox', { name: 'Offering code' }), 'custom-1y');
  await userEvent.type(screen.getByRole('textbox', { name: 'Offering name' }), 'Custom annual');
  await userEvent.type(screen.getByRole('spinbutton', { name: 'Monthly fee (INR)' }), '449');
  await userEvent.click(screen.getByRole('button', { name: 'Save pricing' }));
  await waitFor(() => expect(call).toHaveBeenCalledWith('/v1/platform/pricing', 'POST', expect.objectContaining({ code: 'custom-1y', monthly_fee: '449', unit: 'none', term_months: 12 })));
  expect(await screen.findByText('Saved price · version 1')).toBeInTheDocument();
});
it('saves the loaded version and allows deactivation', async () => {
  render(<PricingEditor id={id} scope="test" onClose={vi.fn()} onSaved={vi.fn()} />);
  await screen.findByDisplayValue('449');
  expect(screen.getByRole('textbox', { name: 'Offering code' })).toBeDisabled();
  await userEvent.click(screen.getByRole('checkbox', { name: 'Active for new subscriptions' }));
  await userEvent.click(screen.getByRole('button', { name: 'Save pricing' }));
  await waitFor(() => expect(call).toHaveBeenCalledWith('/v1/platform/pricing/' + id, 'PATCH', expect.objectContaining({ expected_version: 1, is_active: false })));
});
it('renders LLM model and separate input/output token pricing', async () => {
  render(<PricingEditor id="new" scope="test" onClose={vi.fn()} onSaved={vi.fn()} />);
  await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Offering category' }), 'llm');
  expect(screen.getByRole('textbox', { name: 'AI provider' })).toBeRequired();
  expect(screen.getByRole('textbox', { name: 'Model identifier' })).toBeRequired();
  expect(screen.getByRole('spinbutton', { name: 'INR per 1,000 input tokens' })).toBeInTheDocument();
  expect(screen.getByRole('spinbutton', { name: 'INR per 1,000 output tokens' })).toBeInTheDocument();
  expect(screen.getByRole('combobox', { name: 'Billing term' })).toBeDisabled();
});
it('retains edits on conflict and provides reauthentication for a stale session', async () => {
  render(<PricingEditor id={id} scope="test" onClose={vi.fn()} onSaved={vi.fn()} />); await screen.findByDisplayValue('449');
  await userEvent.clear(screen.getByRole('spinbutton', { name: 'Monthly fee (INR)' }));
  await userEvent.type(screen.getByRole('spinbutton', { name: 'Monthly fee (INR)' }), '499');
  call.mockRejectedValueOnce({ status: 409, message: 'Reload before saving' });
  await userEvent.click(screen.getByRole('button', { name: 'Save pricing' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Reload before saving');
  expect(screen.getByRole('spinbutton', { name: 'Monthly fee (INR)' })).toHaveValue(499);
  call.mockRejectedValueOnce({ status: 403, code: 'platform_reauthentication_required', message: 'Sign in again' });
  await userEvent.click(screen.getByRole('button', { name: 'Save pricing' }));
  expect(await screen.findByRole('link', { name: 'Sign in again' })).toHaveAttribute('href', expect.stringContaining('returnTo='));
});
it('requires confirmation for deletion and retains an inactive restoration', async () => {
  call.mockImplementation((path: string) => Promise.resolve(path.endsWith('/delete') ? { ...price, version: 2, is_active: false, deleted_at: '2026-10-23T00:00:00Z' } : path.endsWith('/restore') ? { ...price, version: 3, is_active: false } : price));
  render(<PricingEditor id={id} scope="test" onClose={vi.fn()} onSaved={vi.fn()} />); await screen.findByDisplayValue('449');
  await userEvent.click(screen.getByRole('button', { name: 'Delete offering' }));
  const dialog = screen.getByRole('dialog', { name: 'Delete this offering?' });
  await userEvent.click(within(dialog).getByRole('button', { name: 'Delete offering' }));
  expect(await screen.findByRole('button', { name: 'Restore offering' })).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Save pricing' })).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Restore offering' }));
  await userEvent.click(within(screen.getByRole('dialog', { name: 'Restore this offering?' })).getByRole('button', { name: 'Restore offering' }));
  expect(await screen.findByRole('checkbox', { name: 'Active for new subscriptions' })).not.toBeChecked();
});
it('loads immutable price history only when requested', async () => {
  call.mockImplementation((path: string) => Promise.resolve(path.includes('/revisions') ? { items: [{ id, version: 1, created_at: '2026-10-23T00:00:00Z', snapshot: price }], page: page.page } : price));
  render(<PricingEditor id={id} scope="test" onClose={vi.fn()} onSaved={vi.fn()} />); await screen.findByDisplayValue('449');
  expect(call).toHaveBeenCalledTimes(1);
  await userEvent.click(screen.getByRole('button', { name: 'Show price history' }));
  expect(await screen.findByRole('table', { name: 'Price revisions' })).toBeInTheDocument();
});
it('restricts the pricing proxy to catalog endpoints and allowlisted query parameters', () => {
  expect(allowedPlatformRequest('GET', '/v1/platform/pricing?status=all&limit=50')).toBe(true);
  expect(allowedPlatformRequest('PATCH', '/v1/platform/pricing/' + id)).toBe(true);
  expect(allowedPlatformRequest('POST', '/v1/platform/pricing/' + id + '/delete')).toBe(true);
  for (const path of ['/v1/platform/pricing?tenant_id=x', '/v1/platform/pricing/' + id + '/delete?x=1', '/v1/platform/pricing/../../tenants', '/v1/platform/pricing/' + id + '/sql']) expect(allowedPlatformRequest('POST', path)).toBe(false);
});
it('prevents duplicate writes while a save is pending', async () => {
  render(<PricingEditor id={id} scope="pending" onClose={vi.fn()} onSaved={vi.fn()} />); await screen.findByDisplayValue('449');
  call.mockReturnValue(new Promise(() => {}));
  const button = screen.getByRole('button', { name: 'Save pricing' });
  await userEvent.dblClick(button);
  expect(call.mock.calls.filter(([, method]) => method === 'PATCH')).toHaveLength(1);
  expect(screen.getByRole('button', { name: 'Saving pricing…' })).toBeDisabled();
});
it('keeps the recovered draft version so a concurrent server edit cannot be overwritten', async () => {
  const draft = { code: price.code, name: 'Recovered name', category: 'platform', description: '', term_months: '12', monthly_fee: '479', unit_price: '0', output_unit_price: '0', tax_percent: '18', fx_inr_per_usd: '94.8228', provider: '', model: '', is_active: 'true', version: '1' };
  sessionStorage.setItem('janso-platform-draft:recovered:pricing:' + id, JSON.stringify({ at: Date.now(), key: 'recovered-key', draft }));
  call.mockResolvedValue({ ...price, version: 2 });
  render(<PricingEditor id={id} scope="recovered" onClose={vi.fn()} onSaved={vi.fn()} />);
  await screen.findByDisplayValue('Recovered name'); await screen.findByText('Saved price · version 2');
  await userEvent.click(screen.getByRole('button', { name: 'Save pricing' }));
  await waitFor(() => expect(call).toHaveBeenCalledWith('/v1/platform/pricing/' + id, 'PATCH', expect.objectContaining({ expected_version: 1, monthly_fee: '479' })));
});
