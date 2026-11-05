'use client';

import { useEffect, useMemo, useState, type ReactNode } from 'react';
import {
  Button,
  Card,
  ColumnPicker,
  DataTable,
  ExportMenu,
  FilterBar,
  Notice,
  PageHeader,
  Pager,
  Select,
  serializeSort,
  useColumnPreferences,
  useFormatters,
  useListQuery,
  type AppliedFilter,
  type Column,
  type ErrorStatus,
  type Tone,
} from '@janso/ui';
import {
  AUDIT_CATEGORIES,
  AUDIT_DEFAULT_SORT,
  AUDIT_ENTITY_TYPES,
  AUDIT_LIST_LIMIT,
  AuditQueryError,
  actorLabel,
  createAuditDetailLoader,
  createAuditLoader,
  entityLabel,
  type AuditDetailLoader,
  type AuditEventItem,
  type AuditEventPage,
  type AuditListParams,
  type AuditLoader,
} from '../lib/audit-events';
import { AuditApiError, liveAuditLoader, liveAuditDetailLoader, liveAuditExporter, type AuditExporter } from '../lib/audit-api';
import type { AuditTrail } from '../lib/audit-trail';
import { AuditEventPanel } from './AuditEventPanel';
import { platformAuditLoader, platformAuditDetailLoader } from '../lib/platform-audit-api';

/** Which categories `audit.read` covers, as the filter offers them. */
const CATEGORY_LABEL: Readonly<Record<string, string>> = {
  money: 'Money',
  admin: 'Administration',
  access: 'Access',
  system: 'System',
  security: 'Security',
};

/**
 * The category's tone. `money` is the one that carries weight — it is a change to a figure someone
 * will be held to — and `access` is what an investigation starts from. Neither is a *warning*: an
 * audit row is a record of something that happened correctly until proven otherwise, so nothing
 * here is toned danger.
 */
const CATEGORY_TONE: Readonly<Record<string, Tone>> = {
  money: 'brand',
  admin: 'neutral',
  access: 'info',
  system: 'neutral',
};

/** How far back the reader is looking. The instant is computed when the choice is made. */
const RANGES = [
  { value: 'any', label: 'Any time', hours: 0 },
  { value: '24h', label: 'Last 24 hours', hours: 24 },
  { value: '7d', label: 'Last 7 days', hours: 24 * 7 },
  { value: '30d', label: 'Last 30 days', hours: 24 * 30 },
] as const;

const HOUR = 3_600_000;

/**
 * The columns, declared once at module scope.
 *
 * Static: a `Column` is data — what the field *is* — and the table decides how it renders
 * (design-system §5.11). Nothing request-scoped is captured here, which is what makes it safe to
 * hold outside the component, and `useColumnPreferences` needs the identity to be stable anyway.
 */
const COLUMNS: readonly Column<AuditEventItem>[] = [
  {
    key: 'occurred_at',
    header: 'Recorded',
    /*
     * `datetime`, not `relative`. An auditor cites an instant, and this column is rendered on the
     * server first — "2 hours ago" computed there and again in the browser would disagree, which is
     * a hydration mismatch. The elapsed form is prose inside the expanded panel, where the render
     * only ever happens client-side.
     */
    type: 'datetime',
    sortable: true,
    locked: true,
    width: '13rem',
  },
  {
    key: 'category',
    header: 'Category',
    type: 'status',
    label: (value) => CATEGORY_LABEL[value] ?? value,
    tone: (value) => CATEGORY_TONE[value] ?? 'neutral',
    width: '9rem',
  },
  { key: 'action', header: 'Action', type: 'code', width: '14rem' },
  {
    key: 'entity',
    header: 'Subject',
    value: (event) => entityLabel(event),
    description: 'The record the event is about, and the tail of its id.',
    truncate: true,
  },
  {
    key: 'actor',
    header: 'Actor',
    /*
     * An id, never a name. The trail stores `actor_user_id` and nothing else about the person
     * (docs/audit.md §5.2, CLAUDE.md §6.9) — resolving it to a name here would mean a lookup per
     * row against a service that may have renamed or anonymised them since.
     */
    value: (event) => actorLabel(event),
    description: 'The account that caused the event. Names are resolved separately, never stored here.',
    width: '11rem',
  },
  {
    key: 'sequence',
    header: 'Chain',
    type: 'quantity',
    // A position, so no decimals — and grouped by the reader's own grouping like every figure.
    precision: 0,
    sortable: true,
    description: 'Position in this tenant’s hash chain.',
    width: '8rem',
  },
  { key: 'source_service', header: 'Service', type: 'text', hidden: true, width: '9rem' },
  { key: 'trace_id', header: 'Trace', type: 'code', hidden: true, truncate: true },
];

