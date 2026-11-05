'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import type { components } from '@janso/api-client/reports';
import type { components as VoucherComponents } from '@janso/api-client/vouchers';
import { productFieldRequest as request } from './product-fields';
import { reportExportFailure, trackReportExport } from './report-exports';
import { DAY_BOOK_CODE, UUID, liveParameters, reportParameters, matchingDayBookParameters, type DayBookPosition, type DayBookFilters, type DayBookRow, type DayBookSummary } from './day-book';

type Schemas = components['schemas'];
export type DayBookJob = Schemas['JobDetail'];
type LivePage = VoucherComponents['schemas']['DayBookPage'];
const pending = (job: DayBookJob) => ['QUEUED', 'RUNNING'].includes(job.status);
const failures: Record<string, string> = {
  REPORT_CAPACITY_EXCEEDED: 'This report exceeds the supported capacity. Choose a smaller source or ask your administrator to prepare a bounded report.',
  REPORT_VERIFICATION_FAILED: 'The report could not be verified. Check that the source covers the selected period, then retry.',
  AUTHORITY_REVOKED: 'Your report access has changed. Refresh the page to check your current access.',
};

export function useDayBook(company: string) {
  const base = '/v2/companies/' + company;
  const [definition, setDefinition] = useState<Schemas['DefinitionDetail'] | null>(null);
  const [generation, setGeneration] = useState('');
  const [sourceState, setSourceState] = useState<'loading' | 'ready' | 'missing' | 'error'>('loading');
  const [sourceError, setSourceError] = useState('');
  const [rows, setRows] = useState<DayBookRow[]>([]), [summary, setSummary] = useState<DayBookSummary | null>(null);
  const [job, setJob] = useState<DayBookJob | null>(null), [exportJob, setExportJob] = useState<DayBookJob | null>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [operation, setOperation] = useState<'run' | 'page' | 'export' | 'source' | 'refresh'>('run');
  const [exportFormat, setExportFormat] = useState(''), [targetPage, setTargetPage] = useState(0);
  const retryAction = useRef<(() => void) | null>(null);
  const [observed, setObserved] = useState('');
  const [nextCursor, setNextCursor] = useState<string | null>(null), [pageCursors, setPageCursors] = useState<(string | null)[]>([null]);
  const [pageIndex, setPageIndex] = useState(0);
  const [active, setActive] = useState<DayBookFilters | null>(null);
  const controller = useRef<AbortController | null>(null), sequence = useRef(0);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);
  const keys = useRef(new Map<string, string>());
  const alive = useRef(true);
  const command = useCallback(async <T,>(path: string, body: unknown, signal?: AbortSignal) => {
    const payload = JSON.stringify({ path, body });
    if (!keys.current.has(payload)) keys.current.set(payload, crypto.randomUUID());
    const result = await request<T>('reports', 'POST', base + path, body, keys.current.get(payload), signal);
    keys.current.delete(payload);
    return result;
  }, [base]);
  useEffect(() => { alive.current = true; return () => { alive.current = false; sequence.current++; controller.current?.abort(); timers.current.forEach(clearTimeout); }; }, [company]);

  const discover = useCallback(async (signal?: AbortSignal) => {
    setSourceState('loading'); setSourceError('');
    try {
      const found = await request<Schemas['DefinitionDetail']>('reports', 'GET', base + '/report-definitions/' + DAY_BOOK_CODE, undefined, undefined, signal);
      if (signal?.aborted || !alive.current) return '';
      setDefinition(found);
      let cursor: string | null = null;
      for (let page = 0; page < 20; page++) {
        const result: Schemas['ResourcePage'] = await request('reports', 'GET', base + '/report-generations?limit=50' + (cursor ? '&cursor=' + encodeURIComponent(cursor) : ''), undefined, undefined, signal);
        if (signal?.aborted || !alive.current) return '';
        const ready = result.items.find(item => item.status === 'READY');
        if (ready) { setGeneration(ready.id); setSourceState('ready'); return ready.id; }
        cursor = result.page.next_cursor;
        if (!cursor) break;
      }
      setSourceState('missing'); return '';
    } catch (failure) {
      if (!signal?.aborted && alive.current) { setSourceState('error'); setSourceError(failure instanceof Error ? failure.message : 'Report data is unavailable.'); }
      return '';
    }
  }, [base]);
  useEffect(() => { const abort = new AbortController(); void discover(abort.signal); return () => abort.abort(); }, [discover]);

  const loadPage = useCallback(async (identity: string, cursor: string | null, signal: AbortSignal) => {
    const result = await request<Schemas['ResultPage']>('reports', 'GET', base + '/report-runs/' + identity + '/rows?limit=50' + (cursor ? '&cursor=' + encodeURIComponent(cursor) : ''), undefined, undefined, signal);
    return { rows: result.items.map(item => item.data as DayBookRow), cursor: result.page.next_cursor };
  }, [base]);

  const run = useCallback(async (filters: DayBookFilters, restoreId?: string, position?: DayBookPosition, generationOverride?: string): Promise<void> => {
    const version = ++sequence.current;
    controller.current?.abort(); controller.current = new AbortController();
    const signal = controller.current.signal;
    timers.current.forEach(clearTimeout); timers.current = [];
    setOperation('run'); retryAction.current = () => { void run(filters, undefined, undefined, generationOverride); };
    setBusy(true); setError(''); setExportJob(null);
    try {
      if (filters.scope === 'POSTED' && filters.type_id) {
        const type = await request<VoucherComponents['schemas']['DayBookTypeRevisions']>('vouchers', 'GET', '/v1/companies/' + company + '/day-book/types/' + filters.type_id + '/revisions', undefined, undefined, signal);
        if (type.type_id !== filters.type_id || !type.revision_ids.length || type.revision_ids.some(id => !UUID.test(id))) throw new Error('The voucher type could not be verified. Choose the type again.');
        filters = { ...filters, type_revision_ids: type.revision_ids };
      }
      if (filters.scope === 'ALL') {
        const result = await request<LivePage>('vouchers', 'POST', '/v1/companies/' + company + '/day-book/query', liveParameters(filters, position ? position.cursors[position.index] : null), undefined, signal);
        if (version !== sequence.current || signal.aborted) return;
        if (!result.summary) throw new Error('The live activity summary is unavailable. Retry the report.');
        setJob(null); setRows(result.items); setSummary(result.summary); setObserved(result.observed_at);
        setNextCursor(result.page.next_cursor ?? null); setPageCursors(position ? position.cursors : [null]); setPageIndex(position ? position.index : 0); setActive(filters); setBusy(false); return;
      }
      if (!generation && !generationOverride && !restoreId) throw new Error('Prepare report data before running the posted book.');
      let result = restoreId && UUID.test(restoreId)
        ? await request<DayBookJob>('reports', 'GET', base + '/report-runs/' + restoreId, undefined, undefined, signal)
        : await command<DayBookJob>('/report-runs', { code: DAY_BOOK_CODE, generation_id: generationOverride || generation, parameters: reportParameters(filters), view: filters.mode === 'ACCOUNTING' ? 'accounting' : 'default' }, signal);
      if (result.code !== DAY_BOOK_CODE || result.kind !== 'RUN' || JSON.stringify(result.parameters) === '{}') throw new Error('The saved Day Book report is unavailable. Apply the filters to create a new report.');
      if (!matchingDayBookParameters(filters, result.parameters)) throw new Error('The saved Day Book report does not match these filters. Select Apply to prepare a matching report.');
      async function accept(value: DayBookJob) {
        if (signal.aborted || version !== sequence.current) return;
        if (pending(value)) {
          timers.current.push(setTimeout(() => { void request<DayBookJob>('reports', 'GET', base + '/report-runs/' + value.id, undefined, undefined, signal).then(accept).catch(fail); }, 1500));
          return;
        }
        if (value.status !== 'COMPLETE') throw new Error(failures[value.failure_code ?? ''] ?? 'The report could not complete. Retry or adjust the selected period.');
        const restored = restoreId && position;
        const page = await loadPage(value.id, restored ? restored.cursors[restored.index] : null, signal);
        if (signal.aborted || version !== sequence.current) return;
        const totals = (value.result?.evidence as { day_book?: DayBookSummary } | undefined)?.day_book;
        if (!totals) throw new Error('This report has no verified Day Book summary. Apply the filters to create a new report.');
        setJob(value); setRows(page.rows); setSummary(totals); setObserved(value.created_at);
        setNextCursor(page.cursor); setPageCursors(restored ? restored.cursors : [null]); setPageIndex(restored ? restored.index : 0); setActive(filters); setBusy(false);
      }
      function fail(failure: unknown) {
        if (!signal.aborted && version === sequence.current) { setBusy(false); setError(failure instanceof Error ? failure.message : 'The report is unavailable. Retry.'); }
      }
      await accept(result);
    } catch (failure) {
      if (!signal.aborted && version === sequence.current) { setBusy(false); setError(failure instanceof Error ? failure.message : 'The report is unavailable. Retry.'); }
    }
  }, [base, company, generation, command, loadPage]);

  async function navigate(index: number) {
    if (!active || busy || index < 0) return;
    const cursor = index > pageIndex ? nextCursor : pageCursors[index];
    if (index > pageIndex && !cursor || index > 0 && cursor === undefined) return;
    setOperation('page'); setTargetPage(index); retryAction.current = () => { void navigate(index); };
    const version = sequence.current, abort = new AbortController();
    controller.current?.abort(); controller.current = abort; setBusy(true); setError('');
    try {
      const result = active.scope === 'ALL'
        ? await request<LivePage>('vouchers', 'POST', '/v1/companies/' + company + '/day-book/query', liveParameters(active, cursor), undefined, abort.signal)
        : null;
      if (result && !result.summary) throw new Error('The live activity summary is unavailable. Retry the report.');
      const page = result ? { rows: result.items, cursor: result.page.next_cursor ?? null } : await loadPage(job!.id, cursor, abort.signal);
      if (abort.signal.aborted || version !== sequence.current) return;
      setRows(page.rows); setNextCursor(page.cursor); setPageIndex(index);
      setPageCursors(previous => { const next = [...previous]; next[index] = cursor; return next; });
      if (result) { setSummary(result.summary); setObserved(result.observed_at); }
    } catch (failure) { if (!abort.signal.aborted && version === sequence.current) setError(failure instanceof Error ? failure.message : 'Unable to load this page. Retry.'); }
    finally { if (!abort.signal.aborted) setBusy(false); }
  }

  async function exportReport(format: 'CSV' | 'XLSX' | 'PDF', resume?: DayBookJob) {
    if (!job || !active || busy) return;
    setOperation('export'); setExportFormat(format); retryAction.current = () => { void exportReport(format, resume); };
    setBusy(true); setError(''); setExportJob(null);
    const version = sequence.current, abort = new AbortController();
    controller.current?.abort(); controller.current = abort;
    try {
      const first = resume ?? await command<DayBookJob>('/report-runs/' + job.id + '/exports', { format, view: active.mode === 'ACCOUNTING' ? 'accounting' : 'default', delivery: 'SINGLE' }, abort.signal);
      if (abort.signal.aborted || version !== sequence.current) return;
      let latest = first;
      retryAction.current = () => { void exportReport(format, latest); };
      setExportJob(first);
      const completed = await trackReportExport(company, first, abort.signal, value => {
        if (!abort.signal.aborted && version === sequence.current) { latest = value; setExportJob(value); }
      });
      if (abort.signal.aborted || version !== sequence.current) return;
      if (completed.status !== 'COMPLETE') {
        retryAction.current = () => { void exportReport(format); };
        throw new Error(reportExportFailure(completed));
      }
      setBusy(false);
    } catch (failure) { if (!abort.signal.aborted && version === sequence.current) { setExportJob(null); setBusy(false); setError(failure instanceof Error ? failure.message : 'Export unavailable.'); } }
  }

  async function refresh(filters: DayBookFilters) {
    if (filters.scope === 'ALL') { await run(filters); return; }
    const version = ++sequence.current, abort = new AbortController();
    controller.current?.abort(); controller.current = abort;
    timers.current.forEach(clearTimeout); timers.current = [];
    setOperation('refresh'); retryAction.current = () => { void refresh(filters); };
    setBusy(true); setError('');
    const latest = await discover(abort.signal);
    if (abort.signal.aborted || version !== sequence.current) return;
    if (latest) await run(filters, undefined, undefined, latest);
    else setBusy(false);
  }

  async function prepare(filters?: DayBookFilters) {
    setOperation('source'); retryAction.current = () => { void prepare(filters); };
    setBusy(true); setError('');
    const abort = new AbortController(); controller.current?.abort(); controller.current = abort;
    try {
      const created = await command<{ id: string }>('/report-generations', {}, abort.signal);
      async function check() {
        try {
          const source = await request<{ status: string }>('reports', 'GET', base + '/report-generations/' + created.id, undefined, undefined, abort.signal);
          if (abort.signal.aborted) return;
          if (source.status === 'READY') { const latest = await discover(abort.signal); setBusy(false); if (latest && filters) await run(filters, undefined, undefined, latest); }
          else if (['FAILED', 'BLOCKED', 'CANCELLED', 'QUARANTINED'].includes(source.status)) throw new Error('Report data could not be prepared. Ask your administrator to check reporting sources.');
          else timers.current.push(setTimeout(() => void check(), 2000));
        } catch (failure) { if (!abort.signal.aborted) { setBusy(false); setError(failure instanceof Error ? failure.message : 'Unable to prepare report data.'); } }
      }
      await check();
    } catch (failure) { if (!abort.signal.aborted) { setBusy(false); setError(failure instanceof Error ? failure.message : 'Unable to prepare report data.'); } }
  }
  return { definition, generation, sourceState, sourceError, rows, summary, job, exportJob, busy, error, observed,
    operation, exportFormat, targetPage, retry: () => retryAction.current?.(),
    nextCursor, pageIndex, pageCursors, active, run, navigate, exportReport, prepare, discover, refresh };
}
