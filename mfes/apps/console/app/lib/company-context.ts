import { cookies } from 'next/headers';
import { unstable_rethrow } from 'next/navigation';
import { businessToday, DEFAULT_DISPLAY_CONFIG, type PageMeta } from '@janso/ui';
import type { components as accounting } from '@janso/api-client/accounting';
import { accountingFetch, identityFetch } from '../identity-session';
import { FISCAL_YEAR_COOKIE, readFiscalYearCookie } from './company-cookies';
import { companyChoices, sessionCompanyListPath, SWITCHER_LIMIT, type CompanyChoice, type SessionCompanyPage } from './company-list';
import type { Session } from '../session';

export type { CompanyChoice };

export type FiscalYearChoice = {
  id: string;
  code: string;
  startDate: string;
  endDate: string;
  /** Contains today, in the company's timezone. */
  current: boolean;
  /** At least one period of this year is OPEN. Not postability — Accounting decides that. */
  open: boolean;
};

export type CompanyContext = {
  companies: CompanyChoice[];
  /** Why the list is empty, when it is empty for a reason the user can act on. */
  companiesNote: string | null;
  companiesPage?: PageMeta;
  fiscalYears: FiscalYearChoice[];
  fiscalYear: FiscalYearChoice | null;
  fiscalNote: string | null;
};

/** The readable companies, for the one request-scoped fetch `pageContext` makes. */
export type CompanyList = { companies: CompanyChoice[]; refused: boolean; page?: PageMeta };

/**
 * Which financial year the console *shows*, in order of preference:
 *
 *   1. the one this browser selected, if it still exists for this company
 *   2. the year containing today, in the company's timezone
 *   3. the latest year with an OPEN period
 *   4. the earliest year that exists
 *
 * **This is display and filter context only.** It never becomes a `posting_date`: every entry
 * screen resolves its own effect dates from the date on the document, and the server resolves
 * them again independently (CLAUDE.md invariant 4, docs/voucher-financial-year-design.md §3 —
 * "user selection can be a scoped preference; it cannot mutate calendar facts").
 *
 * Exported as a pure function because every one of these four branches is a real case for some
 * company — a mid-year signup, a year generated but not opened, a company whose first year
 * starts next April — and none of them is reachable by clicking around.
 */
export function resolveFiscalYear(
  years: readonly FiscalYearChoice[],
  selected: string | null,
  today: string,
): FiscalYearChoice | null {
  if (years.length === 0) return null;
  const chosen = selected ? years.find((year) => year.id === selected) : undefined;
  if (chosen) return chosen;
  // ISO dates compare as strings, and a business date has no instant to convert (see `format`).
  const containing = years.find((year) => year.startDate <= today && today <= year.endDate);
  if (containing) return containing;
  const byStart = [...years].sort((a, b) => a.startDate.localeCompare(b.startDate));
  const open = byStart.filter((year) => year.open).at(-1);
  return open ?? byStart[0] ?? null;
}

/**
 * The companies this actor may work in, fetched once per request.
 *
 * `GET /v1/session/companies` is a self-read derived from the actor's own grants, so it serves
 * a clerk and a tenant administrator the same way. The company *list* endpoint needs
 * `company.read`, which the seeded clerk, approver and controller roles do not hold — asking it
 * this question is what left their switcher empty during the UI phase.
 *
 * It takes no session, so it can be started in parallel with the session's own resolution.
 * `is_default` comes from the server, so nothing has to be marked afterwards.
 */
export async function getCompanyList(): Promise<CompanyList> {
  try {
    const response = await identityFetch(sessionCompanyListPath());
    if (!response.ok) return { companies: [], refused: true };
    const data: SessionCompanyPage = await response.json();
    return { companies: companyChoices(data), refused: false, page: { ...data.page, limit: SWITCHER_LIMIT } };
  } catch (error) {
    unstable_rethrow(error);
    return { companies: [], refused: true };
  }
}

function listNote(list: CompanyList): string | null {
  if (list.companies.length > 0) return null;
  // An empty self-read means this actor holds nothing in any company — not that they may not
  // look. The only other way to be empty is an outage, which is not the user's to fix.
  return list.refused
    ? 'Your companies are unavailable right now. Retry in a moment.'
    : 'No company has been assigned to you yet. Ask your administrator.';
}

