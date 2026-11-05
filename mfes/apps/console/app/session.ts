/** Identity session resolved separately for every server request. */
import type { DisplayConfig, ThemePreference } from '@janso/ui';
import {resolvedDisplay} from '@janso/ui';
import type { components } from '@janso/api-client/identity';
import { identityFetch } from './identity-session';
import { COMPANY_COOKIE, readCompanyCookie } from './lib/company-cookies';
import { cookies } from 'next/headers';
import { redirectSessionFailure } from './lib/session-recovery';

type Detail = components['schemas']['SessionDetail'];

function object(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
function verifiedSession(value: unknown): value is Detail {
  if (!object(value) || !object(value.user) || !object(value.tenant)) return false;
  if (typeof value.user.display_name !== 'string' || typeof value.user.user_type !== 'string' ||
      typeof value.tenant.name !== 'string' || typeof value.tenant.slug !== 'string' ||
      !Array.isArray(value.permissions) || !value.permissions.every(key => typeof key === 'string')) return false;
  if (value.grants !== undefined && (!Array.isArray(value.grants) || !value.grants.every(grant =>
    object(grant) && typeof grant.scope_type === 'string' && Array.isArray(grant.permissions) &&
    grant.permissions.every(key => typeof key === 'string')))) return false;
  return value.company === null || value.company === undefined ||
    (object(value.company) && typeof value.company.id === 'string' && typeof value.company.display_name === 'string');
}
function verifiedDisplay(value: unknown): value is components['schemas']['DisplayConfig'] {
  if (!object(value)) return false;
  const choices: Record<string, readonly string[]> = {
    rounding_mode: ['half_up', 'half_even', 'down', 'floor', 'ceil'],
    digit_grouping: ['western', 'indian'], currency_display: ['symbol', 'code', 'none'],
    currency_symbol_position: ['prefix', 'suffix'], negative_format: ['minus', 'parentheses'],
  };
  return typeof value.base_currency === 'string' && /^[A-Z]{3}$/.test(value.base_currency) &&
    ['timezone', 'locale', 'date_format', 'datetime_format', 'decimal_separator', 'thousands_separator']
      .every(key => typeof value[key] === 'string' && value[key].length > 0) &&
    Object.entries(choices).every(([key, allowed]) => typeof value[key] === 'string' && allowed.includes(value[key])) &&
    (value.currency_symbol_override === undefined || value.currency_symbol_override === null ||
      typeof value.currency_symbol_override === 'string') &&
    ['amount_precision', 'quantity_precision'].every(key => typeof value[key] === 'number' &&
      Number.isInteger(value[key]) && value[key] >= 0 && value[key] <= 4);
}

async function readBody(response: Response): Promise<unknown> {
  if (!response.ok) return redirectSessionFailure(response.status);
  try { return await response.json(); }
  catch { return redirectSessionFailure(503); }
}

/**
 * How the open company was chosen — the rail says so rather than implying a stored default.
 * Identity's own value (`selected_source`), not a guess reconstructed from what came back.
 */
export type CompanySource = Detail['selected_source'];

export type Session = {
  user: { id?: string; name: string; secondary: string; theme: ThemePreference | null; defaultCompanyId: string | null };
  organisation: { name: string; code: string; id?: string; defaultCountryCode?: string; defaultStateCode?: string | null };
  company: { name: string; id?: string; code?: string };
  companySource: CompanySource;
  /**
   * The company Identity selected and then withheld, because it demands a fresh sign-in
   * (`company.requires_step_up`). Distinct from having no company at all: there is something
   * to open here, and one action away from being open.
   */
  stepUpCompanyId: string | null;
  /**
   * Company ids the actor's own grants name, from the session's `grants`. Not a substitute for
   * the company list: it has no names, and a tenant-wide grant names no company at all.
   */
  companyScopes: string[];
  /** Account classification; assigned roles are shown on the Roles & access page. */
  role: string;
  permissions: string[];
  /** Preserve scope and validity for access review; these do not widen company permissions. */
  grants?: Detail['grants'];
  display: Partial<DisplayConfig>;
};

/**
 * The session, with the company Identity resolved for it.
 *
 * **The resolution chain is the server's** (`identity/services/session_context.py`): the company
 * named by this browser, else the user's stored default, else their primary membership, else the
 * first company they can open. The console used to run the last two steps itself, which cost a
 * second session round trip and — because its fallback was sent back as an *explicit* selection —
 * turned a first company that happens to require step-up into a 403 on the whole page. One
 * request answers it now, and mobile gets the same answer without reimplementing it.
 */
export async function getSession(): Promise<Session> {
  const selected = readCompanyCookie((await cookies()).get(COMPANY_COOKIE)?.value);
  const response = await identityFetch('/v1/session' + (selected ? '?company_id=' + selected : ''));
  const data = await readBody(response);
  if (!verifiedSession(data)) return redirectSessionFailure(503);
  let display: Partial<DisplayConfig> = {};
  if (data.company) {
    const settings = await identityFetch(`/v1/companies/${data.company.id}/display-config`);
    const values = await readBody(settings);
    if (!verifiedDisplay(values)) return redirectSessionFailure(503);
    display = resolvedDisplay(values);
  }
  return {
    user: { id: data.user.id, name: data.user.display_name, secondary: data.tenant.name,
      theme: data.user.theme as ThemePreference | null,
      defaultCompanyId: data.user.default_company_id ?? null },
    organisation: { name: data.tenant.name, code: /^workspace-[0-9a-f]{32}$/.test(data.tenant.slug) ? 'Workspace' : data.tenant.slug, id: data.tenant.id,
      defaultCountryCode: data.tenant.default_country_code, defaultStateCode: data.tenant.default_state_code },
    company: { name: data.company?.display_name ?? 'Select a company', id: data.company?.id, code: data.company?.code ?? undefined },
    companySource: data.selected_source,
    stepUpCompanyId: data.step_up_required ? data.selected_company_id ?? null : null,
    companyScopes: (data.grants ?? [])
      .filter((grant) => grant.scope_type === 'company' && typeof grant.scope_id === 'string')
      .map((grant) => grant.scope_id as string),
    role: data.user.user_type.replaceAll('_', ' '),
    permissions: data.permissions, grants: data.grants ?? [], display,
  };
}
