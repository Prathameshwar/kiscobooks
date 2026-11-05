/**
 * The client's half of `GET /v1/audit-events` — the audit trail (docs/audit.md §1, §5).
 *
 * Written against the endpoint that exists, not against a convenient shape: the filters, the two
 * sort keys, the `{items, page}` envelope and the separate detail surface all match
 * `apis/audit/src/audit/api/routes.py`. The runtime transport is in `audit-api.ts`;
 * in-memory loaders in this file support component tests only.
 *
 * Four things this file is careful about, all of which the screen above it inherits:
 *
 *  - **No PII.** An audit row holds `actor_user_id`, never a name (docs/audit.md §5.2,
 *    CLAUDE.md §6.9). Names resolve through identity, elsewhere and separately; a trail that
 *    denormalized them would keep a copy of personal data for the retention period of the trail.
 *  - **No free-text search.** The endpoint has no `q`. Filters are typed and indexed — category,
 *    entity type, action, an `occurred_at` range — because scanning a partitioned append-only table
 *    for a substring is the query that takes the database down (api-conventions §2.3).
 *  - **The cursor is bound to the whole query**, sort and filters included, and reusing one after
 *    any of them changed is a `422` rather than a silently different window (§2.1).
 *  - **`security` is not here.** That category is a separate surface behind
 *    `audit.read_security` (§5.1), so a reader with plain `audit.read` never sees one — including
 *    in an export.
 *
 * **Request-scoped data never lives at module scope.** There is no `export const events`: one
 * module-scope binding is one object per server *process*, shared by every request it serves, which
 * is how one tenant's trail reaches another tenant's page (CLAUDE.md §5.3). The sample set is built
 * per call inside `sampleAuditEvents()`.
 */
import type { components } from '@janso/api-client/audit';
import { MASTER_AUDIT_ENTITIES } from './master-audit-entities';
import { checkLimit, encodeCursor, offsetFor } from './list-cursor';

/** The two keys the endpoint allows a sort on, and its default. */
export const AUDIT_SORT_KEYS = ['occurred_at', 'sequence'] as const;
export const AUDIT_DEFAULT_SORT = '-occurred_at';

/** Every category `audit.read` covers. `security` is a separate surface (§5.1). */
export const AUDIT_CATEGORIES = ['money', 'admin', 'access', 'system'] as const;
export type AuditCategory = (typeof AUDIT_CATEGORIES)[number];

/**
 * The entity types the trail records, for the `entity_type` filter.
 *
 * A declared list rather than one derived from the rows on screen: a filter built from the page in
 * hand could only ever offer what is already visible, which is the opposite of what a filter is for.
 * Server-side these are the registered auditable entities — the real screen reads them from the
 * registry endpoint, and this is the list to replace when it does.
 */
export const AUDIT_ENTITY_TYPES = MASTER_AUDIT_ENTITIES;

/** The platform's list bounds (api-conventions §2.1). Not preferences a screen may raise. */
export const AUDIT_LIST_LIMIT = 50;
export const AUDIT_LIST_MAX_LIMIT = 200;

/** Long enough that the table's pending state is a state a person sees. */
export const AUDIT_LIST_DELAY_MS = 90;

/**
 * The lean list row — exactly `AuditEventItem`. No `changes`, no `context`: a list never returns
 * the JSON columns (api-conventions §3), which is also why the detail is a second request.
 */
export type AuditEventItem = components['schemas']['AuditEventItem'];

/** One field's before and after, as the trail stores them — strings, never coerced numbers. */
export type AuditChange = { from: string | null; to: string | null; changed?: boolean; from_recorded?: boolean; to_recorded?: boolean };

