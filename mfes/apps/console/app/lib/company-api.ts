'use client';

import { replayableServiceRequest, requestFailure, serviceCall, type RequestFailure, type ServiceRequest } from './service-call';
import { goTo, reload, stepUpUrl } from './navigate';
import { sessionFetch } from './session-fetch';
import { BEFORE_COMPANY_CHANGE } from './use-unsaved-changes';

export type CompanyService = 'identity' | 'accounting' | 'catalog' | 'vouchers';
export type CompanyFailure = RequestFailure;

/** One company-setup call, through the console's own boundary (`app/api/company`). */
export async function companyCall<T>(service: CompanyService, path: string, request: Omit<ServiceRequest, 'service' | 'path'> = {}): Promise<T> {
  const saved = { ...request, body: request.body === undefined ? undefined : structuredClone(request.body) };
  for (let attempt = 0; ; attempt++) {
    try {
      return await serviceCall<T>('/api/company', { service, path, ...saved }, 'company setup');
    } catch (value) {
      const failure = requestFailure(value, 'company setup');
      // New-company enrollment and feature changes briefly invalidate Catalog's
      // source lease. Wait for its verified worker; never fabricate authority.
      // Only reads and requests carrying an unchanged idempotency key are safe.
      if (service !== 'catalog' || failure.status !== 503 || failure.code !== 'source_unavailable'
        || !replayableServiceRequest(saved) || saved.signal?.aborted || attempt >= 29) throw value;
      await new Promise<void>(resolve => setTimeout(resolve, 1000));
    }
  }
}

export function companyFailure(value: unknown): CompanyFailure {
  return requestFailure(value, 'company service');
}

/**
 * Stores this company as the user's default (`PATCH /v1/session/preferences`).
 *
 * A self-write that confers no access: Identity accepts only a company this actor can already
 * open, and refuses anything else with a 422 on the field. It replaces the 8 h cookie as the
 * thing that decides where a *new* session lands — the cookie still decides this browser's.
 *
 * Throws on refusal, unlike `openCompany`: there is no step-up branch to absorb here, so the
 * caller simply shows the message.
 */
export function setDefaultCompany(company: string): Promise<unknown> {
  return companyCall('identity', '/v1/session/preferences', { method: 'PATCH', body: { default_company_id: company } });
}

/**
 * Opens a company for this browser: records the selection, then re-renders the page against it.
 *
 * The one way company context changes, so the rule that matters is stated once — a company
 * whose answer is `step_up_required` is **not** a failure to report, it is a company that wants
 * a fresh sign-in, and auth owns that flow. Forgetting that branch strands the operator on a
 * 403 they cannot act on, which is why both the rail and the directory call this rather than
 * each repeating it.
 *
 * Returns the failure for the caller to render, or `null` once the page is on its way. It never
 * throws: every caller needs the message, and none of them needs a stack.
 */
let selectionPending = false;
export async function openCompany(company: string, fiscalYear?: string | null, destination?: 'company' | 'companies'): Promise<CompanyFailure | null> {
  if (selectionPending) return { status: 409, message: 'A company change is already in progress. Wait for it to finish.' };
  if (!window.dispatchEvent(new Event(BEFORE_COMPANY_CHANGE, { cancelable: true }))) {
    return { status: 409, message: 'Save or discard unsaved changes before changing company or financial year.' };
  }
  selectionPending = true;
  try { return await selectCompany(company, fiscalYear, destination); }
  finally { selectionPending = false; }
}
async function selectCompany(company: string, fiscalYear?: string | null, destination?: 'company' | 'companies'): Promise<CompanyFailure | null> {
  try {
    const response = await sessionFetch('/api/company-context', {
      method: 'POST',
      cache: 'no-store',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ company, ...(fiscalYear ? { fiscalYear } : {}) }),
    });
    if (!response.ok) {
      const value = await response.json().catch(() => null);
      const failure: CompanyFailure = {
        status: response.status,
        code: value?.error?.code,
        message: value?.error?.message ?? 'Unable to open this company. Try again.',
      };
      if (failure.code === 'step_up_required') {
        goTo(stepUpUrl(company));
        return null;
      }
      return failure;
    }
  } catch (value) {
    return companyFailure(value);
  }
  /*
   * A full load, not `router.refresh()`. The open company decides the permissions, the display
   * config and every company-scoped read on the page, all resolved in Server Components. An RSC
   * refresh would also work and would be faster; it is the natural follow-up, and it is deferred
   * only because it puts a router dependency into two components that are otherwise router-free.
   */
  if (destination) goTo(destination === 'company' ? '/companies/' + company : '/companies');
  else reload();
  return null;
}
