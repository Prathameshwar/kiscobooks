'use client';

import { createContext, useContext, useEffect, useId, useRef, useState, type ReactNode, type FormEvent } from 'react';
import { Badge, Button, Card, CardBody, CardFooter, CardHeader, ConfirmDialog, DataTable, Disclosure, ErrorState, FieldGrid, FilterBar, Modal, Notice, ReviewList, Select, Skeleton, TextField, Toolbar, asErrorStatus, pluralNoun, pluralOf, type Column, type Tone } from '@janso/ui';
import { notificationCall, notificationPermission, type Job, type NotificationOwner, type Page } from '../../lib/notification-api';
import { notificationRecordLink, notificationRoot } from '../../lib/notification-navigation';
import { requestFailure, type RequestFailure } from '../../lib/service-call';

export const ALL_COMPANIES = '00000000-0000-0000-0000-000000000000';
export type AdminContext = {
  owner: NotificationOwner; permissions: readonly string[]; companyId?: string; query: URLSearchParams;
  can: (family: string, action?: string) => boolean;
  href: (path?: string) => string;
};
const Context = createContext<AdminContext | null>(null);
export function NotificationScope({ owner, permissions, companyId, query, children }: Omit<AdminContext, 'can' | 'href'> & { children: ReactNode }) {
  return <Context.Provider value={{ owner, permissions, companyId, query,
    can: (family, action = 'read') => permissions.includes(notificationPermission(owner, family, action)),
    href: (path = '') => notificationRoot(owner) + (path ? '/' + path : ''),
  }}>{children}</Context.Provider>;
}
export function useNotifications() { const scope = useContext(Context); if (!scope) throw new Error('Notification scope required'); return scope; }
export function useResource<T>(resource?: string) {
  const { owner } = useNotifications();
  const [state, setState] = useState<{ data?: T; error?: RequestFailure; loading: boolean; resource?: string }>({ loading: !!resource });
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setState({ loading: !!resource, resource });
    if (resource) notificationCall<T>(owner, resource, 'GET', undefined, undefined, controller.signal)
      .then(data => { if (!controller.signal.aborted) setState({ data, loading: false, resource }); })
      .catch(error => { if (!controller.signal.aborted) setState({ error: requestFailure(error, 'notification'), loading: false, resource }); });
    return () => controller.abort();
  }, [owner, resource, revision]);
  return { ...(state.resource === resource ? state : { loading: !!resource }), refresh: () => setRevision(value => value + 1) };
}
export function ResourceState({ state, children }: { state: { loading: boolean; error?: RequestFailure; refresh: () => void }; children?: ReactNode }) {
  if (state.loading) return <div role="status" aria-label="Loading notifications"><Skeleton /></div>;
  if (state.error?.status === 404) return <Notice tone="danger">This notification record was not found in the current scope.</Notice>;
  if (state.error) return <ErrorState status={asErrorStatus(state.error.status)} detail={state.error.message} action={<Button onClick={state.refresh}>Try again</Button>} />;
  return <>{children}</>;
}
export function useActions() {
  const { owner } = useNotifications();
  const [busy, setBusy] = useState(false), [error, setError] = useState<RequestFailure>(), [message, setMessage] = useState('');
  const alive = useRef(true), locked = useRef(false), identities = useRef(new Map<string, string>());
  const controller = useRef(new AbortController());
  useEffect(() => { alive.current = true; if (controller.current.signal.aborted) controller.current = new AbortController(); const current = controller.current; return () => { alive.current = false; current.abort(); }; }, []);
  async function send<T>(resource: string, method: string, body?: unknown, idempotent = false): Promise<T> {
    const fingerprint = resource + ':' + JSON.stringify(body ?? {});
    let key: string | undefined;
    if (idempotent) { key = identities.current.get(fingerprint) ?? crypto.randomUUID(); identities.current.set(fingerprint, key); }
    const result = await notificationCall<T>(owner, resource, method, body, key, controller.current.signal);
    identities.current.delete(fingerprint);
    return result;
  }
  async function run(work: () => Promise<void>, success = 'Changes saved.'): Promise<boolean> {
    if (locked.current || !alive.current) return false;
    locked.current = true; setBusy(true); setError(undefined); setMessage('');
    try { await work(); if (alive.current) setMessage(success); return true; }
    catch (value) { if (alive.current) setError(requestFailure(value, 'notification')); return false; }
    finally { locked.current = false; if (alive.current) setBusy(false); }
  }
  return { busy, error, message, send, run };
}
export type Actions = ReturnType<typeof useActions>;
export function Feedback({ action }: { action: Actions }) {
  return <>{action.error && <Notice tone="danger">{action.error.message}{action.error.status === 409 && ' Refresh the record before changing it again.'}</Notice>}{action.message && <Notice tone="success">{action.message}</Notice>}</>;
}
export const readable = (value?: string | null) => value ? value.replaceAll('_', ' ').replaceAll('.', ' / ') : 'Not available';
/*
 * Four tones, not two. A delivery that is *in flight* is not a delivery that failed and not one
 * that arrived, and "sending" rendered in the same grey as "cancelled" is how an unresolved
 * provider outcome gets read as a finished one — the single state this console most has to keep
 * distinguishable (notification §2, recovery).
 */
