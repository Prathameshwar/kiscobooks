'use client';

import { useEffect, useMemo, useState } from 'react';
import { asErrorStatus, Button, Card, DataTable, ErrorState, FilterBar, Notice, PageHeader, PageNavigation, Pager, type Column } from '@janso/ui';
import { activityLoader, type ActivityItem, type ActivityLoader, type ActivityPage } from '../lib/activity-api';
import { AuditApiError } from '../lib/audit-api';
import { actorLabel, entityLabel } from '../lib/audit-events';
import { logsAndActivitiesPath } from '../lib/logs-navigation';

const categoryLabels: Record<string, string> = { admin: 'Administration', money: 'Money', access: 'Access', system: 'System' };
const columns: Column<ActivityItem>[] = [
  { key: 'occurred_at', header: 'Recorded', type: 'datetime', width: '15rem' },
  { key: 'category', header: 'Category', type: 'status', label: value => categoryLabels[value] ?? value, width: '9rem' },
  { key: 'action', header: 'Action', type: 'code' },
  { key: 'entity_type', header: 'Subject', type: 'custom', render: row => <span title={row.entity_id ?? undefined}>{entityLabel(row)}</span> },
  { key: 'actor_user_id', header: 'Actor', type: 'custom', render: row => <span title={row.actor_user_id ?? undefined}>{actorLabel(row) ?? 'Not recorded'}{row.on_behalf_of_user_id ? <> for <span title={row.on_behalf_of_user_id}>user ·{row.on_behalf_of_user_id.replaceAll('-', '').slice(-6)}</span></> : null}</span>, width: '10rem' },
  { key: 'source_service', header: 'Source', type: 'text', width: '8rem' },
];

type ActivityFeedProps = { company: string; organisation?: boolean; canOrganisation?: boolean; canAudit?: boolean; load?: ActivityLoader };

export function ActivityFeed(props: ActivityFeedProps) {
  return <CompanyActivityFeed key={props.company + ':' + !!props.organisation} {...props} />;
}

function CompanyActivityFeed({ company, organisation = false, canOrganisation = false, canAudit = false, load: supplied }: ActivityFeedProps) {
  const load = useMemo(() => supplied ?? activityLoader(organisation ? null : company), [company, organisation, supplied]);
  const [page, setPage] = useState<ActivityPage | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [previous, setPrevious] = useState<(string | null)[]>([]);
  const [revision, setRevision] = useState(0);
  const [pending, setPending] = useState(true);
  const [failure, setFailure] = useState<AuditApiError | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    setPending(true); setFailure(null);
    load(cursor, controller.signal).then(data => {
      if (!controller.signal.aborted) { setPage(data); setPending(false); }
    }).catch(error => {
      if (!controller.signal.aborted) { setPage(null); setFailure(error instanceof AuditApiError ? error : new AuditApiError(503)); setPending(false); }
    });
    return () => controller.abort();
  }, [load, cursor, revision]);
  useEffect(() => {
    if (cursor || failure?.status === 401 || failure?.status === 403 || failure?.status === 422) return;
    const timer = setInterval(() => { if (!document.hidden && !pending) setRevision(value => value + 1); }, 30_000);
    return () => clearInterval(timer);
  }, [cursor, failure, pending]);
  function first() { if (cursor) setPage(null); setCursor(null); setPrevious([]); setRevision(value => value + 1); }
  return <div className="janso-page">
    <PageNavigation back={{ href: logsAndActivitiesPath, label: 'logs and activities' }} breadcrumbs={[{ label: 'Business overview', href: '/' }, { label: 'Logs and activities', href: logsAndActivitiesPath }, { label: 'Activities' }]} />
    <PageHeader overline="Administer" title="Activities" lede={organisation ? 'Recent recorded changes across your organisation.' : 'Recent recorded changes for the company currently open.'} />
    <Notice tone="info">Recent changes may take a moment to appear. Security events require the separate security audit permission.</Notice>
    <Card className="janso-event-log">
      <div className="janso-event-log__toolbar"><FilterBar actions={<Button variant="ghost" onClick={first} disabled={pending}>Refresh activity</Button>}>
        {canOrganisation && <nav aria-label="Activity scope" className="janso-filter-bar__actions">
          <a href="/activity" className={'janso-btn janso-btn--' + (organisation ? 'ghost' : 'primary')} aria-current={organisation ? undefined : 'page'}>Company activity</a>
          <a href="/activity?scope=organisation" className={'janso-btn janso-btn--' + (organisation ? 'primary' : 'ghost')} aria-current={organisation ? 'page' : undefined}>Organisation activity</a>
        </nav>}
        <p className="janso-meta" role="status" aria-live="polite">{pending ? page ? 'Refreshing activities…' : 'Loading activities…' : cursor ? 'Earlier recorded changes' : 'Recent recorded changes'}</p>
      </FilterBar></div>
      <p className="janso-event-log__note">The recent page updates every 30 seconds. Use the page controls to review earlier changes.</p>
      {failure ? <ErrorState status={asErrorStatus(failure.status)} detail={failure.message} action={<Button variant="ghost" onClick={first}>{failure.status === 422 ? 'Return to recent activity' : 'Try again'}</Button>} />
        : <DataTable caption={organisation ? 'Organisation activity' : 'Company activity'} columns={columns} rows={page?.items ?? []} rowId={row => row.id} loading={pending && !page}
          emptyTitle="No recorded activity" emptyBody="Recorded company changes will appear here when they become available."
          rowActions={canAudit ? row => [{ id: 'audit', label: 'View audit history', href: '/audit?' + new URLSearchParams({ ...(organisation && !row.company_id ? { scope: 'organisation' } : { company_id: row.company_id ?? company }), entity_type: row.entity_type, ...(row.entity_id ? { entity_id: row.entity_id } : {}) }) }] : undefined} />}
      {!failure && <Pager count={page?.items.length ?? 0} limit={50} busy={pending} hasPrevious={previous.length > 0} hasNext={!!page?.page.has_more}
        onPrevious={() => { if (!pending && previous.length) { setPage(null); setCursor(previous.at(-1) ?? null); setPrevious(previous.slice(0, -1)); } }}
        onNext={() => { if (!pending && page?.page.has_more && page.page.next_cursor) { setPage(null); setPrevious([...previous, cursor]); setCursor(page.page.next_cursor); } }} noun="event" />}
    </Card>
  </div>;
}
