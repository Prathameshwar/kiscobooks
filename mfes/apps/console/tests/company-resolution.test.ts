/**
 * The company and financial-year resolution the rail renders from.
 *
 * Every branch here is a real company's situation that clicking around cannot reach: a
 * mid-year signup, a year generated but never opened, a clerk whose only authority is a grant
 * on one company. The year rule is display context only — it is asserted here precisely so
 * nobody later mistakes it for a posting input.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fiscalYearCookieValue, readCompanyCookie, readFiscalYearCookie } from '../app/lib/company-cookies';
import { getCompanyContext, getCompanyList, resolveFiscalYear, type FiscalYearChoice } from '../app/lib/company-context';
import type { CompanyChoice } from '../app/lib/company-list';
import type { Session } from '../app/session';
import { redirect } from 'next/navigation';

const { cookieGet, identityFetch, accountingFetch } = vi.hoisted(() => ({
  cookieGet: vi.fn(),
  identityFetch: vi.fn(),
  accountingFetch: vi.fn(),
}));
vi.mock('next/headers', () => ({ cookies: async () => ({ get: cookieGet }) }));
vi.mock('../app/identity-session', () => ({ identityFetch, accountingFetch }));

const company = '01990000-0000-7000-8000-000000000001';
const other = '01990000-0000-7000-8000-000000000009';

const year = (id: string, start: string, end: string, open = false): FiscalYearChoice => ({
  id,
  code: 'FY' + start.slice(0, 4),
  startDate: start,
  endDate: end,
  current: false,
  open,
});
const Y2025 = year('y1', '2025-04-01', '2026-03-31');
const Y2026 = year('y2', '2026-04-01', '2027-03-31');
const Y2027 = year('y3', '2027-04-01', '2028-03-31');

function session(overrides: Partial<Session> = {}): Session {
  return {
    user: { name: 'Admin', secondary: 'Tenant', theme: null, defaultCompanyId: null },
    organisation: { name: 'Tenant', code: 'tenant', id: 't1' },
    company: { name: 'Acme', id: company, code: 'ACME-01' },
    companySource: 'default',
    stepUpCompanyId: null,
    companyScopes: [],
    role: 'tenant admin',
    permissions: ['company.read', 'period.read'],
    display: { timezone: 'Asia/Kolkata' },
    ...overrides,
  };
}

describe('resolveFiscalYear', () => {
  it('honours this browser’s selection when the year still exists', () => {
    expect(resolveFiscalYear([Y2025, Y2026], 'y1', '2026-06-01')?.id).toBe('y1');
  });

  it('ignores a selection that is no longer one of the company’s years', () => {
    expect(resolveFiscalYear([Y2025, Y2026], 'deleted', '2026-06-01')?.id).toBe('y2');
  });

  it('prefers the year containing today, read in the company’s timezone', () => {
    expect(resolveFiscalYear([Y2025, Y2026, Y2027], null, '2027-03-31')?.id).toBe('y2');
    expect(resolveFiscalYear([Y2025, Y2026, Y2027], null, '2027-04-01')?.id).toBe('y3');
  });

  it('falls back to the latest year with an open period when today is outside every year', () => {
    const years = [year('y1', '2023-04-01', '2024-03-31', true), year('y2', '2024-04-01', '2025-03-31', true), Y2027];
    expect(resolveFiscalYear(years, null, '2026-06-01')?.id).toBe('y2');
  });

  it('falls back to the earliest year when none is open and today is outside them all', () => {
    expect(resolveFiscalYear([Y2027, Y2026], null, '2020-01-01')?.id).toBe('y2');
  });

  it('resolves nothing when no year has been generated', () => {
    expect(resolveFiscalYear([], 'y1', '2026-06-01')).toBeNull();
  });
});

describe('context cookies', () => {
  it('accepts only a uuid as the selected company, case-insensitively', () => {
    expect(readCompanyCookie(company.toUpperCase())).toBe(company);
    expect(readCompanyCookie('../other')).toBeNull();
    expect(readCompanyCookie(company + '&company_id=other')).toBeNull();
    expect(readCompanyCookie(undefined)).toBeNull();
  });

  it('reads a year only for the company it was stored against', () => {
    const value = fiscalYearCookieValue(company, 'd1f0c0de-0000-7000-8000-00000000000a');
    expect(readFiscalYearCookie(value, company)).toBe('d1f0c0de-0000-7000-8000-00000000000a');
    expect(readFiscalYearCookie(value, other)).toBeNull();
    expect(readFiscalYearCookie(value, null)).toBeNull();
    expect(readFiscalYearCookie(`${company}.not-a-uuid`, company)).toBeNull();
    expect(readFiscalYearCookie('malformed', company)).toBeNull();
  });
});

describe('getCompanyContext', () => {
  // A fresh `Response` per call: a body can only be read once, and the resolver legitimately
  // makes two Accounting calls.
  const json = (value: unknown, status = 200) => () => Promise.resolve(Response.json(value, { status }));
  const Y1 = '01990000-0000-7000-8000-0000000000a1';
  const Y2 = '01990000-0000-7000-8000-0000000000a2';
  const years = {
    items: [
      { id: Y1, code: 'FY2025-2026', start_date: '2025-04-01', end_date: '2026-03-31' },
      { id: Y2, code: 'FY2026-2027', start_date: '2026-04-01', end_date: '2027-03-31' },
    ],
    page: { has_more: false, next_cursor: null },
  };

  beforeEach(() => {
    vi.clearAllMocks();
    cookieGet.mockReturnValue(undefined);
    identityFetch.mockImplementation(json({ items: [], page: { has_more: false, next_cursor: null } }));
    accountingFetch.mockImplementation(json({ items: [], page: { has_more: false, next_cursor: null } }));
  });
  afterEach(() => vi.resetAllMocks());

  /** The one request-scoped list, as `pageContext` hands it over. */
  const list = (companies: CompanyChoice[] = [], refused = false) => ({ companies, refused });
  const choice = (id: string, code: string, name: string, overrides: Partial<CompanyChoice> = {}): CompanyChoice => ({
    id,
    name,
    code,
    isDefault: false,
    requiresStepUp: false,
    ...overrides,
  });

  it('reads the companies the actor may work in, without asking for company.read', async () => {
    identityFetch.mockImplementation(
      json({
        items: [
          { id: company, code: 'ACME-01', display_name: 'Acme Manufacturing', is_default: false, requires_step_up: false },
          { id: other, code: 'NW-01', display_name: 'Northwind', is_default: true, requires_step_up: true },
        ],
        page: { has_more: false, next_cursor: null },
      }),
    );

    const fetched = await getCompanyList();
    // The session's own list, not `/v1/companies`: a clerk holds no `company.read` and would
    // get a 403 from that endpoint, which is what emptied their switcher.
    expect(identityFetch).toHaveBeenCalledWith('/v1/session/companies?limit=50');
    expect(fetched).toEqual({
      refused: false,
      page: { limit: 50, has_more: false, next_cursor: null },
      companies: [
        choice(company, 'ACME-01', 'Acme Manufacturing'),
        // Both flags are the server's answer now, so nothing has to re-derive them.
        choice(other, 'NW-01', 'Northwind', { isDefault: true, requiresStepUp: true }),
      ],
    });
  });

  it('reports an outage as an outage rather than an empty tenant', async () => {
    identityFetch.mockImplementation(json({ error: {} }, 503));
    expect(await getCompanyList()).toEqual({ companies: [], refused: true });
  });

  it('keeps the server’s default marking, with no second opinion about it', async () => {
    const fetched = list([choice(company, 'ACME-01', 'Acme Manufacturing'), choice(other, 'NW-01', 'Northwind', { isDefault: true })]);

    const context = await getCompanyContext(
      session({ user: { name: 'Admin', secondary: 'T', theme: null, defaultCompanyId: other } }),
      fetched,
    );
    expect(context.companies.map((item) => [item.code, item.isDefault])).toEqual([
      ['ACME-01', false],
      ['NW-01', true],
    ]);
    expect(context.companiesNote).toBeNull();
  });

  it('explains an empty list as no authority, and an outage as an outage', async () => {
    // An empty self-read is not a permission problem: it means this actor holds nothing in any
    // company, which is a thing an administrator has to fix.
    const none = await getCompanyContext(session({ companyScopes: [], permissions: [] }), list());
    expect(none.companies).toEqual([]);
    expect(none.companiesNote).toMatch(/No company has been assigned/);

    const outage = await getCompanyContext(session(), list([], true));
    expect(outage.companiesNote).toMatch(/unavailable/);
  });

  it('marks the years that have an open period, with one query rather than one per year', async () => {
    accountingFetch.mockImplementation((path: string) =>
      path.includes('fiscal-periods')
        ? json({ items: [{ id: 'p1', fiscal_year_id: Y1, status: 'OPEN' }] })()
        : json(years)(),
    );

    const context = await getCompanyContext(session(), list());
    // Two queries, not one per year — and both started together, since neither needs the other.
    expect(accountingFetch).toHaveBeenCalledTimes(2);
    expect(context.fiscalYears.map((item) => [item.code, item.open])).toEqual([
      ['FY2025-2026', true],
      ['FY2026-2027', false],
    ]);
  });

  it('uses supported calendar queries and follows year and period continuations', async () => {
    accountingFetch.mockImplementation(async (path: string) => {
      expect(path).not.toContain('sort=start_date');
      const period = path.includes('fiscal-periods');
      if (path.includes('cursor=')) return Response.json({ items: period ? [{ fiscal_year_id: Y2 }] : [years.items[1]], page: { has_more: false, next_cursor: null } });
      return Response.json({ items: period ? [] : [years.items[0]], page: { has_more: true, next_cursor: period ? 'period-next' : 'year-next' } });
    });
    const result = await getCompanyContext(session(), list());
    expect(result.fiscalYears).toHaveLength(2); expect(result.fiscalYears.find(item => item.id === Y2)?.open).toBe(true);
    expect(accountingFetch.mock.calls.some(call => call[0].includes('cursor=year-next'))).toBe(true);
    expect(accountingFetch.mock.calls.some(call => call[0].includes('cursor=period-next'))).toBe(true);
  });

  it('keeps the page usable when the actor cannot read the fiscal calendar', async () => {
    accountingFetch.mockImplementation(json({ error: { code: 'permission_denied' } }, 403));

    const context = await getCompanyContext(session(), list());
    expect(context.fiscalYears).toEqual([]);
    expect(context.fiscalYear).toBeNull();
    // A permission the actor does not hold is not a failure to report.
    expect(context.fiscalNote).toBeNull();
  });

  it('reports a genuine calendar outage, unlike a denial', async () => {
    accountingFetch.mockImplementation(json({ error: {} }, 503));
    expect((await getCompanyContext(session(), list())).fiscalNote).toMatch(/unavailable/);
  });

  it('does not contact Accounting without calendar authority', async () => {
    accountingFetch.mockRejectedValue(new TypeError('offline'));
    const context = await getCompanyContext(session({ permissions: ['company.read'] }), list());
    expect(accountingFetch).not.toHaveBeenCalled();
    expect(context.fiscalYear).toBeNull();
    expect(context.fiscalNote).toBeNull();
  });

  it('keeps the company page available when calendar transport fails', async () => {
    accountingFetch.mockRejectedValue(new TypeError('offline'));
    const context = await getCompanyContext(session(), list());
    expect(context.fiscalYear).toBeNull();
    expect(context.fiscalNote).toMatch(/unavailable/);
  });

  it('reports an unavailable company switcher when its transport fails', async () => {
    identityFetch.mockRejectedValue(new TypeError('offline'));
    expect(await getCompanyList()).toEqual({ companies: [], refused: true });
  });

  it('preserves authentication and step-up redirects instead of hiding them as outages', async () => {
    identityFetch.mockImplementation(() => redirect('/refresh'));
    await expect(getCompanyList()).rejects.toMatchObject({ digest: expect.stringContaining('NEXT_REDIRECT') });
    accountingFetch.mockImplementation(() => redirect('/step-up'));
    await expect(getCompanyContext(session(), list())).rejects.toMatchObject({ digest: expect.stringContaining('NEXT_REDIRECT') });
  });

  it('applies this browser’s year selection only when it belongs to the open company', async () => {
    accountingFetch.mockImplementation((path: string) => (path.includes('fiscal-periods') ? json({ items: [] })() : json(years)()));

    cookieGet.mockReturnValue({ value: fiscalYearCookieValue(company, Y1) });
    expect((await getCompanyContext(session(), list())).fiscalYear?.code).toBe('FY2025-2026');

    // Another company's selection is ignored, falling through to the date rule.
    cookieGet.mockReturnValue({ value: fiscalYearCookieValue(other, Y1) });
    const foreign = await getCompanyContext(session(), list());
    expect(foreign.fiscalYear?.id).not.toBe(Y1);
  });

  it('asks nothing of Accounting when no company is open', async () => {
    const context = await getCompanyContext(session({ company: { name: 'Select a company' }, companySource: 'none' }), list());
    expect(accountingFetch).not.toHaveBeenCalled();
    expect(context.fiscalYear).toBeNull();
  });
});
