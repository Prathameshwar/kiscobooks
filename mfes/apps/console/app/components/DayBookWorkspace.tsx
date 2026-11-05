'use client';

import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import { Button, DisplayConfigProvider, Menu, Modal, Notice, PageHeader, PageNavigation, Select, TextField, resolvedDisplay, useDisplayConfig, useFormatters } from '@janso/ui';
import type { FiscalYearChoice } from '../lib/company-context';
import { defaultDayBookFilters, filterError, kindLabel, statusLabel, preferencesKey, readDayBookFilters, readDayBookPosition, UUID, type DayBookPosition, type DayBookSummary, type DayBookFilters as Filters, type SavedDayBookView } from '../lib/day-book';
import { productFieldRequest as request } from '../lib/product-fields';
import { useDayBook } from '../lib/use-day-book';
import { newVoucherActions } from '../lib/new-voucher-actions';
import { canPreviewReportExport, primaryExportFormats, reportDownloadHref, reportExportOptions } from '../lib/report-exports';
import { DayBookFilters } from './DayBookFilters';
import { DayBookResults, DayBookSummaryStrip, defaultColumns, type DayBookColumns } from './DayBookResults';

type Props = { company: string; companyName: string; actor: string; permissions: readonly string[]; year?: FiscalYearChoice | null };
export function DayBookWorkspace({ company, companyName, actor, permissions, year }: Props) {
  const display = useDisplayConfig(), format = useFormatters();
  const initial = useMemo(() => defaultDayBookFilters(display, year), [display, year]);
  const [draft, setDraft] = useState(initial), [initialized, setInitialized] = useState(false);
  const [advanced, setAdvanced] = useState(false), [saveOpen, setSaveOpen] = useState(false), [saveName, setSaveName] = useState('');
  const [mobileFilters, setMobileFilters] = useState(false);
  const filterPanelId = useId();
  const [saved, setSaved] = useState<SavedDayBookView[]>([]), [selectedView, setSelectedView] = useState('');
  const [message, setMessage] = useState(''), [validation, setValidation] = useState(''), [typeBusy, setTypeBusy] = useState(false);
  const [columns, setColumns] = useState<DayBookColumns>(defaultColumns), [density, setDensity] = useState('comfortable');
  const model = useDayBook(company);
  const started = useRef(false), restoreId = useRef(''), restorePosition = useRef<DayBookPosition | undefined>(undefined), typeRequest = useRef<AbortController | null>(null);
  const key = preferencesKey(actor, company);
  const canReadVouchers = permissions.includes('vouchers.read');
  const canCreate = canReadVouchers && permissions.includes('vouchers.create');
  const canExport = permissions.includes('report.export');
  const change = useCallback((update: Partial<Filters>) => { setDraft(current => ({ ...current, ...update })); setValidation(''); }, []);
  useEffect(() => {
    let filters = initial;
    try {
      const query = new URLSearchParams(window.location.search);
      if (query.get('company') === company) {
        const raw = query.get('filters');
        if (raw && raw.length <= 16000) filters = readDayBookFilters(JSON.parse(raw), initial) ?? initial;
        const run = query.get('run'); if (run && UUID.test(run)) restoreId.current = run;
        const position = sessionStorage.getItem(key + ':position');
        if (position && position.length <= 1000000) { const savedPosition = JSON.parse(position); if (savedPosition.run === (run ?? '') && savedPosition.filters === JSON.stringify(filters) && String(savedPosition.position?.index) === query.get('page')) restorePosition.current = readDayBookPosition(savedPosition.position); }
      }
      if (filters.scope === 'ALL' && !canReadVouchers) filters = initial;
      const stored = localStorage.getItem(key);
      if (stored && stored.length <= 100000) {
        const value = JSON.parse(stored);
        if (Array.isArray(value.views)) setSaved(value.views.slice(0, 20).flatMap((item: SavedDayBookView) => {
          const verified = readDayBookFilters(item.filters, initial);
          return typeof item.name === 'string' && item.name.length <= 60 && typeof item.id === 'string' && verified ? [{ id: item.id, name: item.name, filters: verified }] : [];
        }));
        if (value.density === 'compact') setDensity('compact');
        if (value.columns && Object.keys(defaultColumns).every(name => typeof value.columns[name] === 'boolean')) setColumns(value.columns);
      }
    } catch { /* Invalid/unavailable browser preferences never block the report. */ }
    setDraft(filters); setInitialized(true);
    return () => typeRequest.current?.abort();
  }, [company, key, initial, canReadVouchers]);
  useEffect(() => {
    if (!initialized || started.current) return;
    if (draft.scope === 'POSTED' && (model.sourceState !== 'ready' || !restoreId.current && !model.definition?.run_enabled)) return;
    started.current = true;
    void model.run(draft, restoreId.current || undefined, restorePosition.current);
  }, [initialized, draft, model.sourceState, model.definition, model.run]);
  useEffect(() => {
    if (!initialized) return;
    try { localStorage.setItem(key, JSON.stringify({ views: saved, columns, density })); }
    catch { /* Keep the current view usable if storage is disabled or full. */ }
  }, [initialized, key, saved, columns, density]);
  useEffect(() => {
    if (!model.active) return;
    const query = new URLSearchParams({ company, filters: JSON.stringify(model.active) });
    if (model.job) query.set('run', model.job.id);
    if (model.pageIndex) query.set('page', String(model.pageIndex));
    try { sessionStorage.setItem(key + ':position', JSON.stringify({ run: model.job?.id ?? '', filters: JSON.stringify(model.active), position: { index: model.pageIndex, cursors: model.pageCursors } })); } catch { /* Paging remains usable when session storage is unavailable. */ }
    window.history.replaceState(window.history.state, '', '/books/day-book?' + query);
  }, [company, key, model.active, model.job, model.pageIndex, model.pageCursors]);

  useEffect(() => { if (model.active) setDraft(model.active); }, [model.active]);

  function apply(value = draft) {
    if (model.busy || typeBusy) return;
    if (value.scope === 'POSTED' && (model.sourceState !== 'ready' || !model.definition?.run_enabled)) return;
    const error = filterError(value);
    if (error) { setValidation(error); return; }
    setValidation(''); started.current = true; restoreId.current = '';
    void model.run(value);
  }
  function scope(scope: Filters['scope']) {
    const next: Filters = { ...draft, scope, status: '', mode: 'VOUCHERS',
      ...(scope === 'ALL' ? { account_id: '', account_label: '', amount_min: '', amount_max: '', sort: 'date', group_by: 'date' } : {}) };
    setDraft(next); apply(next);
  }
  async function chooseType(id: string | null, label?: string) {
    typeRequest.current?.abort(); const abort = new AbortController(); typeRequest.current = abort;
    change({ type_id: id ?? '', type_label: label ?? '', type_revision_ids: [] });
    if (!id) { setTypeBusy(false); return; }
    setTypeBusy(true); setValidation('');
    try {
      const value = await request<{ type_id: string; revision_ids: string[] }>('vouchers', 'GET', '/v1/companies/' + company + '/day-book/types/' + id + '/revisions', undefined, undefined, abort.signal);
      if (abort.signal.aborted) return;
      if (value.type_id !== id || !Array.isArray(value.revision_ids) || !value.revision_ids.length || value.revision_ids.some(item => !UUID.test(item))) throw new Error('The voucher type revisions could not be verified. Choose the type again.');
      change({ type_revision_ids: value.revision_ids });
    } catch (error) { if (!abort.signal.aborted) { change({ type_id: '', type_label: '', type_revision_ids: [] }); setValidation(error instanceof Error ? error.message : 'Unable to select this voucher type.'); } }
    finally { if (!abort.signal.aborted) setTypeBusy(false); }
  }
  function updateView(update: Partial<Filters>) { const next = { ...draft, ...update }; setDraft(next); apply(next); }
  function save() {
    if (!saveName.trim()) { setMessage('Enter a name for this view.'); return; }
    if (saved.length >= 20) { setMessage('You can save up to 20 views. Delete an unused view first.'); return; }
    const view = { id: crypto.randomUUID(), name: saveName.trim().slice(0, 60), filters: model.active ?? draft };
    setSaved(previous => [...previous, view]); setSelectedView(view.id); setSaveOpen(false); setSaveName(''); setMessage('View saved on this browser for ' + companyName + '.');
  }
  const active = model.active ?? draft;
  const dirty = !!model.active && JSON.stringify(draft) !== JSON.stringify(model.active);
  const returnQuery = new URLSearchParams({ company, filters: JSON.stringify(active) });
  if (model.job) returnQuery.set('run', model.job.id);
  if (model.pageIndex) returnQuery.set('page', String(model.pageIndex));
  const returnTo = '/books/day-book?' + returnQuery;
  const exportOptions = reportExportOptions({ run: model.job, limits: model.definition?.export_limits, view: active.mode === 'ACCOUNTING' ? 'accounting' : 'default', formats: primaryExportFormats });
  const pdfUnavailable = exportOptions.find(item => item.id === 'PDF')?.disabledReason;
  const canRun = draft.scope === 'ALL' || model.sourceState === 'ready' && !!model.definition?.run_enabled;
  const currency = model.summary?.currency ?? (active.basis === 'TRANSACTION' ? active.currency : display.currency);
  const presentation = model.job?.display ? resolvedDisplay(model.job.display) : display;
  const reset = () => {
    const next = { ...initial, scope: draft.scope, mode: draft.mode, group_by: draft.group_by, sort: draft.sort, date_from: draft.date_from, date_to: draft.date_to };
    setDraft(next); setSelectedView(''); apply(next);
  };
  const discovering = draft.scope === 'POSTED' && model.sourceState === 'loading' && !model.busy;
  const loadingReport = discovering || model.busy && model.operation !== 'export';
  const progress = discovering ? 'Loading report data…' : model.busy ? {
    run: 'Preparing your Day Book…', page: 'Loading page ' + (model.targetPage + 1) + '…',
    export: 'Preparing ' + model.exportFormat + ' report…', source: 'Preparing accounting data…',
    refresh: 'Checking for updated report data…',
  }[model.operation] : '';
  const retryLabel = model.operation === 'export' ? 'Retry export' : model.operation === 'page' ? 'Retry page' : model.operation === 'source' ? 'Retry report data' : 'Retry report';
  const unavailable = !model.active && !!(model.error || model.sourceError || draft.scope === 'POSTED' && model.sourceState === 'ready' && !model.definition?.run_enabled);
  const chips: { text: string; clear: Partial<Filters> }[] = [
    ...active.kinds.map(kind => ({ text: kindLabel(kind), clear: { kinds: active.kinds.filter(value => value !== kind) } })),
    ...(active.status ? [{ text: 'Status: ' + statusLabel(active.status), clear: { status: '' } }] : []),
    ...(active.basis === 'TRANSACTION' ? [{ text: 'Currency: ' + active.currency, clear: { basis: 'BASE' as const, currency: '' } }] : []),
    ...(active.party_id ? [{ text: active.party_label || 'Selected party', clear: { party_id: '', party_label: '' } }] : []),
    ...(active.account_id ? [{ text: active.account_label || 'Selected ledger', clear: { account_id: '', account_label: '' } }] : []),
    ...(active.type_id ? [{ text: active.type_label || 'Selected type', clear: { type_id: '', type_label: '', type_revision_ids: [] } }] : []),
    ...(active.q ? [{ text: 'Search: ' + active.q, clear: { q: '' } }] : []),
    ...(active.amount_min || active.amount_max ? [{ text: 'Posting value: ' + (active.amount_min || '0') + '–' + (active.amount_max || 'any'), clear: { amount_min: '', amount_max: '' } }] : []),
    ...(active.conditions.length ? [{ text: active.conditions.length + ' conditions · ' + active.match, clear: { conditions: [] } }] : []),
  ];
  return <div className="janso-page janso-day-book" data-density={density}>
    <PageNavigation breadcrumbs={[{ label: 'Books', href: '/books' }, { label: 'Day Book' }]} />
    <PageHeader overline={companyName + (year ? ' · ' + year.code : '')} title="Day Book" lede="A clear view of your daily vouchers and accounting activity." actions={<>
      {canExport && active.scope === 'POSTED' && <Menu label="Export Day Book" triggerLabel="Export" disabled={!model.job || model.busy || dirty} items={exportOptions} onSelect={value => void model.exportReport(value as 'CSV' | 'XLSX' | 'PDF')} />}
      {canExport && active.scope === 'POSTED' && <Button variant="ghost" title={pdfUnavailable ?? 'Export all matching rows as PDF'} disabled={!model.job || model.busy || dirty || !!pdfUnavailable} onClick={() => void model.exportReport('PDF')}>Print / PDF</Button>}
      {canCreate && <Menu label="New voucher" triggerLabel="+ New voucher" triggerVariant="primary" items={newVoucherActions} onSelect={() => {}} />}
    </>} />
    <div className="janso-day-book__scope-row">
      <div className="janso-day-book__segmented" role="group" aria-label="Day Book scope"><Button variant="ghost" aria-pressed={draft.scope === 'POSTED'} disabled={model.busy} onClick={() => scope('POSTED')}>Posted book</Button>{canReadVouchers && <Button variant="ghost" aria-pressed={draft.scope === 'ALL'} disabled={model.busy} onClick={() => scope('ALL')}>All vouchers</Button>}</div>
      <div className="janso-day-book__freshness"><span>{active.scope === 'POSTED' ? 'Frozen accounting snapshot' : 'Live document activity'}{model.observed ? (active.scope === 'POSTED' ? ' · Report prepared ' : ' · Checked ') + format.dateTime(model.observed) : ''}</span><Button variant="ghost" disabled={model.busy || typeBusy || !canRun} onClick={() => { const error = filterError(draft); if (error) setValidation(error); else void model.refresh(draft); }}>Refresh</Button>{active.scope === 'POSTED' && model.sourceState === 'ready' && permissions.includes('report.definition.manage') && <Button variant="ghost" disabled={model.busy || typeBusy || dirty} onClick={() => void model.prepare(active)}>Update accounting data</Button>}</div>
    </div>
    <section className="janso-day-book__surface" aria-label="Filters and saved views" data-mobile-open={mobileFilters}>
      <div className="janso-day-book__mobile-filter-toggle"><Button variant="ghost" aria-expanded={mobileFilters} aria-controls={filterPanelId} onClick={() => setMobileFilters(value => !value)}>{mobileFilters ? 'Hide filters' : 'Filters'}</Button></div>
      <div className="janso-day-book__filter-content" id={filterPanelId}><DayBookFilters company={company} value={draft} change={change} apply={() => apply()} advanced={advanced} setAdvanced={setAdvanced} busy={model.busy} canApply={canRun} typeBusy={typeBusy} chooseType={chooseType} canReadVouchers={canReadVouchers} canReadParties={permissions.includes('accounting.party.read')} canReadAccounts={permissions.includes('accounting.account.read')} year={year} /></div>
      <div className="janso-day-book__filter-foot"><div className="janso-day-book__chips"><span>{format.range(active.date_from, active.date_to)}</span>{chips.map(chip => <button key={chip.text} type="button" aria-label={'Remove filter ' + chip.text} disabled={model.busy} onClick={() => { const next = { ...draft, ...chip.clear }; setDraft(next); apply(next); }}>{chip.text}<span aria-hidden="true">×</span></button>)}</div><div className="janso-day-book__view-actions"><Button variant="ghost" disabled={model.busy} onClick={reset}>Reset filters</Button><Button variant="ghost" disabled={model.busy || dirty || !model.active} onClick={() => { setMessage(''); setSaveOpen(true); }}>Save view</Button></div></div>
      {saved.length > 0 && <div className="janso-day-book__saved"><Select label="Saved view" value={selectedView} options={[{ value: '', label: 'Choose a saved view…' }, ...saved.map(item => ({ value: item.id, label: item.name }))]} onChange={id => { setSelectedView(id); const view = saved.find(item => item.id === id); if (view) { setDraft(view.filters); apply(view.filters); } }} disabled={model.busy} /><Button variant="ghost" disabled={!selectedView || model.busy} onClick={() => { setSaved(previous => previous.filter(item => item.id !== selectedView)); setSelectedView(''); }}>Delete saved view</Button></div>}
    </section>
    {progress && <div className="janso-day-book__progress" role="status" aria-label="Day Book progress" aria-atomic="true"><span className="janso-spinner" aria-hidden="true" /><div><strong>{progress}</strong><span>{model.operation === 'export' && model.busy ? 'Your report remains available while the file is prepared.' : model.active ? 'Your current results remain visible until the update is ready.' : 'Results and totals will appear when the data is ready.'}</span></div></div>}
    {canExport && model.exportJob?.status === 'COMPLETE' && <Notice tone="success" live="polite">Your report is ready. <a className="janso-link" href={reportDownloadHref(company, model.exportJob.id)}>Download report</a> All matching rows from the applied filters are included.{canPreviewReportExport(model.exportJob) && <> · <a className="janso-link" href={reportDownloadHref(company, model.exportJob.id, true)} target="_blank" rel="noopener noreferrer">Open print preview</a></>}</Notice>}
    {canExport && active.scope === 'ALL' && <Notice>To export PDF, Excel or CSV, switch to Posted book. Exports use the verified report snapshot.</Notice>}
    {dirty && !model.busy && canRun && <Notice>Filters changed. Select Apply to update the report and totals.</Notice>}
    {validation && <Notice tone="danger">{validation}</Notice>}
    {model.error && <Notice tone="danger"><span>{model.error}</span>{model.active && ' Your previous report is still shown.'} <Button variant="ghost" disabled={model.busy} onClick={model.retry}>{retryLabel}</Button></Notice>}
    {message && !saveOpen && <p role="status" className="janso-day-book__muted">{message}</p>}
    {draft.scope === 'POSTED' && model.sourceState === 'error' && <Notice tone="warning" live="assertive">{model.sourceError}<Button variant="ghost" disabled={model.busy} onClick={() => void model.refresh(draft)}>Retry report data</Button></Notice>}
    {draft.scope === 'POSTED' && model.sourceState === 'missing' && <Notice>There is no prepared accounting snapshot yet. {permissions.includes('report.definition.manage') ? <Button variant="ghost" disabled={model.busy} onClick={() => void model.prepare()}>Prepare report data</Button> : 'Ask your administrator to prepare report data.'}{canReadVouchers && ' You can view live documents under All vouchers.'}</Notice>}
    {draft.scope === 'POSTED' && model.sourceState === 'ready' && !model.definition?.run_enabled && <Notice>New report generation is currently unavailable. Your administrator can enable the reporting worker.</Notice>}
    <DisplayConfigProvider config={presentation}>
      <DayBookSummaryStrip summary={model.summary} scope={active.scope} />
      <section className="janso-day-book__report" aria-label="Day Book report" aria-busy={loadingReport}>
        <div className="janso-day-book__report-toolbar"><div className="janso-day-book__segmented" role="group" aria-label="Report view"><Button variant="ghost" aria-pressed={draft.mode === 'VOUCHERS'} disabled={model.busy || draft.scope === 'ALL'} onClick={() => updateView({ mode: 'VOUCHERS' })}>Vouchers</Button>{draft.scope === 'POSTED' && <Button variant="ghost" aria-pressed={draft.mode === 'ACCOUNTING'} disabled={model.busy} onClick={() => updateView({ mode: 'ACCOUNTING' })}>Accounting</Button>}</div><div className="janso-day-book__table-options">
          {draft.scope === 'POSTED' && <Select label="Group by" value={draft.group_by} options={[{ value: 'date', label: 'Date' }, { value: 'kind', label: 'Voucher kind' }, { value: 'particulars', label: 'Particulars' }, { value: 'none', label: 'No grouping' }]} onChange={group_by => updateView({ group_by: group_by as Filters['group_by'] })} disabled={model.busy} />}
          <Select label="Sort by" value={draft.sort} options={[{ value: 'date', label: 'Oldest first' }, { value: '-date', label: 'Newest first' }, { value: 'number', label: 'Voucher number' }, ...(draft.scope === 'POSTED' ? [{ value: '-amount', label: 'Largest posting value' }] : [])]} onChange={sort => updateView({ sort: sort as Filters['sort'] })} disabled={model.busy} />
          <Menu label="Visible columns" triggerLabel="Columns" items={(Object.keys(columns) as (keyof DayBookColumns)[]).map(name => ({ id: name, label: name === 'kind' ? 'Voucher type' : name.charAt(0).toUpperCase() + name.slice(1), checked: columns[name] }))} onSelect={name => setColumns(previous => ({ ...previous, [name]: !previous[name as keyof DayBookColumns] }))} />
          <Select label="Row density" value={density} options={[{ value: 'comfortable', label: 'Comfortable' }, { value: 'compact', label: 'Compact' }]} onChange={setDensity} />
        </div></div>
        <p className="janso-day-book__report-context">{active.scope === 'POSTED' ? 'By posting date · ' + (active.basis === 'BASE' ? 'Complete matching journals' : 'Selected-currency entries; journals may include other currencies') + ' · ' + currency : 'By document date · Live status counts · No accounting totals'}{(loadingReport || dirty && !canRun) && model.active ? ' · Showing previous results' : ''}</p>
        {loadingReport && !model.active ? <div className="janso-day-book__loading" aria-hidden="true"><span className="janso-day-book__loading-line" /><span className="janso-day-book__loading-line" /><span className="janso-day-book__loading-line" /></div> : model.rows.length ? <DayBookResults key={JSON.stringify(active) + ':' + model.pageIndex} rows={model.rows} summary={model.summary} filters={active} columns={columns} returnTo={returnTo} canOpen={canReadVouchers} /> : <div className="janso-day-book__empty"><span aria-hidden="true">▤</span><h2>{unavailable ? 'Report unavailable' : model.active ? 'No transactions found' : 'Your Day Book is ready to explore'}</h2><p>{unavailable ? 'Check the message above for the next step.' : model.active ? 'Try another period or remove a filter to see more activity.' : 'Choose your period and filters. Prepared accounting data will appear here.'}</p>{model.active && <Button variant="ghost" disabled={model.busy} onClick={reset}>Reset filters</Button>}</div>}
        <footer className="janso-day-book__report-footer"><div><strong>{model.active ? <>{model.rows.length ? model.pageIndex * 50 + 1 + '–' + (model.pageIndex * 50 + model.rows.length) : '0'}{model.summary ? ' of ' + (active.mode === 'ACCOUNTING' ? model.summary.line_count : model.summary.activity_count ?? model.summary.voucher_count) : ''} {active.mode === 'ACCOUNTING' ? 'lines' : model.summary?.activity_count !== undefined && model.summary.activity_count !== model.summary.voucher_count ? 'voucher entries' : 'vouchers'}</> : 'Results pending'}</strong><span>{active.scope === 'POSTED' ? 'Totals cover all matching results' : 'Live documents may change between pages'}</span></div><div><Button variant="ghost" disabled={model.busy || model.pageIndex === 0} onClick={() => void model.navigate(model.pageIndex - 1)}>Previous</Button><Button variant="ghost" disabled={model.busy || !model.nextCursor} onClick={() => void model.navigate(model.pageIndex + 1)}>Next</Button></div></footer>
      </section>
      {model.summary && <KindBreakdown summary={model.summary} currency={currency} />}
    </DisplayConfigProvider>

    <Modal open={saveOpen} title="Save this view" onClose={() => setSaveOpen(false)} footer={<><Button variant="ghost" onClick={() => setSaveOpen(false)}>Cancel</Button><Button onClick={save} disabled={!saveName.trim()}>Save view</Button></>}><TextField label="View name" value={saveName} maxLength={60} placeholder="For example, This month’s purchases" onChange={event => setSaveName(event.target.value)} hint="Saved on this browser, for your account and this company." />{message && <p role="alert">{message}</p>}</Modal>
  </div>;
}

function KindBreakdown({ summary, currency }: { summary: DayBookSummary; currency: string }) {
  const format = useFormatters();
  if (!Object.keys(summary.by_kind).length) return null;
  return <details className="janso-day-book__breakdown"><summary>Breakdown by voucher kind</summary><dl>{Object.entries(summary.by_kind).map(([kind, value]) => <div key={kind}><dt>{kindLabel(kind)}</dt><dd>{typeof value === 'number' ? value : value.count} vouchers{typeof value !== 'number' && <small>Debit {format.money(value.debit, { display: 'none' })} / Credit {format.money(value.credit, { display: 'none' })} {currency}</small>}</dd></div>)}</dl></details>;
}
