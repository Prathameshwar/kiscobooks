'use client';

import { useEffect, useRef, useState } from 'react';
import { Badge, Button, Card, CardBody, CardHeader, DataTable, DEFAULT_DISPLAY_CONFIG,
  DisplayConfigProvider, Notice, PageHeader, PageNavigation, Pager, ReviewList, Select,
  Skeleton, TextField, formatDate, formatMoney, resolvedDisplay, useFormatters, type Column } from '@janso/ui';
import type { components as accounting } from '@janso/api-client/accounting';
import type { components as identity } from '@janso/api-client/identity';
import type { components as reports } from '@janso/api-client/reports';
import { companyCall, companyFailure, openCompany } from '../lib/company-api';
import { productFieldRequest as request } from '../lib/product-fields';
import { administrationBackLabel, administrationLink, administrationReturn } from '../lib/administration-navigation';
import { reportRowLabel } from '../lib/report-labels';
import { canPreviewReportExport, reportDownloadHref, reportExportOptions, trackReportExport } from '../lib/report-exports';

type Year = accounting['schemas']['FiscalYearDetail'];
type Job = reports['schemas']['JobDetail'];
type Row = reports['schemas']['ResultRow'];
type Definition = reports['schemas']['DefinitionDetail'];
type Source = { id: string; status: string; applied_sequence?: number | null };
type SourcePage = { items: Source[]; page?: { next_cursor: string | null } };
const pendingJob = (job: Job | null) => !!job && ['QUEUED', 'RUNNING'].includes(job.status);
const failureText: Record<string, string> = {
  REPORT_VERIFICATION_FAILED: 'The source does not contain verified original books and consecutive financial years. Review the source and calendar before retrying.',
  REPORT_CAPACITY_EXCEEDED: 'The review exceeds this deployment’s report capacity. Ask your administrator to review its configured limits.',
  AUTHORITY_REVOKED: 'Your read access changed. Refresh your session before requesting another review.',
  DEPENDENCY_UNAVAILABLE: 'A reporting dependency is unavailable. You can retry the review.',
};

export function CompanyBalanceContinuity({ company, yearId, name, permissions, returnTo }: {
  company: string; yearId: string; name: string; permissions: readonly string[]; returnTo?: string;
}) {
  const [year, setYear] = useState<Year | null>(null), [display, setDisplay] = useState<identity['schemas']['DisplayConfig'] | null>(null);
  const [error, setError] = useState(''), [displayError, setDisplayError] = useState(false), [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController(); setYear(null); setError(''); setDisplayError(false);
    companyCall<Year>('accounting', `/v1/companies/${company}/fiscal-years/${yearId}`, { signal: controller.signal }).then(value => {
      if (controller.signal.aborted) return;
      if (value.company_id !== company || value.id !== yearId || !value.start_date || !value.end_date) throw new Error('The financial year is unavailable for this company.');
      setYear(value);
    }).catch(value => { if (!controller.signal.aborted) setError(companyFailure(value).message); });
    companyCall<identity['schemas']['DisplayConfig']>('identity', `/v1/companies/${company}/display-config`, { signal: controller.signal })
      .then(value => { if (!controller.signal.aborted) setDisplay(value); }).catch(() => { if (!controller.signal.aborted) setDisplayError(true); });
    return () => controller.abort();
  }, [company, yearId, revision]);
  const config = { ...DEFAULT_DISPLAY_CONFIG, ...Object.fromEntries(Object.entries(resolvedDisplay(display ?? {})).filter(([, value]) => value !== undefined)) };
  return <DisplayConfigProvider config={config}>{year ? <BalanceContinuityWorkspace key={company + ':' + yearId} company={company} name={name} year={year} permissions={permissions} returnTo={returnTo} displayError={displayError} />
    : <div className="janso-page"><PageNavigation back={{ href: `/companies/${company}/years/${yearId}`, label: 'Financial year' }} /><PageHeader title="Review opening balances" lede={'Company: ' + name} />
      {error ? <Notice tone="danger">{error}<Button variant="ghost" onClick={() => setRevision(value => value + 1)}>Retry year details</Button></Notice> : <div role="status" aria-label="Loading financial year"><Skeleton /></div>}
    </div>}</DisplayConfigProvider>;
}

