/**
 * How the console learns which company is open.
 *
 * The chain itself is **Identity's** now (`identity/services/session_context.py`), so what is
 * tested here is the console's half of the contract: the cookie hint it is allowed to send, the
 * source it reports without inventing one, the step-up case it has to keep apart from "no
 * company", and failing closed when either request is refused. The branches are unreachable by
 * clicking — a brand-new user has no default, an invited clerk has no list.
 */
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { getSession } from '../app/session';
const { go } = vi.hoisted(() => ({ go: vi.fn() }));
vi.mock('next/navigation', () => ({ redirect: go }));

const { cookieGet, identityFetch } = vi.hoisted(() => ({ cookieGet: vi.fn(), identityFetch: vi.fn() }));
vi.mock('next/headers', () => ({ cookies: async () => ({ get: cookieGet }), headers: async () => new Headers() }));
vi.mock('../app/identity-session', () => ({ identityFetch }));

const id = '0198ffff-0000-7000-8000-000000000001';
const second = '0198ffff-0000-7000-8000-000000000002';
const user = { display_name: 'Reader', user_type: 'company_user', theme: null, default_company_id: null };
const detail = {
  user,
  tenant: { id: 't1', name: 'Tenant', slug: 'tenant' },
  company: null,
  selected_source: 'none',
  selected_company_id: null,
  step_up_required: false,
  permissions: ['company.read'],
  grants: [],
};
const withCompany = (company: string, overrides: Record<string, unknown> = {}) => ({
  ...detail,
  selected_source: 'explicit',
  selected_company_id: company,
  ...overrides,
  company: { id: company, display_name: 'Acme Manufacturing', code: 'ACME-01' },
});
const displayConfig = {
  timezone: 'Asia/Kolkata', base_currency: 'INR', amount_precision: 2, quantity_precision: 3,
  rounding_mode: 'half_up', locale: 'en', date_format: 'dd-MM-yyyy', datetime_format: 'dd-MM-yyyy HH:mm',
  digit_grouping: 'indian', decimal_separator: '.', thousands_separator: ',', negative_format: 'minus',
  currency_symbol_position: 'prefix', currency_symbol_override: null, show_amount_in_words: false,
  currency_display: 'symbol',
};

/** Answers each Identity path the session resolution may touch, in any order. */
function respond(routes: Record<string, unknown>) {
  identityFetch.mockImplementation((path: string) => {
    const key = Object.keys(routes).find((candidate) => path === candidate || path.startsWith(candidate));
    if (key === undefined) return Promise.resolve(Response.json({ error: {} }, { status: 404 }));
    const value = routes[key];
    return Promise.resolve(value instanceof Response ? value.clone() : Response.json(value as object));
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  go.mockImplementation((url) => { throw new Error('redirect:' + url); });
  cookieGet.mockReturnValue(undefined);
});
afterEach(() => vi.resetAllMocks());

it.each([id, id.toUpperCase()])('carries only the validated selected-company hint into bootstrap: %s', async (selected) => {
  cookieGet.mockReturnValue({ value: selected });
  respond({ '/v1/session': withCompany(id), [`/v1/companies/${id}/display-config`]: displayConfig });

  const session = await getSession();
  expect(identityFetch).toHaveBeenCalledWith('/v1/session?company_id=' + id);
  expect(session.companySource).toBe('explicit');
});

it.each(['../other', id + '&company_id=other', ''])('ignores malformed selection: %s', async (selected) => {
  cookieGet.mockReturnValue({ value: selected });
  respond({ '/v1/session': detail });

  await getSession();
  expect(identityFetch).toHaveBeenCalledWith('/v1/session');
});

it.each([403, 503])('fails closed when Identity refuses the selected company: %s', async (status) => {
  cookieGet.mockReturnValue({ value: id });
  identityFetch.mockResolvedValue(Response.json({}, { status }));
  await expect(getSession()).rejects.toThrow('redirect:/session-recovery?');
});

it.each(['default', 'membership', 'first'] as const)('reports the rule Identity used, never a guess: %s', async (source) => {
  respond({
    '/v1/session': withCompany(id, { selected_source: source, user: { ...user, default_company_id: source === 'default' ? id : null } }),
    [`/v1/companies/${id}/display-config`]: displayConfig,
  });

  const session = await getSession();
  // One request: the chain is resolved server-side, so there is no second session round trip
  // and no company-list probe to find a fallback.
  expect(identityFetch).toHaveBeenCalledWith('/v1/session');
  expect(identityFetch).not.toHaveBeenCalledWith(expect.stringContaining('/v1/session?company_id='));
  expect(identityFetch).not.toHaveBeenCalledWith(expect.stringContaining('/v1/companies?'));
  expect(session.companySource).toBe(source);
  expect(session.company).toMatchObject({ id, name: 'Acme Manufacturing', code: 'ACME-01' });
  expect(session.stepUpCompanyId).toBeNull();
});

it('keeps a company awaiting verification apart from having no company', async () => {
  respond({
    '/v1/session': { ...detail, selected_source: 'default', selected_company_id: second, step_up_required: true },
  });

  const session = await getSession();
  // Nothing is open, so no display config is fetched — but there is a company to verify, and
  // the rail offers that instead of "Select a company".
  expect(session.company.id).toBeUndefined();
  expect(session.stepUpCompanyId).toBe(second);
  expect(session.companySource).toBe('default');
});

it('opens nothing, and says so, when no company can be opened', async () => {
  respond({ '/v1/session': detail });

  const session = await getSession();
  expect(session.companySource).toBe('none');
  expect(session.company.id).toBeUndefined();
  expect(session.company.name).toBe('Select a company');
  expect(session.stepUpCompanyId).toBeNull();
});

it('keeps the company scopes the actor’s own grants name, for an empty switcher to explain', async () => {
  respond({
    '/v1/session': {
      ...detail,
      grants: [
        { permissions: ['invoice.create'], scope_type: 'company', scope_id: second, valid_from: '2026-01-01', valid_to: null },
        { permissions: ['tenant.read'], scope_type: 'tenant', scope_id: null, valid_from: '2026-01-01', valid_to: null },
      ],
    },
  });

  expect((await getSession()).companyScopes).toEqual([second]);
});

it('fails closed when the open company’s display settings cannot be read', async () => {
  respond({
    '/v1/session': withCompany(id),
    [`/v1/companies/${id}/display-config`]: Response.json({ error: {} }, { status: 503 }),
  });

  await expect(getSession()).rejects.toThrow('redirect:/session-recovery?');
});
