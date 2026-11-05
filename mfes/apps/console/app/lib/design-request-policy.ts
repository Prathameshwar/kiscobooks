const uuid = '[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}';
const prefix = '/v1/companies/' + uuid;
/** `Limit` is `ge=1, le=200` and `Cursor` `max_length=4096` on every design list route. */
const LIMIT = 200;
const CURSOR = 4096;

/**
 * What the browser may ask the `design` service for, as a closed list of method/path/query
 * triples (docs/invoice-design.md §6.4).
 *
 * The service authorizes every one of these again on arrival, against the actor's grants **and
 * the object's own company** — this is not the authorization boundary and must not be read as
 * one. What it is: the reason a path the console never calls cannot be reached through the
 * console's own credentials at all. A proxy that forwards `{service, path}` from the browser
 * without an allowlist is an open relay into the service mesh.
 *
 * Two deliberate narrowings beyond "what the API exposes":
 *
 *  - **`POST /renders` is absent.** Recording print evidence is the renderer's job, under
 *    `design.render.record`; a browser asserting "this document was printed" is evidence of
 *    nothing. The console reads that history (`GET /renders`) and never writes it.
 *  - **`status` is not writable anywhere**, matching the service: a template goes `PUBLISHED`
 *    by publishing a version and `ARCHIVED` by `DELETE`. There is no path here that sets it.
 */
export function allowedDesignRequest(method: string, path: string): boolean | undefined {
  const [route = '', query = ''] = path.split('?');
  // Claim the namespace first, so an unrecognised design path is a hard `false` rather than
  // falling through to another service's allowlist and being judged by its rules.
  if (!new RegExp('^' + prefix + '/(?:templates|assignments|resolve|assets|components|renders)(?:/|$)').test(route)) {
    return undefined;
  }
  if (!path.startsWith('/') || path.startsWith('//') || path.split('?').length > 2 || /[%\\#]/.test(route)) return false;
  const params = new URLSearchParams(query);
  const keys = [...params.keys()];
  // A repeated key is how one value gets past a check that reads only the first.
  if (new Set(keys).size !== keys.length) return false;

  const at = (pattern: string) => new RegExp('^' + prefix + pattern + '$', 'i').test(route);
  /** A paged read: the caller's own filters, plus the shared cursor/limit contract. */
  const paged = (filters: Record<string, (value: string) => boolean>) =>
    method === 'GET' &&
    keys.every((key) => {
      const value = params.get(key)!;
      if (key === 'limit') return /^\d+$/.test(value) && +value >= 1 && +value <= LIMIT;
      if (key === 'cursor') return value.length > 0 && value.length <= CURSOR;
      return key in filters && filters[key]!(value);
    });

  const bool = (value: string) => value === 'true' || value === 'false';
  const upper = (value: string) => /^[A-Z][A-Z0-9_]{0,49}$/.test(value);

  /* ---- templates and their versions ---- */
  if (at('/templates')) return method === 'POST' ? keys.length === 0 : paged({ status: (v) => v === 'DRAFT' || v === 'PUBLISHED' });
  if (at('/templates/' + uuid)) return keys.length === 0 && ['GET', 'PUT', 'DELETE'].includes(method);
  if (at('/templates/' + uuid + '/versions')) return method === 'POST' ? keys.length === 0 : paged({});
  if (at('/templates/' + uuid + '/versions/' + uuid)) return method === 'GET' && keys.length === 0;
  if (at('/templates/' + uuid + '/versions/' + uuid + '/publish')) return method === 'POST' && keys.length === 0;

  /* ---- routing rules, and what they resolve to ---- */
  // `template_id` answers "where is this design used" for the designer (plan R4).
  const id = (value: string) => new RegExp('^' + uuid + '$', 'i').test(value);
  if (at('/assignments')) return method === 'POST' ? keys.length === 0 : paged({ voucher_kind: upper, include_inactive: bool, template_id: id });
  if (at('/assignments/' + uuid)) return method === 'PATCH' && keys.length === 0;
  if (at('/resolve')) return method === 'POST' && keys.length === 0;

  /* ---- brand assets and reusable blocks ----
   * Uploading one (`POST /assets`) carries its bytes, base64, up to ~7MiB — far past this
   * route's small JSON ceiling — and goes through its own dedicated route instead
   * (`api/design-asset-upload/route.ts`), the same reason Purchase supporting files do. */
  if (at('/assets')) return method !== 'POST' && paged({ asset_type: upper, include_inactive: bool });
  if (at('/assets/' + uuid)) return keys.length === 0 && ['GET', 'DELETE'].includes(method);
  if (at('/components')) return method === 'POST' ? keys.length === 0 : paged({ category: upper, include_inactive: bool });
  if (at('/components/' + uuid)) return keys.length === 0 && ['GET', 'PATCH'].includes(method);

  /* ---- print evidence: read only, never written from a browser ---- */
  if (at('/renders')) return paged({ voucher_id: id });

  return false;
}