const FILTER_KEYS = ['category', 'entity_type', 'occurred_from'] as const;

/**
 * The audit log (docs/audit.md §1, design-system §5.11).
 *
 * Read-only by construction, and the one screen that shows what the shared table is for: cursor
 * paging with no total, typed filters instead of a free-text box, a lazily-loaded detail panel per
 * row, and an export downloaded from the server-authorized export response.
 *
 * Three things it deliberately does not do:
 *
 *  - **No search box.** The endpoint has no `q`. Substring-scanning an append-only partitioned table
 *    is the query that takes the database down (api-conventions §2.3), so the filters are typed and
 *    indexed and the screen offers exactly those.
 *  - **No selection, and no row verbs.** An audit row cannot be edited, voided or deleted — that is
 *    what makes it evidence (§2.2). A kebab here would have nothing to put in it.
 *  - **No `security` category.** It lives behind `audit.read_security` on its own surface (§5.1), so
 *    a reader holding plain `audit.read` is never offered it — including in an export.
 *
 * `trail` is a prop, resolved per request by the page's Server Component: a client component
 * reaching for module-scope data would share one tenant's trail across every request the server
 * process handles (CLAUDE.md §5.3). It arrives as **data**, not as a loader, because a function
 * cannot cross the server/client boundary — so the loaders are built here.
 */