const SETTLED = ['active', 'verified', 'approved', 'completed', 'delivered', 'read', 'processed', 'granted', 'ready', 'enabled', 'healthy'];
const FAILED = ['failed', 'rejected', 'error', 'denied', 'withdrawn', 'bounced', 'unreachable'];
const IN_FLIGHT = ['pending', 'processing', 'sending', 'scheduled', 'queued', 'running', 'accepted', 'retry_wait'];
const WITHHELD = ['unmatched', 'suppressed', 'expired', 'unknown', 'degraded'];
export const stateTone = (value: string): Tone =>
  SETTLED.includes(value) ? 'success' : FAILED.includes(value) ? 'danger' : IN_FLIGHT.includes(value) ? 'info' : WITHHELD.includes(value) ? 'warn' : 'neutral';
export function StateBadge({ value }: { value: string }) {
  return <Badge tone={stateTone(value)}>{readable(value)}</Badge>;
}
export function Surface({ icon, title, subtitle, badge, action, footer, children }: { icon?: ReactNode; title: string; subtitle?: string; badge?: ReactNode; action?: ReactNode; footer?: ReactNode; children: ReactNode }) {
  // `janso-flow` inside the body: a card's own padding is all `CardBody` carries, so without it
  // every paragraph, table and notice in a record sits flush against the next one.
  return <Card><CardHeader icon={icon} title={title} subtitle={subtitle} badge={badge} action={action} /><CardBody><div className="janso-flow">{children}</div></CardBody>{footer ? <CardFooter>{footer}</CardFooter> : null}</Card>;
}
/** Label/value facts, in the same list a record detail uses everywhere else in the console. */
export function Facts({ items }: { items: readonly { label: string; value: ReactNode }[] }) {
  return <ReviewList items={items.filter(item => item.value !== null && item.value !== undefined && item.value !== '')} />;
}
/** A record's verbs, as one row. The caller orders them: the primary action first. */
export function ActionBar({ children }: { children: ReactNode }) {
  return <Toolbar left={children} />;
}
/** Read-only verbatim content — message text, an HTML source — in the shared preview panel. */
export function Verbatim({ caption, children }: { caption: string; children: string }) {
  return <figure className="janso-preview"><figcaption className="janso-preview__caption">{caption}</figcaption><pre className="janso-preview__text">{children}</pre></figure>;
}
export function References({ entries }: { entries: Record<string, string | null | undefined> }) {
  return <Disclosure summary="Reference details"><dl className="janso-preview__grid">{Object.entries(entries).map(([label, value]) => <div className="janso-preview__row" key={label}>
    <dt className="janso-preview__key">{label}</dt><dd className="janso-preview__value janso-table__code">{value ?? 'Not available'}</dd></div>)}</dl></Disclosure>;
}
/*
 * A list, its empty state and its pager. No `action` slot: the card header above already carries
 * the one verb a list has, and the same button in both places gave every screen two controls with
 * one name — ambiguous to anyone navigating by control, and noise to everyone else.
 */
