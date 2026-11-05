import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { AccountingFields } from '../app/components/AccountingConfigurationCommon';
import { AccountingConfigurationEditor } from '../app/components/AccountingConfigurationEditor';
import { AccountingConfigurationDirectory } from '../app/components/AccountingConfigurationDirectory';
import {
  accountingBody,
  accountingChange,
  accountingInitial,
} from '../app/lib/accounting-configuration';
import { accountingResource } from '../app/lib/accounting-configuration-resources';
import { serviceCall } from '../app/lib/service-call';
import { COMPANY, form, response } from './accounting-configuration-fixtures';

vi.mock('../app/lib/service-call', async (original) => ({
  ...(await original<typeof import('../app/lib/service-call')>()),
  serviceCall: vi.fn(),
}));
vi.mock('../app/lib/navigate', () => ({
  goTo: vi.fn(),
  signInUrl: () => '/signin',
}));

function accountForm() {
  const metadata = form('accounts');
  for (const field of metadata.fields) {
    if (field.key === 'currency') {
      field.initial = 'INR';
      Object.assign(field.control, {
        depends_on: { currency_mode: ['FIXED'] },
        required_when_active: true,
        reference_filters: { company_currency: 'true' },
      });
    }
    if (field.key === 'party_id' || field.key === 'party_role')
      Object.assign(field.control, {
        depends_on: { kind: ['PARTY'] },
        required_when_active: true,
      });
    if (field.key === 'rounding_limit')
      Object.assign(field.control, {
        depends_on: { rounding_method: ['NORMAL', 'UP', 'DOWN'] },
        required_when_active: true,
      });
  }
  return metadata;
}
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(serviceCall).mockImplementation(async (_, request) =>
    request.path.includes('/configuration/accounts/field-set')
      ? (accountForm() as never)
      : (response(request.path, request.method, request.body) as never),
  );
});

it('disables irrelevant currency, party and rounding controls and explains why', () => {
  render(
    <AccountingFields
      company={COMPANY}
      resource="accounts"
      fields={accountForm().fields}
      values={{
        kind: 'GENERAL',
        currency_mode: 'BASE',
        rounding_method: 'NONE',
      }}
      onChange={() => {}}
    />,
  );
  expect(screen.getByRole('combobox', { name: 'Currency' })).toBeDisabled();
  expect(screen.getByRole('combobox', { name: 'Party' })).toBeDisabled();
  expect(
    screen.getByRole('textbox', { name: 'Rounding limit' }),
  ).toBeDisabled();
  expect(screen.getByText(/Available when Currency mode/)).toBeVisible();
});

it('uses the company default when fixed currency is explicitly selected and clears it for base mode', async () => {
  render(
    <AccountingConfigurationEditor
      company={COMPANY}
      config={accountingResource('accounts')!}
    />,
  );
  const mode = await screen.findByRole('combobox', { name: 'Currency mode' });
  const currency = screen.getByRole('combobox', { name: 'Currency' });
  expect(currency).toBeDisabled();
  await userEvent.selectOptions(mode, 'FIXED');
  await waitFor(() => expect(currency).toHaveValue('Indian rupee'));
  expect(currency).toBeRequired();
  expect(
    vi
      .mocked(serviceCall)
      .mock.calls.some(([, req]) => req.path.includes('company_currency=true')),
  ).toBe(true);
  await userEvent.selectOptions(mode, 'BASE');
  expect(currency).toBeDisabled();
  expect(currency).toHaveValue('');
});

it('preserves stored choices that are no longer available and offers an explicit clear', async () => {
  const field = accountForm().fields.find(
    (entry) => entry.key === 'currency_mode',
  )!;
  field.control.choices = ['BASE', 'FIXED'];
  const change = vi.fn();
  render(
    <AccountingFields
      company={COMPANY}
      resource="accounts"
      fields={[field]}
      values={{ currency_mode: 'MULTI' }}
      onChange={change}
    />,
  );
  expect(screen.getByRole('combobox', { name: 'Currency mode' })).toHaveValue(
    'MULTI',
  );
  expect(
    screen.getByRole('option', { name: /Multi.*unavailable/ }),
  ).toBeDisabled();
  expect(change).not.toHaveBeenCalled();
});