/** `AuditEventDetail`: the row in full, including the chain proof an external auditor re-verifies. */
export type AuditEventDetail = AuditEventItem & {
  /** Optional authorized Identity projection, never an Audit API or stored field. */
  actor_name?: string | null;
  on_behalf_of_name?: string | null;
  changes: Readonly<Record<string, AuditChange>> | null;
  context: Readonly<Record<string, string>> | null;
  reason: string | null;
  request_id: string | null;
  message_id: string;
  /** Hex of the `BINARY(32)` chain values. `null` on the first event of a tenant's chain. */
  prev_hash: string | null;
  row_hash: string;
};

export type AuditEventPage = {
  items: AuditEventItem[];
  page: { limit: number; has_more: boolean; next_cursor: string | null };
};

/** Typed, allowlisted, indexed — never a field/operator query language (api-conventions §2.2). */
export type AuditListParams = {
  category?: string;
  entity_type?: string;
  action?: string;
  /** `occurred_at` bounds, as ISO instants. A range is two named parameters, not an operator. */
  occurred_from?: string;
  occurred_to?: string;
  sort?: string;
  limit?: number;
  cursor?: string | null;
};

/** What the API returns as `422`: a parameter it cannot use. */
export class AuditQueryError extends Error {
  readonly status = 422;

  constructor(message: string) {
    super(message);
    this.name = 'AuditQueryError';
  }
}

/** This surface's 422, for the shared cursor and limit rules in `list-cursor`. */
const fail = (message: string): Error => new AuditQueryError(message);

/**
 * The query a cursor is bound to: the sort, every filter and the page size, in a fixed order.
 *
 * `limit` is in it because the position a cursor carries is expressed in pages of the size it was
 * minted for — honouring one across a resize returns the wrong window rather than a rejected
 * parameter. `useListQuery` restarts the walk on a page-size change for the same reason.
 */
function queryKey(params: AuditListParams, sort: string, limit: number): string {
  return JSON.stringify([
    sort,
    limit,
    params.category ?? '',
    params.entity_type ?? '',
    params.action ?? '',
    params.occurred_from ?? '',
    params.occurred_to ?? '',
  ]);
}

function normalizeSort(sort: string | undefined): { key: string; descending: boolean } {
  const raw = sort?.trim() || AUDIT_DEFAULT_SORT;
  const descending = raw.startsWith('-');
  const key = descending ? raw.slice(1) : raw;
  // An unallowlisted sort key is a 422, exactly as `validate_sort` answers server-side (§2.4).
  if (!(AUDIT_SORT_KEYS as readonly string[]).includes(key)) {
    throw new AuditQueryError(`sort must be one of ${AUDIT_SORT_KEYS.join(', ')}`);
  }
  return { key, descending };
}

function matches(event: AuditEventItem, params: AuditListParams): boolean {
  if (params.category && event.category !== params.category) return false;
  if (params.entity_type && event.entity_type !== params.entity_type) return false;
  if (params.action && event.action !== params.action) return false;
  // Inclusive bounds on an instant. ISO-8601 UTC strings compare lexicographically, which is why
  // the wire format is the one the trail stores rather than a parsed `Date`.
  if (params.occurred_from && event.occurred_at < params.occurred_from) return false;
  if (params.occurred_to && event.occurred_at > params.occurred_to) return false;
  return true;
}

/**
 * One page of the trail. Synchronous and pure, so the cursor and paging rules are testable without
 * a clock or a transport.
 */