export function AuditEvents({
  trail,
  load: injectedLoad,
  loadDetail: injectedDetail,
  exportData: injectedExport,
  companyId, entityId, entityType,
  platform = false,
  navigation,
}: {
  trail?: AuditTrail;
  companyId?: string;
  entityId?: string;
  entityType?: string;
  platform?: boolean;
  exportData?: AuditExporter;
  /**
   * The transport, overridable. The page never passes these — it passes the trail. They exist
   * because the loader is the seam the real `fetch` goes through (`lib/audit-events`), and a test
   * needs to drive the states the stand-in cannot produce on request: a rejected cursor, a 500.
   */
  load?: AuditLoader;
  loadDetail?: AuditDetailLoader;
  navigation?: ReactNode;
}) {
  const format = useFormatters();
  /* Memoized on the payload: the fetch effect depends on the loader's identity, so one rebuilt on
   * every render would re-request the page on every render. */
  const load = useMemo(
    () => injectedLoad ?? (trail ? createAuditLoader(trail.events) : platform ? platformAuditLoader(entityId) : liveAuditLoader(companyId, entityId)),
    [injectedLoad, trail, companyId, entityId, platform],
  );
  const loadDetail = useMemo(
    () => injectedDetail ?? (trail ? createAuditDetailLoader(trail.details) : platform ? platformAuditDetailLoader() : liveAuditDetailLoader()),
    [injectedDetail, trail, platform],
  );
  const [page, setPage] = useState<AuditEventPage | null>(null);
  const [pending, setPending] = useState(true);
  const [error, setError] = useState<ErrorStatus | null>(null);
  const [errorDetail, setErrorDetail] = useState<string | null>(null);
  const [range, setRange] = useState<string>('any');
  const [exported, setExported] = useState<string | null>(null);
  const [exportPending, setExportPending] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const exportData = useMemo(() => injectedExport ?? liveAuditExporter(companyId, entityId), [injectedExport, companyId, entityId]);
  /* Bumped by "Try again". It is what makes the fetch effect run again when nothing about the query
   * changed — see `retry` below. */
  const [attempt, setAttempt] = useState(0);

  const query = useListQuery({
    initial: {
      filters: entityType ? { entity_type: entityType } : {},
      // The endpoint's own default, restated so the first request and the header arrow agree.
      sort: [{ key: 'occurred_at', direction: 'desc' }],
      limit: AUDIT_LIST_LIMIT,
    },
    meta: page?.page ?? null,
  });

  const prefs = useColumnPreferences('audit-events', COLUMNS);

  /*
   * The request. Assembled from the query handle rather than from `params`, because the loader takes
   * typed parameters and not a URL — building a query string here and parsing it there would be two
   * conversions to keep in step.
   */
  const request = useMemo<AuditListParams>(() => {
    const filters = query.filters;
    const one = (key: string): string | undefined => {
      const value = filters[key];
      return typeof value === 'string' && value !== '' ? value : undefined;
    };
    return {
      category: one('category'),
      entity_type: entityType ?? one('entity_type'),
      occurred_from: one('occurred_from'),
      sort: serializeSort(query.sort) || AUDIT_DEFAULT_SORT,
      limit: query.limit,
      cursor: query.cursor,
    };
  }, [query.filters, query.sort, query.limit, query.cursor, entityType]);

  useEffect(() => {
    const controller = new AbortController();
    setPending(true);
    load(request, controller.signal)
      .then((result) => {
        if (controller.signal.aborted) return;
        setPage(result);
        setError(null);
        setErrorDetail(null);
        setPending(false);
      })
      .catch((failure: unknown) => {
        // Abandoned because the query changed under it — not a failure, and the next request is
        // already in flight, so leaving `pending` set is correct.
        if (controller.signal.aborted) return;
        if (failure instanceof DOMException && failure.name === 'AbortError') return;
        /*
         * A 422 here is a parameter the server will not use — most often a cursor that no longer
         * describes this query (§2.1). It is recoverable: the rows are all still there, only the
         * position was lost, which is what `restart` gets back.
         */
        setError(failure instanceof AuditApiError ? (failure.status === 401 ? 401 : failure.status === 403 ? 403 : failure.status === 422 ? 422 : 500) : failure instanceof AuditQueryError ? 422 : 500);
        setErrorDetail(failure instanceof Error ? failure.message : null);
        setPending(false);
      });
    return () => controller.abort();
  }, [load, request, attempt]);

  /**
   * Re-request the page after a failure.
   *
   * `query.restart` alone is not enough: it is a no-op when the walk is already at its head
   * (`useListQuery`), which is exactly where a first-load 422 or 500 leaves the reader — so "Try
   * again" would do nothing on the one page it is most needed. The nonce is what makes the effect
   * run again; `restart` is still right, because the most likely 422 is a cursor the server refused
   * and the recovery for that is the first page of the same query (api-conventions §2.1). Both land
   * in one update, so it stays one request either way.
   */
  function retry(): void {
    setAttempt((value) => value + 1);
    query.restart();
  }

  /* Every predicate in force, as chips — a list that is filtered without saying so is why a reader
   * concludes the record is missing (design-system §5.11). */
  const applied = useMemo<AppliedFilter[]>(() => {
    const chips: AppliedFilter[] = platform ? [] : [
      {
        id: '__surface',
        label: 'Category',
        value: 'Security events excluded',
        operator: '',
        /*
         * Screen-imposed and unremovable, because it is not this screen's choice: security events
         * are a separate surface behind `audit.read_security` (§5.1). Stated rather than silent —
         * a reader looking for a failed sign-in needs to know why it is not here.
         */
        fixed: true,
      },
    ];
    const category = query.filters.category;
    if (typeof category === 'string' && category !== '') {
      chips.push({
        id: 'category',
        label: 'Category',
        value: CATEGORY_LABEL[category] ?? category,
      });
    }
    const entity = entityType ?? query.filters.entity_type;
    if (typeof entity === 'string' && entity !== '') {
      chips.push({ id: 'entity_type', label: 'Subject', value: entity, fixed: !!entityType });
    }
    const from = query.filters.occurred_from;
    if (typeof from === 'string' && from !== '') {
      chips.push({
        id: 'occurred_from',
        label: 'Recorded',
        operator: 'on or after',
        // The bound itself, formatted — the instant was fixed when the range was chosen, so
        // repeating the range's own words ("last 24 hours") would drift as the page stays open.
        value: format.dateTime(from),
      });
    }
    return chips;
  }, [query.filters, format, platform, entityType]);

  function removeFilter(id: string): void {
    if (id === 'occurred_from') setRange('any');
    query.setFilter(id, null);
  }

  function clearFilters(): void {
    setRange('any');
    query.clearFilters();
  }

  function applyRange(value: string): void {
    const choice = RANGES.find((candidate) => candidate.value === value) ?? RANGES[0];
    setRange(choice.value);
    /*
     * The instant is computed here, in an event handler, and never during a render: a bound derived
     * from the clock while rendering would differ between the server's render and the browser's.
     */
    query.setFilter(
      'occurred_from',
      choice.hours === 0 ? null : new Date(Date.now() - choice.hours * HOUR).toISOString(),
    );
  }

  async function exportCurrent(): Promise<void> {
    setExportPending(true);
    setExportError(null);
    try {
      const result = await exportData(request);
      setExported(result.count + ' events exported.' + (result.truncated ? ' The export reached its limit; narrow the filters for the remaining events.' : ''));
    } catch (failure) {
      setExportError(failure instanceof Error ? failure.message : 'Export failed');
    } finally {
      setExportPending(false);
    }
  }

  const rows = page?.items ?? [];

  return (
    <div className="janso-page">
      {navigation}
      <PageHeader
        overline="Administer"
        title={platform ? 'Platform history' : 'Audit logs'}
        lede={platform ? 'Administrative changes, access and account decisions within your platform permissions.' : 'Every state change, in the order it was recorded. Rows are append-only and cannot be edited from here.'}
      />

      {exported ? (
        <Notice
          tone="info"
          title="Export ready"
          onDismiss={() => setExported(null)}
        >
          {exported}
        </Notice>
      ) : null}

      {exportError ? <Notice tone="danger" title="Export failed">{exportError}</Notice> : null}
      <Card className="janso-event-log">
      <div className="janso-event-log__toolbar">
      <FilterBar
        applied={applied}
        onRemove={removeFilter}
        onClearAll={clearFilters}
        actions={
          <>
            <Button variant="ghost" disabled={pending} onClick={retry}>{platform ? 'Refresh history' : 'Refresh audit logs'}</Button>
            <ColumnPicker
              columns={prefs.choices}
              hidden={prefs.hidden}
              onToggle={prefs.toggle}
              onReset={prefs.reset}
            />
            {/* Its own key: reading a page of the trail and taking the whole trail away are
              * different capabilities, and the export endpoint enforces `audit.export` (§5.1). */}
            {!platform ? <ExportMenu
              permission="audit.export"
              formats={[{ id: "json", label: "JSON" }]}
              onExport={() => { void exportCurrent(); }}
              disabledReason={exportPending ? 'Export in progress' : rows.length === 0 ? 'There is nothing to export' : undefined}
            /> : null}
          </>
        }
      >
        <Select
          inline
          label="Category"
          value={typeof query.filters.category === 'string' ? query.filters.category : ''}
          options={[
            { value: '', label: 'All categories' },
            ...(platform ? ['admin', 'security', 'access', 'system'] : AUDIT_CATEGORIES).map((category) => ({
              value: category,
              label: CATEGORY_LABEL[category] ?? category,
            })),
          ]}
          onChange={(value) => query.setFilter('category', value === '' ? null : value)}
        />
        <Select
          inline
          label="Subject"
          value={entityType ?? (typeof query.filters.entity_type === 'string' ? query.filters.entity_type : '')}
          options={[
            ...(entityType ? [] : [{ value: '', label: 'All subjects' }]),
            ...(entityType ? [entityType] : platform ? ['tenant', 'account_review', 'platform_installation', 'reference_revision'] : AUDIT_ENTITY_TYPES).map((entity) => ({ value: entity, label: entity })),
          ]}
          onChange={(value) => query.setFilter('entity_type', value === '' ? null : value)}
        />
        <Select
          inline
          label="Recorded"
          value={range}
          options={RANGES.map((option) => ({ value: option.value, label: option.label }))}
          onChange={applyRange}
        />
      </FilterBar>
      </div>
      <p className="janso-event-log__note">Recent changes may take a moment to appear. Open a row to compare recorded values and inspect its evidence.</p>

      <DataTable
        caption="Audit events, newest first"
        columns={prefs.columns}
        rows={rows}
        rowId={(event) => event.id}
        rowLabel={(event) => `${event.action} at ${format.dateTime(event.occurred_at)}`}
        sort={query.sort}
        onSortChange={query.setSort}
        density="compact"
        loading={pending}
        skeletonRows={8}
        error={error}
        errorDetail={errorDetail}
        onRetry={retry}
        filtered={query.filtered}
        emptyTitle="No events match these filters"
        emptyBody="No recorded events match the category, subject and period selected."
        onClearFilters={clearFilters}
        renderDetail={(event) => <AuditEventPanel event={event} load={loadDetail} />}
        pinFirstColumn
        /* No `selectable`, and no `rowActions`: see this component's docblock. */
      />

      {!error && <Pager
        count={rows.length}
        from={query.page.from}
        limit={query.limit}
        hasPrevious={query.page.hasPrevious}
        hasNext={query.page.hasNext}
        onPrevious={query.previousPage}
        onNext={query.nextPage}
        onLimitChange={query.setLimit}
        busy={pending}
        noun="event"
      />}
      </Card>
    </div>
  );
}
