/**
 * The two context cookies and the one rule for reading them.
 *
 * Shared by the writer (`app/api/company-context`) and the reader (`app/lib/company-context`,
 * `app/session`) so the name and the encoding are stated once. `janso-company` is also written
 * by auth's step-up route under the same name — a second opinion about its format would mean a
 * verified company silently failing to open.
 *
 * Both values are **hints**. Identity re-resolves the company on every request and authorizes
 * it; the financial year is checked against the company's actual generated years.
 */
export const COMPANY_COOKIE = 'janso-company';
export const FISCAL_YEAR_COOKIE = 'janso-fiscal-year';

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * The id shape this console will accept from a browser. Exported because the cookie writer
 * validates the same two ids before writing them, and a second regex is how one of the two ends
 * up accepting `../other`.
 */
export function isUuid(value: unknown): value is string {
  return typeof value === 'string' && UUID.test(value);
}

export function readCompanyCookie(value: string | undefined): string | null {
  return isUuid(value) ? value.toLowerCase() : null;
}

/**
 * One cookie carries both ids, because a year only means anything inside its company: a single
 * `janso-fiscal-year` holding a bare year id would be read against whichever company happened
 * to be open after a switch. Keying the cookie *name* by company instead would grow one cookie
 * per company the user ever opens.
 */
export function fiscalYearCookieValue(company: string, fiscalYear: string): string {
  return `${company.toLowerCase()}.${fiscalYear.toLowerCase()}`;
}

/** The selected year, but only when the cookie belongs to the company actually open. */
export function readFiscalYearCookie(value: string | undefined, company: string | null): string | null {
  if (!value || !company) return null;
  const parts = value.split('.');
  if (parts.length !== 2) return null;
  const [owner, year] = parts;
  if (!owner || !year || owner.toLowerCase() !== company.toLowerCase()) return null;
  return isUuid(year) ? year.toLowerCase() : null;
}