async function listFiscalYears(company: string, timezone: string): Promise<Pick<CompanyContext, 'fiscalYears' | 'fiscalNote'>> {
  /*
   * Both queries at once: the periods query is company-scoped and filtered on status, so it
   * depends on nothing in the years response — and one query for every OPEN period rather than
   * one per year, so a company with ten years still costs two round trips, not eleven.
   */
  const [response, periods] = await Promise.all([
    accountingFetch(`/v1/companies/${company}/fiscal-years?limit=200`),
    accountingFetch(`/v1/companies/${company}/fiscal-periods?limit=200&status=OPEN`),
  ]);
  if (!response.ok) {
    // `period.read` is likewise a real permission. The selector is simply absent for an actor
    // without it; it is not an error, and it must not block the page.
    return { fiscalYears: [], fiscalNote: response.status === 403 ? null : 'Financial years are unavailable right now.' };
  }
  let page = (await response.json()) as accounting['schemas']['Page_FiscalYearListItem_'];
  const yearItems = [...page.items];
  const seen = new Set<string>();
  // Bound shell work; the management directory provides normal cursor paging beyond this window.
  for (let count = 1; page.page?.has_more && page.page.next_cursor && count < 10; count++) {
    const cursor = page.page.next_cursor;
    if (seen.has(cursor)) break; seen.add(cursor);
    const next = await accountingFetch(`/v1/companies/${company}/fiscal-years?limit=200&cursor=${encodeURIComponent(cursor)}`);
    if (!next.ok) throw new Error('Unable to read calendar continuation');
    page = await next.json(); yearItems.push(...page.items);
  }
  let limited = !!page.page?.has_more;
  const selected = readFiscalYearCookie((await cookies()).get(FISCAL_YEAR_COOKIE)?.value, company);
  if (selected && !yearItems.some(year => year.id === selected)) {
    const target = await accountingFetch(`/v1/companies/${company}/fiscal-years/${selected}`);
    if (target.ok) { const value: accounting['schemas']['FiscalYearDetail'] = await target.json(); if (value.company_id === company) yearItems.push(value); }
  }
  const openYears = new Set<string>();
  if (periods.ok) {
    let rows = (await periods.json()) as accounting['schemas']['Page_FiscalPeriodListItem_'];
    for (const period of rows.items ?? []) if (period.fiscal_year_id) openYears.add(period.fiscal_year_id);
    seen.clear();
    for (let count = 1; rows.page?.has_more && rows.page.next_cursor && count < 10; count++) {
      const cursor = rows.page.next_cursor;
      if (seen.has(cursor)) break; seen.add(cursor);
      const next = await accountingFetch(`/v1/companies/${company}/fiscal-periods?limit=200&status=OPEN&cursor=${encodeURIComponent(cursor)}`);
      if (!next.ok) { limited = true; break; }
      rows = await next.json();
      for (const period of rows.items ?? []) if (period.fiscal_year_id) openYears.add(period.fiscal_year_id);
    }
    limited ||= !!rows.page?.has_more;
  }
  const today = businessToday(timezone);
  const fiscalYears = [...new Map(yearItems.map(year => [year.id, year])).values()]
    .filter((item) => typeof item.start_date === 'string' && typeof item.end_date === 'string')
    .map((item) => ({
      id: item.id,
      code: item.code ?? '',
      startDate: item.start_date as string,
      endDate: item.end_date as string,
      current: (item.start_date as string) <= today && today <= (item.end_date as string),
      open: openYears.has(item.id),
    }));
  return {
    fiscalYears,
    fiscalNote: fiscalYears.length === 0 ? 'No financial year has been generated for this company.'
      : !periods.ok ? 'Period status is unavailable; open-year indicators could not be checked.'
        : limited ? 'This selector shows a limited calendar window. Use Manage years to browse all years and periods.' : null,
  };
}

/**
 * The company and financial-year context the rail renders, resolved once per request.
 *
 * It takes the session and the already-fetched company list rather than resolving either again:
 * one request resolves both in its page's Server Component and passes them down, because a
 * module-scope session is one object per server process shared across tenants (see `session.ts`).
 *
 * Nothing here is authorization. Every list is already scoped by the service that returned it,
 * and every later request is authorized again on its own.
 */
export async function getCompanyContext(session: Session, list: CompanyList): Promise<CompanyContext> {
  const timezone = session.display.timezone ?? DEFAULT_DISPLAY_CONFIG.timezone;
  const company = session.company.id ?? null;
  let fiscal: Pick<CompanyContext, 'fiscalYears' | 'fiscalNote'> = { fiscalYears: [], fiscalNote: null };
  if (company && session.permissions.includes('period.read')) {
    try { fiscal = await listFiscalYears(company, timezone); }
    catch (error) {
      unstable_rethrow(error);
      fiscal = { fiscalYears: [], fiscalNote: 'Financial years are unavailable right now.' };
    }
  }
  const selected = readFiscalYearCookie((await cookies()).get(FISCAL_YEAR_COOKIE)?.value, company);
  return {
    companies: list.companies,
    companiesNote: listNote(list),
    companiesPage: list.page,
    ...fiscal,
    fiscalYear: resolveFiscalYear(fiscal.fiscalYears, selected, businessToday(timezone)),
  };
}