export function NotificationTable<T extends { id: string }>({ title, columns, state, path, noun = 'record', nounPlural, empty, filtered }: {
  title: string; columns: readonly Column<T>[]; state: ReturnType<typeof useResource<Page<T>>>;
  /** The area path a cursor link navigates to. A panel whose cursor is client state omits it and renders `LocalPages`. */
  path?: string;
  /** What a row is, singular, for the pager's range and the empty copy. */
  noun?: string; nounPlural?: string; empty?: ReactNode; filtered?: boolean;
}) {
  const { owner, query } = useNotifications();
  const rows = state.data?.items ?? [], plural = nounPlural ?? pluralOf(noun);
  const linked = path ? columns.map(column => column.type === 'link' && column.href ? {
    ...column, href: (row: T) => notificationRecordLink(owner, column.href!(row), path, query),
  } : column) : columns;
  // The error case keeps `ResourceState`'s wording (a 404 is a scope answer, not an outage); the
  // loading case goes through the table so the columns stay on screen while a page is in flight.
  if (state.error) return <ResourceState state={state} />;
  return <><DataTable caption={title} columns={linked} rows={rows} rowId={row => row.id} density="compact" loading={state.loading}
    filtered={filtered} emptyTitle={'No ' + plural + ' found'} emptyBody={empty} />
    {path ? <CursorPages path={path} page={state.data?.page} count={rows.length} noun={noun} nounPlural={nounPlural} loading={state.loading} /> : null}
  </>;
}
/*
 * Keyset paging as the rest of the console draws it (`Pager`), but with links: an area reached by
 * URL keeps its cursor in the URL, so a page stays shareable and the back button steps back
 * through pages. There is no total and no page number — the API returns no unconditional count
 * (docs/api-conventions.md §2.1).
 */
function CursorPages({ path, page, count, noun, nounPlural, loading }: { path: string; page?: Page<{ id: string }>['page']; count: number; noun: string; nounPlural?: string; loading: boolean }) {
  const { href, query } = useNotifications();
  const next = new URLSearchParams(query); next.set('cursor', page?.next_cursor ?? '');
  const first = new URLSearchParams(query); first.delete('cursor');
  const back = query.has('cursor'), forward = !!page?.has_more && !!page.next_cursor;
  if (!back && !forward && count === 0 && !loading) return null;
  return <nav className="janso-pager" aria-label={noun + ' pages'}>
    {/* Never "No deliveries" over a table of loading skeletons: a page opened at a cursor has no
      * rows *yet*, and a range stated before the answer arrives is a range that will be wrong. */}
    <p className="janso-pager__range">{loading ? 'Loading…' : count ? `Showing ${count} ${pluralNoun(noun, count, nounPlural)}` : `No ${nounPlural ?? pluralOf(noun)}`}</p>
    <div className="janso-pager__controls">
      {back ? <a className="janso-btn janso-btn--ghost" href={href(path) + (first.size ? '?' + first : '')}>First page</a> : null}
      {forward ? <a className="janso-btn janso-btn--ghost" href={href(path) + '?' + next}>Next page</a> : null}
    </div>
  </nav>;
}
/*
 * The same pager for a panel whose cursor is client state rather than part of the address — an
 * attempt history inside a delivery, say. Drawn identically to `CursorPages`, because a reader
 * should not have to learn two paging controls on one page.
 */
