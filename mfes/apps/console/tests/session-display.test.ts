import { expect, it, vi } from 'vitest';
import { getSession } from '../app/session';
import { identityFetch } from '../app/identity-session';

vi.mock('../app/identity-session', () => ({ identityFetch: vi.fn() }));
vi.mock('next/headers', () => ({ cookies: async () => ({ get: () => undefined }) }));

it('carries tenant location suggestions without selecting an existing company', async () => {
  vi.mocked(identityFetch).mockResolvedValueOnce(Response.json({
    user: { display_name: 'Owner', user_type: 'tenant_user', theme: null },
    tenant: { id: 'tenant-a', name: 'Books', slug: 'books', default_country_code: 'IN', default_state_code: 'MH' },
    company: null, permissions: ['company.create'], grants: [],
  }));
  expect((await getSession()).organisation).toMatchObject({
    id: 'tenant-a', defaultCountryCode: 'IN', defaultStateCode: 'MH',
  });
});

it('retains the resolved company separators, negative convention and symbol', async () => {
  vi.mocked(identityFetch).mockResolvedValueOnce(new Response(JSON.stringify({
    user: { display_name: 'Reader', user_type: 'company_user', theme: null },
    tenant: { name: 'Tenant', slug: 'tenant' }, company: { id: 'company', display_name: 'Company' },
    permissions: ['report.read'],
  }))).mockResolvedValueOnce(new Response(JSON.stringify({
    base_currency: 'EUR', amount_precision: 2, quantity_precision: 3, rounding_mode: 'down',
    date_format: 'dd.MM.yyyy', datetime_format: 'dd.MM.yyyy HH:mm', digit_grouping: 'western',
    currency_display: 'symbol', timezone: 'Europe/Berlin', locale: 'de-DE',
    decimal_separator: ',', thousands_separator: '.', negative_format: 'parentheses',
    currency_symbol_position: 'suffix', currency_symbol_override: '€',
  })));
  expect((await getSession()).display).toMatchObject({
    roundingMode: 'down', decimalSeparator: ',', groupSeparator: '.', negativeFormat: 'parens',
    currencySymbolPosition: 'suffix', currencySymbol: '€',
  });
});

it('keeps generated workspace identifiers out of the organisation switcher', async () => {
  vi.mocked(identityFetch).mockResolvedValueOnce(Response.json({
    user: { display_name: 'Owner', user_type: 'tenant_user', theme: null },
    tenant: { name: 'Books', slug: 'workspace-01900000000070008000000000000001' },
    company: null, permissions: [],
  }));
  // No company and no stored default: the chain asks the request's company list, which is empty.
  expect((await getSession()).organisation.code).toBe('Workspace');
});

it('preserves department grants while leaving company permissions unchanged', async () => {
  const grants = [{ permissions: ['role.read'], scope_type: 'department', scope_id: 'department', valid_from: '2000-01-01', valid_to: null }];
  vi.mocked(identityFetch).mockResolvedValueOnce(Response.json({
    user: { display_name: 'Reader', user_type: 'tenant_user', theme: null },
    tenant: { name: 'Books', slug: 'books' }, company: null, permissions: [], grants,
  }));
  expect(await getSession()).toMatchObject({ grants, permissions: [] });
});