export function listAuditEvents(
  events: readonly AuditEventItem[],
  params: AuditListParams = {},
): AuditEventPage {
  const limit = checkLimit(params.limit ?? AUDIT_LIST_LIMIT, AUDIT_LIST_MAX_LIMIT, fail);
  if (params.category && !(AUDIT_CATEGORIES as readonly string[]).includes(params.category)) {
    // `security` lands here too: it is a real category, and it is *not* on this surface (§5.1).
    throw new AuditQueryError('category is not readable on this surface');
  }

  const sort = normalizeSort(params.sort);
  const key = queryKey(params, `${sort.descending ? '-' : ''}${sort.key}`, limit);

  const offset = offsetFor(params.cursor, key, fail);

  const matched = events.filter((event) => matches(event, params));
  matched.sort((left, right) => {
    const compare =
      sort.key === 'sequence'
        ? left.sequence - right.sequence
        : left.occurred_at.localeCompare(right.occurred_at);
    // `id` breaks the tie, always — the server appends it so a page boundary is stable when many
    // events share an `occurred_at` to the microsecond.
    return (sort.descending ? -compare : compare) || left.id.localeCompare(right.id);
  });

  // `limit + 1` rows, return `limit`: `has_more` is derived, never counted (§2.1).
  const window = matched.slice(offset, offset + limit + 1);
  const hasMore = window.length > limit;

  return {
    items: window.slice(0, limit),
    page: {
      limit,
      has_more: hasMore,
      next_cursor: hasMore ? encodeCursor({ v: 1, k: key, offset: offset + limit }) : null,
    },
  };
}

function abortError(): DOMException {
  return new DOMException('The audit query was aborted', 'AbortError');
}

/** A cancellable delay, so an abandoned request really is abandoned. */
function wait(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(abortError());
      return;
    }
    let timer: ReturnType<typeof setTimeout>;
    const onAbort = () => {
      clearTimeout(timer);
      reject(abortError());
    };
    timer = setTimeout(() => {
      signal.removeEventListener('abort', onAbort);
      resolve();
    }, ms);
    signal.addEventListener('abort', onAbort, { once: true });
  });
}

export type AuditLoader = (
  params: AuditListParams,
  signal: AbortSignal,
) => Promise<AuditEventPage>;

export type AuditDetailLoader = (event: AuditEventItem, signal: AbortSignal) => Promise<AuditEventDetail>;

/**
 * The list loader the screen is given. This is the seam the real `fetch` goes through, which is why
 * the screen never builds a URL: parameters in, one page out, and a rejection the screen renders as
 * a state rather than as a crash.
 */
export function createAuditLoader(
  events: readonly AuditEventItem[],
  delayMs = AUDIT_LIST_DELAY_MS,
): AuditLoader {
  return async (params, signal) => {
    // The delay comes first so a rejected query fails the way a real 422 does: after the round
    // trip, with the table already showing its pending rows.
    await wait(delayMs, signal);
    if (signal.aborted) throw abortError();
    return listAuditEvents(events, params);
  };
}

/**
 * The detail loader. A **second request**, on purpose: `changes` and `context` are JSON columns a
 * list must not return (api-conventions §3), and most rows are never expanded. `occurred_at` goes
 * with the id because the table is partitioned by it — the endpoint takes both.
 */
export function createAuditDetailLoader(
  details: Readonly<Record<string, AuditEventDetail>>,
  delayMs = AUDIT_LIST_DELAY_MS,
): AuditDetailLoader {
  return async (event, signal) => {
    await wait(delayMs, signal);
    if (signal.aborted) throw abortError();
    const found = details[event.id];
    if (!found) throw new Error('This event could no longer be read');
    return found;
  };
}

/**
 * How an actor reads in a table: the type, then the tail of the id.
 *
 * Not a name, and not by omission — the row does not hold one (§5.2). A trail that stored the
 * display name would keep personal data for the trail's retention period and would still be wrong
 * the moment the person was renamed. The full id is in the detail panel for anyone who needs it.
 */
export function actorLabel(event: Pick<AuditEventItem, 'actor_user_id'> & Partial<Pick<AuditEventItem, 'actor_type'>>): string | null {
  if (!event.actor_user_id) return event.actor_type ?? null;
  const tail = event.actor_user_id.replaceAll('-', '').slice(-6);
  return `${event.actor_type ?? 'user'} ·${tail}`;
}

/** The entity a row is about: its type and, when there is one, the tail of its id. */
export function entityLabel(event: Pick<AuditEventItem, 'entity_id' | 'entity_type'>): string {
  if (!event.entity_id) return event.entity_type;
  return `${event.entity_type} ·${event.entity_id.replaceAll('-', '').slice(-6)}`;
}