export function LocalPages({ cursor, next, setCursor, name }: { cursor: string | null; next?: string | null; setCursor: (cursor: string | null) => void; name: string }) {
  if (!cursor && !next) return null;
  return <nav className="janso-pager" aria-label={name + ' pages'}>
    <p className="janso-pager__range">{cursor ? `A later page of ${pluralOf(name)}` : `First page of ${pluralOf(name)}`}</p>
    <div className="janso-pager__controls">
      {cursor ? <Button variant="ghost" onClick={() => setCursor(null)}>First {name} page</Button> : null}
      {next ? <Button variant="ghost" onClick={() => setCursor(next)}>Next {name} page</Button> : null}
    </div>
  </nav>;
}
export type FormField = { name: string; label: string; type?: 'text' | 'number' | 'datetime-local' | 'textarea' | 'select'; required?: boolean; help?: string; options?: { value: string; label: string }[]; min?: number; max?: number; maxLength?: number };
export type FormValues = Record<string, string>;
export function Editor({ title, fields, initial = {}, submit, onClose, onChange, children }: {
  title: string; fields: FormField[] | ((values: FormValues) => FormField[]); initial?: FormValues;
  submit: (values: FormValues, action: Actions) => Promise<void>; onClose: () => void;
  onChange?: (values: FormValues, name: string) => FormValues; children?: ReactNode;
}) {
  const action = useActions(); const [values, setValues] = useState(initial);
  const visible = typeof fields === 'function' ? fields(values) : fields;
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (visible.some(field => field.required && !values[field.name]?.trim())) {
      await action.run(async () => { throw { status: 422, message: 'Complete the required fields.' }; }); return;
    }
    if (await action.run(() => submit(values, action))) onClose();
  }
  // Cancel then the committing action, with the routed editors' wording — the same reading
  // order whether a change is made in this dialog or on a page of its own.
  return <Modal open title={title} onClose={onClose} busy={action.busy} size="lg"><Feedback action={action} />{children}
    <form aria-label={title} onSubmit={save}><FieldGrid disabled={action.busy}>{visible.map(field => {
      const update = (value: string) => setValues(prior => { const next = { ...prior, [field.name]: value }; return onChange ? onChange(next, field.name) : next; });
      const problem = action.error?.fields?.[field.name] ?? action.error?.fields?.['body.' + field.name];
      return <FormControl key={field.name} field={field} value={values[field.name] ?? ''} update={update} error={problem} />;
    })}</FieldGrid><div className="janso-form-actions"><Button variant="ghost" disabled={action.busy} onClick={onClose}>Cancel</Button><Button type="submit" loading={action.busy} loadingLabel="Saving…">Save changes</Button></div></form>
  </Modal>;
}
function FormControl({ field, value, update, error }: { field: FormField; value: string; update: (value: string) => void; error?: string }) {
  const id = useId();
  if (field.type === 'select') return <Select label={field.label} value={value} onChange={update} options={field.options ?? []} required={field.required} hint={field.help} error={error} />;
  if (field.type === 'textarea') return <div className="janso-field"><label htmlFor={id}>{field.label}</label><textarea id={id} className="janso-input" rows={5} required={field.required} maxLength={field.maxLength} value={value} aria-invalid={!!error} aria-describedby={[field.help ? id + '-hint' : '', error ? id + '-error' : ''].filter(Boolean).join(' ') || undefined} onChange={event => update(event.target.value)} />
    {field.help && <p id={id + '-hint'} className="janso-hint">{field.help}</p>}{error && <p id={id + '-error'} className="janso-error" role="alert">{error}</p>}</div>;
  return <TextField label={field.label} type={field.type ?? 'text'} step={field.type === 'datetime-local' ? '1' : undefined} value={value} required={field.required} min={field.min} max={field.max} maxLength={field.maxLength} hint={field.help} error={error} onChange={event => update(event.target.value)} />;
}
export function ConfirmAction({ title, body, perform, onDone, label = 'Confirm' }: { title: string; body: ReactNode; perform: (action: Actions) => Promise<void>; onDone: () => void; label?: string }) {
  const action = useActions();
  return <ConfirmDialog open title={title} busy={action.busy} error={action.error?.message} onCancel={onDone} confirmLabel={label} onConfirm={async () => { if (await action.run(() => perform(action))) onDone(); }}>{body}</ConfirmDialog>;
}
export function JobStatus({ identity, onComplete }: { identity: string; onComplete?: () => void }) {
  const state = useResource<Job>('jobs/' + identity), count = useRef(0), completed = useRef(false);
  const active = state.data?.status === 'pending' || state.data?.status === 'running';
  useEffect(() => {
    if (state.data && !active && !completed.current) { completed.current = true; onComplete?.(); }
    if (!active || count.current >= 30) return;
    const timer = setTimeout(() => { count.current++; state.refresh(); }, 2000);
    return () => clearTimeout(timer);
  }, [state.data, active]); // Refresh is deliberately bounded; manual checking stays available.
  return <Surface title="Provider check" subtitle="The provider decides the outcome. This panel reports what it has returned so far."
    badge={state.data ? <StateBadge value={state.data.status} /> : undefined}
    action={<Button variant="ghost" onClick={state.refresh} disabled={state.loading}>Check status</Button>}>
    <ResourceState state={state}>{state.data && <><Facts items={[{ label: 'Outcome', value: readable(state.data.reason_code) }]} /><References entries={{ Job: identity }} /></>}</ResourceState>
    {active && count.current >= 30 ? <Notice tone="warning">The check is taking longer than expected. Check its status again when ready.</Notice> : null}</Surface>;
}
export const option = (value: string, label = readable(value)) => ({ value, label });
export const channels = ['email', 'sms', 'whatsapp'];
export const channelField: FormField = { name: 'channel', label: 'Channel', type: 'select', required: true, options: channels.map(value => option(value)) };
export const instant = (value: string) => { const time = new Date(value); if (!value || !Number.isFinite(time.getTime())) throw { status: 422, message: 'Enter a valid date and time.' }; return time.toISOString(); };
export const defaultTime = () => { const now = new Date(); return new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 19); };
export const numeric = (value: string, label: string, min: number, max: number) => { const result = Number(value); if (!value.trim() || !Number.isInteger(result) || result < min || result > max) throw { status: 422, message: `${label} must be a whole number between ${min} and ${max}.` }; return result; };

