import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { AccountingConfigurationEditor } from '../app/components/AccountingConfigurationEditor';
import { accountingResource } from '../app/lib/accounting-configuration-resources';
import { allowedProductRequest } from '../app/lib/product-request-policy';
import { serviceCall } from '../app/lib/service-call';
import { COMPANY, PARTY, form, response } from './accounting-configuration-fixtures';

vi.mock('../app/lib/service-call', async original => ({ ...await original<typeof import('../app/lib/service-call')>(), serviceCall: vi.fn() }));
vi.mock('../app/lib/navigate', () => ({ goTo: vi.fn(), signInUrl: () => '/signin' }));
const currencyNotice = 'New currency defaults use the company base currency: INR.';
const metadata = () => {
  const result = form('party-credit-policies');
  result.notices = [currencyNotice];
  const currency = result.fields.find(field => field.key === 'currency')!;
  currency.initial = 'INR';
  currency.control.reference_filters = { company_currency: 'true' };
  return result;
};
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(serviceCall).mockImplementation(async (_, request) => {
    if (!allowedProductRequest(request.service ?? 'accounting', request.method ?? 'GET', request.path))
      throw { status: 422, message: 'Unsupported product field request' };
    return (request.path.includes('/field-set') ? metadata() : response(request.path, request.method, request.body)) as never;
  });
});
function editor(party = PARTY) {
  return render(<AccountingConfigurationEditor company={COMPANY} config={accountingResource('party-credit-policies')!}
    prefills={{ party_id: party }} returnTo={'/accounting/parties/' + PARTY} />);
}

it('loads the company default and browses currencies through the gateway policy', async () => {
  editor();
  const currency = await screen.findByRole('combobox', { name: 'Currency' });
  await waitFor(() => expect(currency).toHaveValue('Indian rupee'));
  await userEvent.click(currency);
  expect(await screen.findByRole('option', { name: /Indian rupee/ })).toBeVisible();
  const paths = vi.mocked(serviceCall).mock.calls.map(([, request]) => request.path);
  expect(paths).toContain(`/v1/companies/${COMPANY}/configuration/options/currencies?company_currency=true&value=INR&limit=1`);
  expect(paths).toContain(`/v1/companies/${COMPANY}/configuration/options/currencies?company_currency=true&limit=50`);
  expect(screen.queryByText('Unsupported product field request')).not.toBeInTheDocument();
});

it('collapses informational banners into one small guidance line and keeps the party locked', async () => {
  const { container } = editor();
  const summary = await screen.findByText('Credit policy guidance · Party fixed');
  expect(summary).toHaveClass('janso-fine');
  expect(screen.queryByText('Review and maintain credit policies for the current company.')).not.toBeInTheDocument();
  expect(container.querySelectorAll('.janso-notice')).toHaveLength(0);
  expect(screen.getByText(currencyNotice)).not.toBeVisible();
  expect(screen.getByRole('combobox', { name: 'Party' })).toBeDisabled();
  await userEvent.click(summary);
  expect(screen.getByText(currencyNotice)).toBeVisible();
  expect(screen.getByText(/Once an interval takes effect/)).toBeVisible();
  expect(screen.getByRole('link', { name: 'Back to party' })).toHaveAttribute('href', '/accounting/parties/' + PARTY);
});

it('keeps a mismatched party warning visible and prevents creation', async () => {
  editor(COMPANY);
  expect(await screen.findByText(/The party context does not match/)).toBeVisible();
  expect(screen.getByRole('button', { name: 'Create credit policy' })).toBeDisabled();
});