export function BalanceContinuityWorkspace({ company, name, year, permissions, returnTo, displayError = false }: {
  company: string; name: string; year: Year; permissions: readonly string[]; returnTo?: string; displayError?: boolean;
}) {
  const format = useFormatters(), base = '/v2/companies/' + company;
  const canExport = permissions.includes('report.export');
  const yearPath = `/companies/${company}/years/${year.id}`, back = returnTo ? administrationReturn('companies', returnTo) : yearPath;
  const [definition, setDefinition] = useState<Definition | null>(null), [sources, setSources] = useState<Source[]>([]), [source, setSource] = useState('');
  const [sourceNext, setSourceNext] = useState<string | null>(null);
  const [loading, setLoading] = useState(true), [busy, setBusy] = useState(false), [message, setMessage] = useState('');
  const [messageTone, setMessageTone] = useState<'danger' | 'info'>('danger');
  const [run, setRun] = useState<Job | null>(null), [root, setRoot] = useState<Job | null>(null), [exportJob, setExportJob] = useState<Job | null>(null);
  const [rows, setRows] = useState<Row[]>([]), [summary, setSummary] = useState<Record<string, unknown> | null>(null), [detail, setDetail] = useState<Row | null>(null);
  const [q, setQ] = useState(''), [kind, setKind] = useState(''), [filtered, setFiltered] = useState(false);
  const [cursors, setCursors] = useState<Array<string | null>>([null]), [position, setPosition] = useState(0), [next, setNext] = useState<string | null>(null);
  const gate = useRef(false), keys = useRef(new Map<string, string>());
  const activeRun = useRef<string | null>(null), rowRequest = useRef<AbortController | null>(null);
  useEffect(() => () => { activeRun.current = null; rowRequest.current?.abort(); }, []);
  function selectRun(value: Job) {
    if (activeRun.current !== value.id) { rowRequest.current?.abort(); setRows([]); setDetail(null); setNext(null); }
    activeRun.current = value.id; setRun(value);
  }
  async function act(work: () => Promise<void>) {
    if (gate.current) return; gate.current = true; setBusy(true); setMessage(''); setMessageTone('danger');
    try { await work(); } catch (error) { setMessage(error instanceof Error ? error.message : companyFailure(error).message); }
    finally { gate.current = false; setBusy(false); }
  }
  async function create<T>(path: string, body: unknown = {}): Promise<T> {
    const payload = JSON.stringify({ path, body }); let key = keys.current.get(payload);
    if (!key) { key = crypto.randomUUID(); keys.current.set(payload, key); }
    return request<T>('reports', 'POST', base + path, body, key);
  }
  async function load(signal?: AbortSignal) {
    const [catalog, page] = await Promise.all([
      request<reports['schemas']['DefinitionCatalog']>('reports', 'GET', base + '/report-definitions', undefined, undefined, signal),
      request<SourcePage>('reports', 'GET', base + '/report-generations?limit=50', undefined, undefined, signal),
    ]);
    if (signal?.aborted) return;
    setDefinition(catalog.items.find(item => item.definition.code === 'BALANCE_CONTINUITY') ?? null);
    setSources(page.items); setSource(current => current || page.items.find(item => item.status === 'READY')?.id || ''); setLoading(false);
    setSourceNext(page.page?.next_cursor ?? null);
  }
  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal).catch(error => { if (!controller.signal.aborted) { setMessage(error instanceof Error ? error.message : 'The report workspace is unavailable.'); setLoading(false); } });
    return () => controller.abort();
  }, [base]);
  async function page(job: Job, cursor: string | null = null, reset = false) {
    rowRequest.current?.abort(); const controller = new AbortController(); rowRequest.current = controller;
    const value = await request<reports['schemas']['ResultPage']>('reports', 'GET', base + '/report-runs/' + job.id + '/rows?limit=50' + (cursor ? '&cursor=' + encodeURIComponent(cursor) : ''), undefined, undefined, controller.signal);
    if (controller.signal.aborted || activeRun.current !== job.id) return;
    const control = value.items.find(row => row.data.row_kind === 'CONTINUITY_CONTROL')?.data;
    if (control && (control.next_year_id !== year.id || control.next_opening_date !== year.start_date)) throw new Error('The continuity result does not match this financial year.');
    if (control) setSummary(control);
    setRows(value.items); setNext(value.page.next_cursor); setDetail(null);
    if (reset) { setCursors([null]); setPosition(0); }
  }
  async function read(job: Job) {
    const value = await request<Job>('reports', 'GET', base + '/report-runs/' + job.id);
    selectRun(value); if (value.status === 'COMPLETE') await page(value, null, true);
  }
  useEffect(() => {
    if (!pendingJob(run)) return;
    const controller = new AbortController(); let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const value = await request<Job>('reports', 'GET', base + '/report-runs/' + run!.id, undefined, undefined, controller.signal);
        if (controller.signal.aborted) return;
        if (value.status === 'COMPLETE') await page(value, null, true);
        else if (pendingJob(value)) timer = setTimeout(() => void poll(), 2500);
        if (!controller.signal.aborted && activeRun.current === value.id) selectRun(value);
      } catch (error) { if (!controller.signal.aborted) setMessage(error instanceof Error ? error.message : 'Review status is unavailable. Refresh the review to retry.'); }
    }
    timer = setTimeout(() => void poll(), 1500);
    return () => { controller.abort(); clearTimeout(timer); };
  }, [base, run?.id, run?.status]);
  useEffect(() => {
    if (!canExport || !pendingJob(exportJob)) return;
    const controller = new AbortController();
    void trackReportExport(company, exportJob!, controller.signal, setExportJob).catch(error => {
      if (!controller.signal.aborted) setMessage(error instanceof Error ? error.message : 'Export status is unavailable.');
    });
    return () => controller.abort();
  }, [company, canExport, exportJob?.id, exportJob?.status]);
  const exportOptions = reportExportOptions({ run, limits: definition?.export_limits, view: 'default' });
  const frozen = run?.display ? resolvedDisplay(run.display) : null;
  function cell(key: string, value: unknown, money = false): string {
    if (value === null || value === undefined) return '—';
    if (key === 'row_kind') return reportRowLabel(String(value));
    if (typeof value === 'string' && money) return frozen ? formatMoney(value, frozen, { display: 'none' }) : format.money(value, { display: 'none' });
    if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)) return frozen ? formatDate(value, frozen) : format.date(value);
    return typeof value === 'object' ? JSON.stringify(value) : String(value);
  }
  const continuity = !run || run.code === 'BALANCE_CONTINUITY';
  const columns: Column<Row>[] = continuity ? [
    { key: 'record', header: 'Account / reference', type: 'custom', render: row => <div><strong>{String(row.data.reference ?? row.data.account_name ?? '')}</strong>{row.data.account_code != null && <p>{String(row.data.account_code)}</p>}</div> },
    { key: 'kind', header: 'Type', type: 'custom', render: row => reportRowLabel(String(row.data.row_kind)) },
    { key: 'currency', header: 'Currency', type: 'custom', render: row => String(row.data.currency ?? '') },
    ...['previous_closing', 'next_opening', 'difference'].map(key => ({ key, header: ({ previous_closing: 'Previous closing', next_opening: 'Next opening', difference: 'Difference' } as Record<string, string>)[key], type: 'custom' as const, render: (row: Row) => cell(key, row.data[key], true) })),
    { key: 'status', header: 'Check', type: 'custom', render: row => <Badge tone={row.data.reconciled === true ? 'success' : 'warn'}>{row.data.reconciled === true ? 'Matches' : 'Review difference'}</Badge> },
  ] : (run?.views[0]?.columns ?? []).map(column => ({ key: column.key, header: column.title, type: 'custom', render: row => cell(column.key, row.data[column.key], column.kind === 'MONEY') }));
  const shown = rows.filter(row => row.data.row_kind !== 'CONTINUITY_CONTROL');
  async function applyFilters() {
    if (!root) return;
    if (!q.trim() && !kind) { setFiltered(false); await read(root); return; }
    if (q.trim() && q.trim().length < 2) { setMessage('Enter at least two characters to search.'); return; }
    const value = await create<Job>('/report-runs/' + root.id + '/queries', { ...(q.trim() ? { q: q.trim() } : {}), filters: kind ? { row_kind: kind } : {}, sort: 'ordinal' });
    setFiltered(true); selectRun(value);
    if (value.status === 'COMPLETE') await page(value, null, true);
  }
  return <div className="janso-page">
    <PageNavigation back={{ href: back, label: administrationBackLabel(back) }} breadcrumbs={[{ label: 'Companies', href: '/companies' }, { label: 'Financial years', href: `/companies/${company}/years` }, { label: year.code ?? 'Financial year', href: administrationLink(yearPath, back) }, { label: 'Opening balances' }]} />
    <PageHeader title="Review opening balances" lede={`${name} · ${year.code ?? 'Financial year'}`} actions={<Button variant="ghost" disabled={busy} onClick={() => void act(async () => { const error = await openCompany(company, year.id); if (error) throw new Error(error.message); })}>Use this year</Button>} />
    {displayError && <Notice tone="warning">Company display preferences are unavailable. Standard formatting is used until a frozen report is loaded.</Notice>}
    <Notice>Compare the previous year’s closing balances with this year’s opening before its first movement. The review uses one verified source snapshot. Later postings or prior-year adjustments require a new review.</Notice>
    {message && <Notice tone={messageTone}>{message}</Notice>}
    <Card><CardHeader title="Balance continuity review" action={<Button variant="ghost" disabled={busy || loading} onClick={() => void act(() => load())}>Refresh sources</Button>} /><CardBody>
      {loading ? <div role="status" aria-label="Loading review sources"><Skeleton /></div> : !definition ? <Notice tone="warning">Balance continuity is unavailable with your current read access. Ask your accountant or administrator to review access and report availability.</Notice> : <>
        <ReviewList items={[{ label: 'Opening date', value: format.date(year.start_date) }, { label: 'Year ends', value: format.date(year.end_date) }]} />
        {!definition.run_enabled && <Notice tone="warning">New report runs are not enabled for this deployment. Ask your administrator to complete reporting activation.</Notice>}
        {!sources.some(item => item.status === 'READY') && <Notice tone="warning">No verified source snapshot is available. Request a source refresh with the required access, then refresh the source list.</Notice>}
        <Select label="Source snapshot" value={source} disabled={busy || pendingJob(run)} options={sources.filter(item => item.status === 'READY').map((item, index) => ({ value: item.id, label: item.applied_sequence !== undefined && item.applied_sequence !== null ? `Verified snapshot · sequence ${item.applied_sequence}` : `Verified snapshot ${index + 1}` }))} onChange={setSource} />
        {sourceNext && <Button variant="ghost" disabled={busy || pendingJob(run)} onClick={() => void act(async () => {
          const value = await request<SourcePage>('reports', 'GET', base + '/report-generations?limit=50&cursor=' + encodeURIComponent(sourceNext));
          setSources(current => [...current, ...value.items.filter(item => !current.some(existing => existing.id === item.id))]); setSourceNext(value.page?.next_cursor ?? null);
        })}>Load older snapshots</Button>}
        <div className="janso-form-actions"><Button disabled={busy || pendingJob(run) || !source || !definition.run_enabled} loading={busy} loadingLabel="Requesting review…" onClick={() => void act(async () => {
          const value = await create<Job>('/report-runs', { code: 'BALANCE_CONTINUITY', version: definition.definition.version, generation_id: source, parameters: { date_from: year.start_date, date_to: year.end_date }, view: 'default' });
          selectRun(value); setRoot(value); setSummary(null); setRows([]); setFiltered(false); setQ(''); setKind(''); setExportJob(null); setDetail(null); setNext(null);
          if (value.status === 'COMPLETE') await page(value, null, true);
        })}>{root ? 'Create new review' : 'Review balances'}</Button>
          {permissions.includes('report.definition.manage') && <Button variant="ghost" disabled={busy} onClick={() => void act(async () => { await create('/report-generations', source ? { strategy: 'REFRESH', base_generation_id: source } : { strategy: 'FRESH' }); setMessageTone('info'); setMessage('Source refresh requested. Refresh the source list after it completes.'); })}>Request source refresh</Button>}
        </div>
      </>}
    </CardBody></Card>
    {run && <Card><CardHeader title={continuity ? 'Continuity results' : run.title} action={<Button variant="ghost" disabled={busy} onClick={() => void act(() => read(run))}>Refresh review</Button>} /><CardBody>
      <p role="status">Review: {run.status.replaceAll('_', ' ').toLowerCase()}</p>
      <p>Result source: verified snapshot{sources.find(item => item.id === run.generation_id)?.applied_sequence != null ? ` · sequence ${sources.find(item => item.id === run.generation_id)!.applied_sequence}` : ''}. Changing the source selection applies to the next review.</p>
      {run.failure_code && <Notice tone="warning">{failureText[run.failure_code] ?? 'The review could not complete. Check its source and parameters before retrying.'}</Notice>}
      {pendingJob(run) && <Button variant="ghost" disabled={busy} onClick={() => void act(async () => selectRun(await create<Job>('/report-runs/' + run.id + '/cancel')))}>Cancel review</Button>}
      {run.status === 'FAILED' && <Button disabled={busy} onClick={() => void act(async () => selectRun(await create<Job>('/report-runs/' + run.id + '/retry')))}>Retry review</Button>}
      {run.id !== root?.id && root && <Button variant="ghost" disabled={busy} onClick={() => void act(async () => { setFiltered(false); setQ(''); setKind(''); await read(root); })}>Back to complete review</Button>}
      {run.status === 'COMPLETE' && <>
        {summary && continuity && <>
          <Notice tone={summary.reconciled === true ? 'success' : 'warning'}>{summary.reconciled === true ? 'Previous closing and next opening match in this verified snapshot.' : 'Differences require accounting review. The balances are not verified as matching.'}</Notice>
          <ReviewList items={[{ label: 'Previous closing', value: `${summary.previous_year_code} · ${cell('previous_closing_date', summary.previous_closing_date)}` }, { label: 'Next opening', value: `${summary.next_year_code} · ${cell('next_opening_date', summary.next_opening_date)}` }, { label: 'Accounts checked', value: String(summary.account_count) }, { label: 'Outstanding bills', value: String(summary.bill_count) }, { label: 'Advances / credits', value: String(summary.advance_count) }, { label: 'Total absolute difference', value: cell('difference', summary.difference, true) }]} />
          <p>Income and expense accounts retain their ledger history. Current-year P&amp;L uses current-year movements. Accumulated earnings below are derived rather than a new opening voucher.</p>
        </>}
        {continuity && <form className="janso-form-grid" onSubmit={event => { event.preventDefault(); void act(applyFilters); }}>
          <TextField type="search" label="Search accounts or references" placeholder="Code, name or bill reference" value={q} onChange={event => setQ(event.target.value)} minLength={2} maxLength={100} disabled={busy} />
          <Select label="Balance type" value={kind} disabled={busy} options={[{ value: '', label: 'All balances' }, { value: 'ACCOUNT_CONTINUITY', label: 'Accounts' }, { value: 'BILL_CONTINUITY', label: 'Outstanding bills' }, { value: 'ADVANCE_CONTINUITY', label: 'Advances / credits' }, { value: 'EARNINGS_CONTINUITY', label: 'Accumulated earnings' }]} onChange={setKind} />
          <Button type="submit" disabled={busy}>Apply filters</Button>
          {filtered && <p>Filtered rows are shown. The summary remains the complete original review.</p>}
        </form>}
        <DataTable caption={continuity ? 'Financial-year balance continuity' : run.title} columns={columns} rows={shown} rowId={row => String(row.ordinal)} rowLabel={row => String(row.data.reference ?? row.data.account_name ?? row.data.number ?? `Row ${row.ordinal}`)}
          loading={busy} emptyTitle={filtered ? 'No balances match your filters' : 'No balance rows available'} filtered={filtered} onClearFilters={() => { setQ(''); setKind(''); if (root) void act(async () => { setFiltered(false); await read(root); }); }}
          rowActions={row => (row.drilldowns ?? []).map(link => ({ id: link.key, label: link.title, disabledReason: busy ? 'A review action is in progress' : undefined }))}
          onAction={(key, row) => void act(async () => {
            const link = row.drilldowns?.find(item => item.key === key); if (!link) return;
            if (link.method === 'GET') { setDetail(await request<Row>('reports', 'GET', base + '/report-runs/' + run.id + '/rows/' + row.ordinal + '?token=' + encodeURIComponent(link.token))); return; }
            const child = await create<Job>('/report-runs/' + run.id + '/drilldowns', { token: link.token }); selectRun(child);
            if (child.status === 'COMPLETE') await page(child, null, true);
          })} />
        <Pager noun="balance" count={shown.length} from={null} limit={50} hasPrevious={position > 0} hasNext={!!next} busy={busy}
          onPrevious={() => void act(async () => { await page(run, cursors[position - 1] ?? null); setPosition(value => value - 1); })}
          onNext={() => void act(async () => { if (!next) return; await page(run, next); setCursors(values => [...values.slice(0, position + 1), next]); setPosition(value => value + 1); })} />
        {detail && <Card><CardHeader title="Record details" action={<Button variant="ghost" onClick={() => setDetail(null)}>Close details</Button>} /><CardBody><ReviewList items={Object.entries(detail.data).map(([key, value]) => ({ label: key.replaceAll('_', ' '), value: cell(key, value, ['previous_closing', 'next_opening', 'difference'].includes(key)) }))} /></CardBody></Card>}
        {canExport && continuity && <div className="janso-form-actions">{exportOptions.map(option => <Button key={option.id} variant="ghost" disabled={busy || pendingJob(exportJob) || !!option.disabledReason} title={option.disabledReason ?? 'Export all matching rows as ' + option.label} onClick={() => void act(async () => setExportJob(await create<Job>('/report-runs/' + run.id + '/exports', { format: option.id, view: 'default' })))}>Export {option.id}</Button>)}</div>}
      </>}
    </CardBody></Card>}
    {canExport && exportJob && <Card><CardHeader title="Review export" action={<Button variant="ghost" disabled={busy} onClick={() => void act(async () => setExportJob(await request<Job>('reports', 'GET', base + '/report-exports/' + exportJob.id)))}>Refresh export</Button>} /><CardBody><p role="status">Export: {exportJob.status.toLowerCase()}</p>
      {exportJob.failure_code && <Notice tone="warning">The export could not complete. Review its status and retry when available.</Notice>}
      {pendingJob(exportJob) && <Button variant="ghost" disabled={busy} onClick={() => void act(async () => setExportJob(await create<Job>('/report-exports/' + exportJob.id + '/cancel')))}>Cancel export</Button>}
      {exportJob.status === 'FAILED' && <Button disabled={busy} onClick={() => void act(async () => setExportJob(await create<Job>('/report-exports/' + exportJob.id + '/retry')))}>Retry export</Button>}
      {exportJob.status === 'COMPLETE' && <><a className="janso-btn janso-btn--primary" href={reportDownloadHref(company, exportJob.id)}>Download export</a>{canPreviewReportExport(exportJob) && <a className="janso-link" href={reportDownloadHref(company, exportJob.id, true)} target="_blank" rel="noopener noreferrer">Open print preview</a>}</>}
    </CardBody></Card>}
  </div>;
}
