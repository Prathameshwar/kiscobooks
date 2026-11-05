import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import {
  AccountingExchangeDetail,
  AccountingExchangeDirectory,
  AccountingExchangeEditor,
} from '../app/components/AccountingExchangeRates';
import { AccountingConfigurationDetail } from '../app/components/AccountingConfigurationDetail';
import {
  exchangeCandidate,
  exactExchangeRate,
  verifyExchangeContext,
  verifyExchangeQuote,
} from '../app/lib/accounting-exchange-rates';
import {
  accountingBody,
  accountingInitial,
} from '../app/lib/accounting-configuration';
import { accountingResource } from '../app/lib/accounting-configuration-resources';
import { allowedAccountingConfigurationRequest as allowed } from '../app/lib/accounting-configuration-policy';
import { serviceCall } from '../app/lib/service-call';
import { goTo } from '../app/lib/navigate';
import {
  COMPANY,
  ID,
  PARTY,
  form,
  record,
  response,
  page,
} from './accounting-configuration-fixtures';
vi.mock('../app/lib/service-call', async (original) => ({
  ...(await original<typeof import('../app/lib/service-call')>()),
  serviceCall: vi.fn(),
}));
vi.mock('../app/lib/navigate', () => ({
  goTo: vi.fn(),
  signInUrl: () => '/signin',
}));
const context = {
  company_id: COMPANY,
  base_currency: 'INR',
  allowed_currencies: ['USD', 'EUR'],
  multi_currency: true,
};
const quote = {
  id: ID,
  company_id: COMPANY,
  row_version: 1,
  from_currency: 'USD',
  to_currency: 'INR',
  purpose: 'ACCOUNTING' as const,
  effective_date: '2030-01-01',
  rate: '83.123456789012',
  source_kind: 'MANUAL' as const,
  source_reference: 'Reviewed bank quotation',
  source_sha256: 'a'.repeat(64),
  status: 'CANDIDATE' as const,
  created_by: PARTY,
  approved_by: null,
  approved_at: null,
  approval_reason: null,
  withdrawn_by: null,
  withdrawn_at: null,
  withdrawal_reason: null,
};
const writes = () =>
  vi
    .mocked(serviceCall)
    .mock.calls.filter(([, request]) => request.method === 'POST');