export function useListResource(resource: string, filters: string[]) {
  const { query } = useNotifications(); const values = new URLSearchParams({ limit: '50' });
  for (const key of ['cursor', ...filters]) { const value = query.get(key); if (value) values.set(key, value); }
  return resource + '?' + values;
}
/*
 * The strip above a list, in the console's own filter layout: the controls on one row, and a chip
 * for every predicate actually in force. A list that is filtered without saying so is the usual
 * cause of "the record is missing", and here a filter can arrive from the URL — from a delivery's
 * "inspect unmatched receipts" link, say — so the reader may never have chosen the one hiding
 * their row. Submission stays a GET: the query lives in the URL, so a filtered list is shareable.
 */
/*
 * Every predicate the allowlist carries, named in the reader's words. The chips are drawn from the
 * *query*, not from the declared fields, because the predicate most likely to hide a row is the one
 * no form on the screen offers: arriving at Recipients from a delivery's "View masked recipient"
 * pins the list to one endpoint, and a screen that showed no chip for it would be filtered in
 * silence. `cursor` is a position and `sort` is an order — neither excludes a row, so neither
 * earns a chip in a group called "filters in force".
 */
const NOT_A_FILTER = ['cursor', 'sort', 'back'];
const FILTER_LABELS: Record<string, string> = {
  status: 'Status', channel: 'Channel', q: 'Search', request_id: 'Request',
  event_key: 'Purpose', provider_account_id: 'Provider', subject_id: 'Subject reference',
  recipient_endpoint_id: 'Recipient endpoint',
};
export function ListFilters({ path, fields }: { path: string; fields: { name: string; label: string; values?: string[] }[] }) {
  const { href, query } = useNotifications();
  const [values, setValues] = useState<FormValues>(() => Object.fromEntries(fields.map(field => [field.name, query.get(field.name) ?? ''])));
  // `fixed`: the predicate is held in the URL and this console navigates by link, so a chip's
  // remove button would have nowhere to report. The form and "Clear filters" are the way to lift one.
  const applied = [...new Set(query.keys())].filter(key => !NOT_A_FILTER.includes(key) && query.get(key))
    .map(key => ({ id: key, label: fields.find(field => field.name === key)?.label ?? FILTER_LABELS[key] ?? readable(key), value: readable(query.get(key)), fixed: true }));
  const set = (name: string) => (value: string) => setValues(prior => ({ ...prior, [name]: value }));
  return <form method="get" action={href(path)} aria-label="Filter list">
    <FilterBar applied={applied} actions={<><Button type="submit">Apply filters</Button>
      {applied.length ? <a className="janso-btn janso-btn--ghost" href={href(path)}>Clear filters</a> : null}</>}>
      {fields.map(field => field.values
        ? <Select key={field.name} label={field.label} name={field.name} value={values[field.name] ?? ''} onChange={set(field.name)} placeholder="All" options={field.values.map(value => option(value))} />
        : <TextField key={field.name} label={field.label} name={field.name} value={values[field.name] ?? ''} onChange={event => set(field.name)(event.target.value)} />)}
    </FilterBar>
  </form>;
}
export function useChoices<T extends { id: string }>(resource?: string) {
  const { owner } = useNotifications(); const state = useResource<Page<T>>(resource ? resource + (resource.includes('?') ? '&' : '?') + 'limit=50' : undefined);
  const [extra, setExtra] = useState<{ resource?: string; items: T[]; cursor?: string | null }>({ items: [] });
  const action = useActions(); const scoped = extra.resource === resource ? extra : { items: [] as T[] };
  const cursor = 'cursor' in scoped ? scoped.cursor : state.data?.page.next_cursor;
  const items = [...(state.data?.items ?? []), ...scoped.items];
  return { items, state, action, cursor, more: () => action.run(async () => {
    if (!resource || !cursor) return;
    const result = await notificationCall<Page<T>>(owner, resource + (resource.includes('?') ? '&' : '?') + 'limit=50&cursor=' + encodeURIComponent(cursor));
    setExtra({ resource, items: [...scoped.items, ...result.items], cursor: result.page.next_cursor });
  }, '') };
}
export function ChoicePages<T extends { id: string }>({ choices, label }: { choices: ReturnType<typeof useChoices<T>>; label: string }) {
  return <><ResourceState state={choices.state} /><Feedback action={choices.action} />{choices.cursor && <Button disabled={choices.action.busy} onClick={() => void choices.more()}>Load more {label}</Button>}</>;
}
