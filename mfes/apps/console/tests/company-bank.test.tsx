import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { CompanyBankCreate } from '../app/components/CompanyBankCreate';
import {
  companyBankBody,
  companyBankReturn,
  type CompanyBankDraft,
} from '../app/lib/company-bank';
import { allowedCompanyRequest } from '../app/lib/company-request-policy';
import { serviceCall } from '../app/lib/service-call';
import { COMPANY, ID } from './accounting-configuration-fixtures';
vi.mock('../app/lib/service-call', async (original) => ({
  ...(await original<typeof import('../app/lib/service-call')>()),
  serviceCall: vi.fn(),
}));
const api = vi.mocked(serviceCall),
  path = '/v1/companies/' + COMPANY + '/bank-accounts';
const draft: CompanyBankDraft = {
  label: 'Operating bank',
  account_name: 'Review company',
  bank_name: 'Example bank',
  branch: '',
  account_number: '000011112222',
  iban: '',
  ifsc: '',
  swift: '',
  currency_code: 'INR',
};
beforeEach(() => {
  vi.clearAllMocks();
  api.mockImplementation(
    async (_, request) =>
      (request.path.includes('reference/currencies')
        ? [{ code: 'INR', name: 'Indian rupee' }]
        : request.method === 'POST'
          ? {
              id: ID,
              company_id: COMPANY,
              label: 'Operating bank',
              account_last4: '2222',
              is_active: true,
            }
          : {
              id: COMPANY,
              display_name: 'Review company',
              base_currency: 'INR',
              status: 'active',
            }) as never,
  );
});
it('allows only scoped company bank creation through the company boundary', () => {
  expect(allowedCompanyRequest('identity', 'POST', path)).toBe(true);
  for (const rejected of [
    path + '/' + ID + '/reveal',
    path + '?extra=1',
    path + '/rotate',
  ])
    expect(allowedCompanyRequest('identity', 'POST', rejected)).toBe(false);
  expect(allowedCompanyRequest('identity', 'PUT', path + '/' + ID)).toBe(false);
});
it('returns only to a validated bank profile form and retains its account', () => {
  expect(
    companyBankReturn('/accounting/account-bank-profiles/new?account_id=' + ID),
  ).toContain('account_id=' + ID);
  for (const unsafe of [
    '//evil.test',
    '/accounting/accounts/new',
    '/accounting/account-bank-profiles/../new',
    '/accounting/account-bank-profiles/%2e/new',
  ])
    expect(companyBankReturn(unsafe)).toBe('/accounting/account-bank-profiles');
});
it('validates identifiers and sends a non-primary native bank payload', () => {
  expect(companyBankBody(draft)).toMatchObject({
    errors: {},
    body: {
      is_primary: false,
      account_number: draft.account_number,
      iban: null,
    },
  });
  expect(
    companyBankBody({ ...draft, account_number: '', iban: '' }).errors,
  ).toHaveProperty('account_number');
  expect(
    companyBankBody({
      ...draft,
      account_number: 'short',
      ifsc: 'INVALID',
      swift: 'BAD',
      iban: 'short',
      label: '\n',
    }).errors,
  ).toMatchObject({
    label: expect.any(String),
    ifsc: expect.any(String),
    swift: expect.any(String),
    iban: expect.any(String),
  });
});
async function fill() {
  await screen.findByRole('textbox', { name: 'Bank label' });
  for (const [key, label] of [
    ['label', 'Bank label'],
    ['account_name', 'Account holder name'],
    ['bank_name', 'Bank name'],
    ['account_number', 'Account number'],
  ] as const)
    fireEvent.change(screen.getByLabelText(label, { exact: true }), {
      target: { value: draft[key] },
    });
}
it('creates a company bank and shows only masked identifiers with a return link', async () => {
  render(
    <CompanyBankCreate
      company={COMPANY}
      returnTo={'/accounting/account-bank-profiles/new?account_id=' + ID}
    />,
  );
  await fill();
  expect(
    screen.getByLabelText('Account number', { exact: true }),
  ).toHaveAttribute('type', 'password');
  await userEvent.click(
    screen.getByRole('button', { name: 'Create company bank' }),
  );
  await screen.findByText('Company bank created successfully.');
  expect(
    screen.getByRole('link', { name: 'Continue bank profile setup' }),
  ).toHaveAttribute(
    'href',
    '/accounting/account-bank-profiles/new?account_id=' + ID,
  );
  expect(
    screen.queryByDisplayValue(draft.account_number),
  ).not.toBeInTheDocument();
  const write = api.mock.calls.find(
    ([, request]) => request.method === 'POST',
  )![1];
  expect(write).not.toHaveProperty('key');
  expect(write.body).toMatchObject({
    is_primary: false,
    account_number: draft.account_number,
  });
});
it('never replays an uncertain company-bank creation', async () => {
  api.mockImplementation(async (_, request) => {
    if (request.method === 'POST')
      throw { status: 502, message: 'Response unavailable' };
    return (
      request.path.includes('reference/currencies')
        ? [{ code: 'INR', name: 'Indian rupee' }]
        : { id: COMPANY, base_currency: 'INR', status: 'active' }
    ) as never;
  });
  render(<CompanyBankCreate company={COMPANY} />);
  await fill();
  await userEvent.click(
    screen.getByRole('button', { name: 'Create company bank' }),
  );
  await screen.findByText(/Check the available company banks/);
  expect(
    screen.getByRole('button', { name: 'Create company bank' }),
  ).toBeDisabled();
  await waitFor(() =>
    expect(
      api.mock.calls.filter(([, request]) => request.method === 'POST'),
    ).toHaveLength(1),
  );
});

