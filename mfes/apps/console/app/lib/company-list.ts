import type { components } from '@janso/api-client/identity';

export type CompanyChoice = {
  id: string;
  name: string;
  code: string;
  /** The company stored on the user as the one to open. */
  isDefault: boolean;
  /** Opening it will ask for a fresh sign-in, so a row can say so before it is chosen. */
  requiresStepUp: boolean;
};

/** How many companies the rail and the directory ask for before the reader has to search. */
export const SWITCHER_LIMIT = 50;

/** The lowest query length worth sending: the API rejects a shorter `q` with a 422. */
export const SEARCH_MIN = 2;

/**
 * The one company-list request this console makes.
 *
 * `GET /v1/session/companies` is an authenticated **self-read**: it answers "which companies may
 * I work in", derived from the actor's own grants, and needs no `company.read` — which the
 * seeded clerk, approver and controller roles do not hold (docs/roles-permissions.md §4). The
 * company *list* endpoint answers the different question "describe the companies I may read",
 * and using it here is what left those roles with an empty switcher.
 *
 * The rail, the directory and the server-rendered first page all use this, so they cannot drift
 * on the limit, the sort or the source the way three hand-written query strings did.
 */
export function sessionCompanyListPath({ q, limit = SWITCHER_LIMIT, cursor }: { q?: string; limit?: number; cursor?: string | null } = {}): string {
  const query = new URLSearchParams({ limit: String(limit) });
  if (q) query.set('q', q);
  if (cursor) query.set('cursor', cursor);
  return '/v1/session/companies?' + query.toString();
}

export type SessionCompanyPage = components['schemas']['SessionCompanyPage'];

/**
 * Identity's switcher row as this console's own.
 *
 * One mapper, because the name fallback is a judgement (a company may legitimately have no
 * trading name, and a field denied for read is simply absent from the payload) and three copies
 * of it had already disagreed about whether a searched row still shows its "Default" badge.
 * `is_default` is the server's answer now, so no caller has to re-derive it from the session.
 */
export function companyChoices(page: SessionCompanyPage | null | undefined): CompanyChoice[] {
  return (page?.items ?? [])
    .filter((item): item is components['schemas']['SessionCompanyChoice'] & { id: string } => typeof item.id === 'string')
    .map((item) => ({
      id: item.id,
      name: item.display_name ?? item.code ?? 'Company',
      code: item.code ?? '',
      isDefault: item.is_default,
      requiresStepUp: item.requires_step_up ?? false,
    }));
}
