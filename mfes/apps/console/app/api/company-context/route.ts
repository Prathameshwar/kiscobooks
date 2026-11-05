import { NextResponse, type NextRequest } from 'next/server';
import { COMPANY_COOKIE, FISCAL_YEAR_COOKIE, fiscalYearCookieValue, isUuid } from '../../lib/company-cookies';
import { readJsonBody } from '../../lib/json-request';
import { isSameOrigin } from '../../lib/request-origin';
import { accessToken } from '../../lib/service-proxy';
import { serviceOrigin, stepUpCookieName } from '../../lib/services';

const reply = (value: unknown, status: number) => NextResponse.json(value, { status, headers: { 'Cache-Control': 'no-store' } });

/**
 * Writes the selected company (and financial year) for this browser.
 *
 * The selection is only ever a **hint**: every service still authorizes the company on every
 * request, and `getSession` passes the hint back to Identity to be re-resolved. Even so, the
 * company is verified here before the cookie is written — a cookie naming a company the actor
 * cannot reach would otherwise send every later page into an avoidable 403, and the one place
 * that can tell is Identity.
 *
 * Identity's refusal is returned as-is, which is what lets the client act on
 * `step_up_required`: the cookie is not written, and the browser is sent to auth to verify.
 *
 * The cookie attributes mirror the ones auth's step-up route writes for the same name — same
 * lifetime, same `httpOnly`/`lax`/`secure` posture, same optional shared domain. Two writers
 * of one cookie that disagreed on its scope would log a user out of their own selection.
 */
export async function POST(request: NextRequest) {
  if (!isSameOrigin(request)) return reply({ error: { message: 'Invalid request origin' } }, 403);
  const read = await readJsonBody(request, 1024);
  if ('error' in read) return read.error;
  const input = read.value;
  const company = isUuid(input.company) ? input.company.toLowerCase() : null;
  const year = input.fiscalYear === undefined || input.fiscalYear === null ? null : input.fiscalYear;
  const fiscalYear = year === null ? null : isUuid(year) ? year.toLowerCase() : undefined;
  if (!company || fiscalYear === undefined || Object.keys(input).some((key) => !['company', 'fiscalYear'].includes(key))) {
    return reply({ error: { message: 'Select a company to continue' } }, 422);
  }
  const base = process.env.IDENTITY_URL;
  const authUrl = process.env.AUTH_URL;
  if (!base || !authUrl) return reply({ error: { message: 'Company service is not configured' } }, 503);
  const session = await accessToken(request);
  if ('error' in session) return session.error;
  // The proof for *this* company, so a step-up already completed is not demanded twice.
  const proof = request.cookies.get(stepUpCookieName(company))?.value;
  let verified: Response;
  try {
    verified = await fetch(base.replace(/\/$/, '') + '/v1/session?company_id=' + company, {
      cache: 'no-store',
      redirect: 'error',
      signal: AbortSignal.timeout(5000),
      headers: { Authorization: 'Bearer ' + session.token, ...(proof ? { 'X-Company-Step-Up': proof } : {}) },
    });
  } catch {
    return reply({ error: { message: 'Company service is unavailable. Retry the same action.' } }, 503);
  }
  if (!verified.ok) {
    const value = await verified.json().catch(() => ({ error: { message: 'This company is unavailable.' } }));
    return reply(value, verified.status);
  }
  const resolved = await verified.json().catch(() => null);
  if (resolved?.step_up_required) return reply({ error: { code: 'step_up_required', message: 'Verify your access to this company.' } }, 403);
  if (resolved?.company === null && resolved.selected_source === 'explicit' &&
      isUuid(resolved.selected_company_id) && resolved.selected_company_id.toLowerCase() === company) {
    return reply({ error: { code: 'company_unavailable', message: 'This company is unavailable or outside your current access. Select an available company.' } }, 403);
  }
  if (!isUuid(resolved?.company?.id) || resolved.company.id.toLowerCase() !== company) {
    return reply({ error: { message: 'Company selection could not be verified. Try again.' } }, 502);
  }
  if (fiscalYear) {
    const accounting = serviceOrigin('accounting');
    if (!accounting) return reply({ error: { message: 'Financial-year service is not configured.' } }, 503);
    let checked: Response;
    try {
      checked = await fetch(`${accounting}/v1/companies/${company}/fiscal-years/${fiscalYear}`, {
        cache: 'no-store', redirect: 'error', signal: AbortSignal.timeout(5000),
        headers: { Authorization: 'Bearer ' + session.token, ...(proof ? { 'X-Company-Step-Up': proof } : {}) },
      });
    } catch { return reply({ error: { message: 'Financial years are unavailable. Retry the same action.' } }, 503); }
    if (!checked.ok) return reply(await checked.json().catch(() => ({ error: { message: 'This financial year is unavailable.' } })), checked.status);
    const yearDetail = await checked.json().catch(() => null);
    if (!isUuid(yearDetail?.id) || yearDetail.id.toLowerCase() !== fiscalYear || (yearDetail.company_id !== undefined && (!isUuid(yearDetail.company_id) || yearDetail.company_id.toLowerCase() !== company))) {
      return reply({ error: { message: 'Financial-year selection could not be verified.' } }, 502);
    }
  }
  const result = reply({ company, fiscalYear }, 200);
  const attributes = {
    httpOnly: true,
    secure: authUrl.startsWith('https://'),
    sameSite: 'lax' as const,
    path: '/',
    ...(process.env.AUTH_COOKIE_DOMAIN ? { domain: process.env.AUTH_COOKIE_DOMAIN } : {}),
  };
  result.cookies.set(COMPANY_COOKIE, company, { ...attributes, maxAge: 8 * 60 * 60 });
  /*
   * Switching company with no year named clears the year rather than leaving the previous
   * company's selection behind: the resolver would ignore it anyway (the value carries the
   * company it belongs to), and a cookie that is already dead is one more thing to explain.
   */
  if (fiscalYear) result.cookies.set(FISCAL_YEAR_COOKIE, fiscalYearCookieValue(company, fiscalYear), { ...attributes, maxAge: 8 * 60 * 60 });
  else result.cookies.set(FISCAL_YEAR_COOKIE, '', { ...attributes, maxAge: 0 });
  return result;
}