it('validates before writing and focuses the first invalid input', async () => {
  render(<CompanyBankCreate company={COMPANY} />);
  await screen.findByRole('button', { name: 'Create company bank' });
  await userEvent.click(
    screen.getByRole('button', { name: 'Create company bank' }),
  );
  await waitFor(() =>
    expect(screen.getByLabelText('Bank label', { exact: true })).toHaveFocus(),
  );
  expect(api.mock.calls.some(([, request]) => request.method === 'POST')).toBe(
    false,
  );
});

it('retains values for a definitive validation error and permits correction', async () => {
  api.mockImplementation(async (_, request) => {
    if (request.method === 'POST')
      throw {
        status: 422,
        message: 'Bank details need correction.',
        fields: { bank_name: 'Choose the registered bank name.' },
      };
    return (
      request.path.includes('reference/currencies')
        ? [{ code: 'INR', name: 'Indian rupee' }]
        : { id: COMPANY, base_currency: 'INR', status: 'active' }
    ) as never;
  });
  render(<CompanyBankCreate company={COMPANY} />);
  await fill();
  await userEvent.click(
    screen.getByRole('button', { name: 'Create company bank' }),
  );
  await screen.findByText('Choose the registered bank name.');
  expect(screen.getByLabelText('Account number', { exact: true })).toHaveValue(
    draft.account_number,
  );
  expect(screen.getByLabelText('Bank name', { exact: true })).toBeEnabled();
});

it('does not offer creation when the company currency is hidden', async () => {
  api.mockImplementation(
    async (_, request) =>
      (request.path.includes('reference/currencies')
        ? [{ code: 'INR', name: 'Indian rupee' }]
        : { id: COMPANY, status: 'active' }) as never,
  );
  render(<CompanyBankCreate company={COMPANY} />);
  await screen.findByText('Company settings could not be verified.');
  expect(
    screen.queryByRole('button', { name: 'Create company bank' }),
  ).not.toBeInTheDocument();
});

it('does not offer creation for an inactive company', async () => {
  api.mockImplementation(
    async (_, request) =>
      (request.path.includes('reference/currencies')
        ? [{ code: 'INR', name: 'Indian rupee' }]
        : { id: COMPANY, base_currency: 'INR', status: 'inactive' }) as never,
  );
  render(<CompanyBankCreate company={COMPANY} />);
  expect(
    await screen.findByRole('button', { name: 'Create company bank' }),
  ).toBeDisabled();
});