beforeEach(() => {
  vi.clearAllMocks();
  window.history.replaceState(null, '', '/accounting');
  vi.mocked(serviceCall).mockImplementation(async (_, request) => {
    if (!request.path.includes('/exchange-rates'))
      return response(request.path, request.method, request.body) as never;
    if (request.path.endsWith('/context')) return context as never;
    if (request.path.endsWith('/approve'))
      return {
        ...quote,
        status: 'APPROVED',
        row_version: 2,
        approval_reason: (request.body as { reason: string }).reason,
      } as never;
    if (request.path.endsWith('/withdraw'))
      return { ...quote, status: 'WITHDRAWN', row_version: 3 } as never;
    if (
      request.path.includes('/quotes/') ||
      request.path.endsWith('/candidates')
    )
      return quote as never;
    return { items: [quote], page } as never;
  });
});
it.each([
  '0',
  '-1',
  '1e2',
  'NaN',
  '1.1234567890123',
  '1000000000000000',
  83.125,
])('rejects invalid exact FX rate %s', (value) =>
  expect(exactExchangeRate(value)).toBe(false),
);
it('keeps all twelve decimals and restricts the currency pair and source', () => {
  const values = {
    from_currency: 'USD',
    purpose: 'GST_GOODS',
    effective_date: '2030-01-01',
    rate: '83.123456789012',
    source_reference: 'Official Customs source',
  };
  expect(exchangeCandidate(values, context)).toEqual({
    body: { ...values, to_currency: 'INR', source_kind: 'CUSTOMS' },
    errors: {},
  });
  expect(
    exchangeCandidate({ ...values, from_currency: 'GBP' }, context).errors
      .from_currency,
  ).toBeTruthy();
  expect(() =>
    verifyExchangeContext({ ...context, company_id: PARTY }, COMPANY),
  ).toThrow();
  expect(() =>
    verifyExchangeQuote({ ...quote, company_id: PARTY }, COMPANY, ID),
  ).toThrow();
});
it('validates the form and recovers one exact candidate after a lost response', async () => {
  const original = vi.mocked(serviceCall).getMockImplementation()!;
  let fail = true;
  vi.mocked(serviceCall).mockImplementation(async (...args) => {
    if (args[1].path.endsWith('/candidates') && fail) {
      fail = false;
      throw { status: 503, message: 'Connection lost' };
    }
    return original(...args);
  });
  render(<AccountingExchangeEditor company={COMPANY} returnTo="/settings" />);
  await userEvent.click(
    await screen.findByRole('button', { name: 'Create exchange rate' }),
  );
  expect(await screen.findByText(/positive exact rate/)).toBeVisible();
  expect(writes()).toHaveLength(0);
  await userEvent.selectOptions(
    screen.getByRole('combobox', { name: 'From currency' }),
    'USD',
  );
  await userEvent.type(screen.getByLabelText('Effective date'), '2030-01-01');
  await userEvent.type(
    screen.getByRole('textbox', { name: 'Exchange rate' }),
    quote.rate,
  );
  await userEvent.type(
    screen.getByRole('textbox', { name: 'Source reference' }),
    quote.source_reference,
  );
  await userEvent.click(
    screen.getByRole('button', { name: 'Create exchange rate' }),
  );
  expect(
    await screen.findByRole('button', { name: 'Retry same save' }),
  ).toBeVisible();
  expect(screen.getByRole('textbox', { name: 'Exchange rate' })).toBeDisabled();
  await userEvent.click(
    screen.getByRole('button', { name: 'Retry same save' }),
  );
  await waitFor(() =>
    expect(goTo).toHaveBeenCalledWith(
      `/accounting/exchange-rates/${ID}?returnTo=%2Fsettings`,
    ),
  );
  expect(writes()).toHaveLength(2);
  expect(writes()[0][1].key).toBe(writes()[1][1].key);
  expect(writes()[0][1].body).toEqual(writes()[1][1].body);
  expect(writes()[0][1].body).toMatchObject({
    rate: quote.rate,
    to_currency: 'INR',
  });
});
it('blocks the maker from approving their own candidate', async () => {
  render(
    <AccountingExchangeDetail
      company={COMPANY}
      id={ID}
      userId={PARTY}
      canManage
    />,
  );
  await userEvent.click(
    await screen.findByRole('button', { name: 'Quote actions' }),
  );
  expect(
    screen.getByRole('menuitem', { name: /Approve quote/ }),
  ).toHaveAttribute('aria-disabled', 'true');
  expect(writes()).toHaveLength(0);
  expect(screen.getByText(quote.rate)).toBeVisible();
});
it('requires a review reason and retains the version and key on recovery', async () => {
  const original = vi.mocked(serviceCall).getMockImplementation()!;
  let fail = true;
  vi.mocked(serviceCall).mockImplementation(async (...args) => {
    if (args[1].path.endsWith('/approve') && fail) {
      fail = false;
      throw { status: 503, message: 'Review result unconfirmed' };
    }
    return original(...args);
  });
  render(
    <AccountingExchangeDetail
      company={COMPANY}
      id={ID}
      userId={ID}
      canManage
    />,
  );
  await userEvent.click(
    await screen.findByRole('button', { name: 'Quote actions' }),
  );
  await userEvent.click(
    screen.getByRole('menuitem', { name: 'Approve quote' }),
  );
  await userEvent.click(
    within(screen.getByRole('dialog')).getByRole('button', {
      name: 'Approve quote',
    }),
  );
  expect(await screen.findByText(/review reason between/)).toBeVisible();
  expect(writes()).toHaveLength(0);
  await userEvent.type(
    screen.getByRole('textbox', { name: 'Review reason' }),
    'Independent source review',
  );
  await userEvent.click(
    within(screen.getByRole('dialog')).getByRole('button', {
      name: 'Approve quote',
    }),
  );
  await screen.findByRole('button', { name: 'Retry same review' });
  await userEvent.click(
    within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancel' }),
  );
  await userEvent.click(
    screen.getByRole('button', { name: 'Recover same review' }),
  );
  expect(screen.getByRole('textbox', { name: 'Review reason' })).toHaveValue(
    'Independent source review',
  );
  await userEvent.click(
    screen.getByRole('button', { name: 'Retry same review' }),
  );
  expect(
    await screen.findByText('Exchange rate approved successfully.'),
  ).toBeVisible();
  expect(writes()[0][1].body).toEqual({
    expected_version: 1,
    reason: 'Independent source review',
  });
  expect(writes()[0][1].key).toBe(writes()[1][1].key);
});
it('offers a readable register and kebab details without mutations to a reader', async () => {
  render(
    <AccountingExchangeDirectory
      company={COMPANY}
      canManage={false}
      initialQuery="status=CANDIDATE&returnTo=%2Fsettings"
    />,
  );
  await screen.findByRole('table', { name: 'Exchange quotes' });
  expect(screen.getByText(quote.rate)).toBeVisible();
  expect(
    screen.queryByRole('link', { name: 'New exchange rate' }),
  ).not.toBeInTheDocument();
  await userEvent.click(
    screen.getByRole('button', { name: /Actions for USD/ }),
  );
  expect(screen.getByRole('menuitem', { name: 'View quote' })).toHaveAttribute(
    'href',
    expect.stringContaining('status%3DCANDIDATE'),
  );
});
it('validates native charge limits, dates and integer choices', () => {
  const fields = form('charge-policies').fields,
    values = accountingInitial(fields, record('charge-policies'));
  Object.assign(values, {
    minimum: '10.0000',
    cap: '9.9999',
    rate: '0',
    day_basis: '365',
    valid_to: '2029-12-31',
    method: 'FIXED',
    compound: 'DAILY',
  });
  const result = accountingBody(fields, values);
  expect(result.errors).toMatchObject({
    cap: expect.any(String),
    rate: expect.any(String),
    valid_to: expect.any(String),
    compound: expect.any(String),
  });
  expect(result.body.day_basis).toBe(365);
});
it('closes a charge policy through its native versioned action and never offers editing', async () => {
  render(
    <AccountingConfigurationDetail
      company={COMPANY}
      config={accountingResource('charge-policies')!}
      id={ID}
      canManage
      canHistory
      availableResources={[]}
    />,
  );
  await userEvent.click(
    await screen.findByRole('button', { name: 'Record actions' }),
  );
  expect(
    screen.queryByRole('menuitem', { name: 'Edit' }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole('menuitem', { name: 'View history' }),
  ).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole('menuitem', { name: 'Close policy' }));
  await userEvent.type(screen.getByLabelText('Policy end date'), '2030-12-31');
  await userEvent.click(screen.getByRole('button', { name: 'Save end date' }));
  expect(
    await screen.findByText('Policy end date saved successfully.'),
  ).toBeVisible();
  expect(writes()[0][1].path).toBe(
    `/v1/companies/${COMPANY}/charge-policies/${ID}/close`,
  );
  expect(writes()[0][1].body).toEqual({
    expected_version: 3,
    valid_to: '2030-12-31',
  });
});
it.each([
  '/exchange-rates/imports/csv',
  '/exchange-rates/' + ID,
  '/exchange-rates/quotes/' + ID + '?status=CANDIDATE',
  '/exchange-rates/context?unexpected=yes',
  '/history/charge-policies/' + ID,
  '/charge-policies/' + ID + '/activate',
])('closes unsupported workflow route %s', (path) =>
  expect(allowed('POST', '/v1/companies/' + COMPANY + path)).toBe(false),
);