it('shows a feature restriction and company configuration navigation without permitting a write', async () => {
  const original = vi.mocked(serviceCall).getMockImplementation()!;
  vi.mocked(serviceCall).mockImplementation(async (...args) => {
    if (args[1].path.includes('/configuration/withholding-sections/'))
      return {
        ...form('withholding-sections'),
        fields: form('withholding-sections').fields.map((field) => ({
          ...field,
          editable: false,
        })),
        can_manage: false,
        can_create: false,
        unavailable_reason: 'Enable TDS or TCS in Company Config.',
      } as never;
    return original(...args);
  });
  render(
    <AccountingConfigurationEditor
      company={COMPANY}
      config={accountingResource('withholding-sections')!}
    />,
  );
  expect(
    await screen.findByText('Enable TDS or TCS in Company Config.'),
  ).toBeVisible();
  expect(
    screen.queryByText(/A required field is hidden or protected/),
  ).not.toBeInTheDocument();
  expect(
    screen.getByRole('link', { name: 'Open Company Config' }),
  ).toHaveAttribute(
    'href',
    expect.stringContaining('/companies/' + COMPANY + '/configuration'),
  );
  expect(
    screen.getByRole('button', { name: 'Create withholding section' }),
  ).toBeDisabled();
});

it('omits irrelevant defaults and requires a value when its setting is enabled', () => {
  const fields = accountForm().fields;
  const values = accountingInitial(fields);
  expect(values.currency).toBeNull();
  const fixed = accountingChange(fields, values, 'currency_mode', 'FIXED');
  expect(fixed.currency).toBe('INR');
  expect(
    accountingBody(fields, { ...fixed, currency: null }).errors.currency,
  ).toBe('Enter currency.');
  const rounding = accountingChange(
    fields,
    { ...values, rounding_method: 'NORMAL', rounding_limit: '0.5000' },
    'rounding_method',
    'NONE',
  );
  expect(rounding.rounding_limit).toBeNull();
});

it('never clears a protected dependent value when its controller changes', () => {
  const fields = accountForm().fields;
  fields.find((field) => field.key === 'rounding_limit')!.editable = false;
  const result = accountingChange(
    fields,
    { rounding_method: 'NORMAL', rounding_limit: '0.5000' },
    'rounding_method',
    'NONE',
  );
  expect(result.rounding_limit).toBe('0.5000');
  expect(accountingBody(fields, result).body).not.toHaveProperty(
    'rounding_limit',
  );
});

it('keeps a historical unavailable choice out of an unrelated update', () => {
  const field = accountForm().fields.find(
    (entry) => entry.key === 'currency_mode',
  )!;
  field.control.choices = ['BASE', 'FIXED'];
  const result = accountingBody(
    [field],
    { currency_mode: 'MULTI' },
    {
      id: COMPANY,
      company_id: COMPANY,
      row_version: 3,
      currency_mode: 'MULTI',
    },
  );
  expect(result.errors).toEqual({});
  expect(result.body).toEqual({ expected_version: 3 });
});

it('hides new withholding actions while retaining the directory and company config link', async () => {
  vi.mocked(serviceCall).mockImplementation(async (_, request) => {
    if (request.path.includes('/configuration/withholding-sections/'))
      return {
        ...form('withholding-sections', 'read'),
        can_create: false,
        can_manage: false,
        unavailable_reason: 'Enable TDS or TCS in Company Config.',
      } as never;
    return response(request.path, request.method, request.body) as never;
  });
  render(
    <AccountingConfigurationDirectory
      company={COMPANY}
      config={accountingResource('withholding-sections')!}
      canManage
    />,
  );
  expect(
    await screen.findByText('Enable TDS or TCS in Company Config.'),
  ).toBeVisible();
  expect(
    screen.queryByRole('link', { name: 'New withholding section' }),
  ).not.toBeInTheDocument();
  expect(
    screen.getByRole('link', { name: 'Open Company Config' }),
  ).toBeVisible();
});
