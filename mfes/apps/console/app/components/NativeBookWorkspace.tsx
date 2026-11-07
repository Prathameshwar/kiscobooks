'use client';
import {prepareFinanceSource,financeSourceStale,financeRunFailure} from '../lib/finance-source';

import {controlWorkspaces,type ControlReportCode} from '../lib/control-workspace';
import {FinanceInvoiceReference} from './FinanceInvoiceReference';
import {FinanceSessionReference} from './FinanceSessionReference';
import {financeWorkspaces,financeLabels,financeValue,type FinanceReportCode} from '../lib/finance-workspace';
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  BookIcon, Button, Checkbox, Drawer, IconButton, Menu, Notice, PageHeader, PageNavigation, PreparationProgress, Select, TextField,
  DisplayConfigProvider, businessToday, useDisplayConfig, useFormatters, formatDate, formatMoney, formatQuantity, resolvedDisplay, SegmentedControl,
} from '@janso/ui';
import type { components } from '@janso/api-client/reports';
import type { FiscalYearChoice } from '../lib/company-context';
import { productFieldRequest as request } from '../lib/product-fields';
import { parameterText, parameterType, reportParameters, type ReportParameter } from '../lib/report-parameters';
import {
  canPreviewReportExport, primaryExportFormats, reportDownloadHref, reportExportFailure,
  reportExportLabels, reportExportOptions, trackReportExport, type ReportExportFormat,
} from '../lib/report-exports';
import { bookColumnLabel, bookParameterLabel, bookPreferencesKey, nativeBooks, stockSummary, type ReportBookKey } from '../lib/book-workspace';
import { ReportReference } from './ReportReference';
import {taxParameterLabels,taxWorkspaces,isTaxReport,taxValueLabel,type TaxReportCode,type TaxSummary} from '../lib/tax-workspace';
import {TaxReportTotals} from './TaxReportTotals';
import {AnalyticsInsights} from './AnalyticsInsights';
import {isAnalyticsReport,isDimensionProfit,profitColumnLabels,profitDetailColumns,analyticsDefaultColumns,analyticsLabels,analyticsWorkspaces,type AnalyticsCode,type AnalyticsSummary} from '../lib/analytics-workspace';
import { inventoryColumnVisible, inventoryCoverageHint, inventoryParameterLabels, inventorySummaryFields, inventoryWorkspaces, type InventoryReportCode } from '../lib/inventory-workspace';

type Schemas = components['schemas'];
type Definition = Schemas['DefinitionDetail'];
type Job = Schemas['JobDetail'];
type ResultRow = Schemas['ResultRow'];
type Filters = Record<string, string>;
type SavedView = { id: string; name: string; filters: Filters; view: string; columns?:Record<string,boolean> };
type ParentSelection = { title: string; page: number; cursors: (string | null)[]; columns: Record<string, boolean> };
type BookSummary = {
  code: string; record_count: number; entry_count: number; reduction_count?: number;
  voucher_count?: number; instrument_count?: number; unit?: string | null;
  amounts: Record<string, Record<string, string>>;
  quantities?: { inward: string; outward: string; closing: string };
};
type Props = {
  book: ReportBookKey; company: string; companyName: string; actor: string;
  permissions: readonly string[]; year?: FiscalYearChoice | null;
  inventoryReport?: InventoryReportCode;
  taxReport?: TaxReportCode;
  analyticsReport?: AnalyticsCode;
  controlReport?:ControlReportCode; years?:readonly FiscalYearChoice[];
  financeReport?: FinanceReportCode; initialRun?:string; initialParty?:string; trialBalanceRun?:string;
};

const pending = (job: Job | null) => !!job && ['QUEUED', 'RUNNING'].includes(job.status);
const references: Record<string, 'accounts' | 'account-groups' | 'parties' | 'items' | 'item-groups' | 'warehouses' | 'batches'> = {
  account_id: 'accounts', tax_ledger_id: 'accounts', group_id: 'account-groups', party_id: 'parties', item_id: 'items',
  location_id: 'warehouses', lot_id: 'batches',
};
const errors: Record<string, string> = {
  REPORT_IMPLEMENTATION_UNAVAILABLE: 'The report service was updated. Refresh the page and run the report again.',
  AUTHORITY_REVOKED: 'Your access changed. Refresh the page to check your current authority.',
  REPORT_VERIFICATION_FAILED: 'The frozen source could not be verified. Refresh the accounting data or narrow the selection.',
  REPORT_CAPACITY_EXCEEDED: 'This book exceeds its supported capacity. Choose a shorter period.',
  DEPENDENCY_UNAVAILABLE: 'A required reporting service is unavailable. Retry in a moment.',
};
const columnVisibility = (columns: readonly Schemas['Column'][], code = '', inventory = false) => Object.fromEntries(columns.map(column => [column.key, inventory || code === 'STOCK_SUMMARY' ? inventoryColumnVisible(code, column.key) ?? column.kind !== 'IDENTIFIER' : column.kind !== 'IDENTIFIER']));

async function snapshotInfo(base: string, identity: string, signal: AbortSignal, stock = false) {
  const source = await request<Schemas['SourceGenerationDetail']>('reports', 'GET', base + '/report-generations/' + identity, undefined, undefined, signal);
  if (source.id !== identity || source.status !== 'READY') throw new Error('The selected snapshot is no longer ready. Reload this book.');
  const control = source.manifest?.control as { coverage_start?: unknown; counts?: { inventory_report_record?: number } } | undefined;
  const start = typeof control?.coverage_start === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(control.coverage_start) ? control.coverage_start : null;
  const inventory = stock && control?.counts?.inventory_report_record !== 0 ? await request<Schemas['StockReferencePage']>('reports', 'GET', base + '/report-generations/' + identity + '/inventory?limit=1', undefined, undefined, signal) : null;
  if (inventory && inventory.generation_id !== identity) throw new Error('The inventory snapshot identity differs. Refresh stock data.');
  return { start, verifiedAt:source.verified_at, inventoryMissing: control?.counts?.inventory_report_record === 0 || stock && !inventory, inventory: inventory?.coverage ?? null };
}

async function readySnapshots(base: string, signal: AbortSignal, stock: boolean, maximum = 1) {
  const found: { id: string; info: Awaited<ReturnType<typeof snapshotInfo>> }[] = [];
  let cursor: string | null = null, inspected = 0;
  for (let page = 0; page < 20 && inspected < 20 && found.length < maximum; page++) {
    const generations: Schemas['ResourcePage'] = await request<Schemas['ResourcePage']>('reports', 'GET', base + '/report-generations?limit=50' + (cursor ? '&cursor=' + encodeURIComponent(cursor) : ''), undefined, undefined, signal);
    for (const candidate of generations.items.filter(item => item.status === 'READY')) {
      if (inspected++ >= 20 || found.length >= maximum) break;
      try {
        const info = await snapshotInfo(base, candidate.id, signal, stock);
        if (!stock || info.inventory) found.push({ id: candidate.id, info });
      } catch (error) {
        if (!stock || !(error instanceof Error) || !/(complete inventory snapshot|native stock changed|verified source snapshot)/i.test(error.message)) throw error;
      }
    }
    cursor = generations.page.next_cursor;
    if (!cursor) break;
  }
  return found;
}

function initialFilters(definition: Definition, today: string, year?: Pick<FiscalYearChoice, 'startDate' | 'endDate'> | null, coverage?: string | null): Filters {
  const properties = (definition.parameter_schema.properties ?? {}) as Record<string, ReportParameter>;
  const inYear = year && today >= year.startDate && today <= year.endDate;
  const to = year ? (definition.definition.code==='BALANCE_CONTINUITY'?year.endDate:inYear ? today : year.endDate) : today;
  const proposedFrom = year ? year.startDate : to.slice(0, 8) + '01';
  const from = ['BALANCE_CONTINUITY','INCOME_EXPENSE','PROFIT_MARGIN_ANALYSIS','EXPENSE_PROFIT_LEAKAGE'].includes(definition.definition.code) ? proposedFrom : coverage && coverage > proposedFrom ? coverage : proposedFrom;
  return Object.fromEntries(Object.entries(properties).map(([key, raw]) => {
    const fallback = key === 'date_from' ? from : key === 'date_to' || key === 'as_of' ? to : undefined;
    return [key, parameterText(raw.default ?? fallback)];
  }));
}

function safeViews(raw: string | null): SavedView[] {
  if (!raw || raw.length > 100_000) return [];
  try {
    const value = JSON.parse(raw) as { views?: unknown };
    if (!Array.isArray(value.views)) return [];
    return value.views.slice(0, 20).flatMap(item => {
      if (!item || typeof item !== 'object') return [];
      const row = item as SavedView;
      if (typeof row.id !== 'string' || typeof row.name !== 'string' || row.name.length > 80 || typeof row.view !== 'string' || !row.filters || typeof row.filters !== 'object') return [];
      if (Object.values(row.filters).some(entry => typeof entry !== 'string' || entry.length > 4096)) return [];
      return [row];
    });
  } catch { return []; }
}

export function NativeBookWorkspace({ book, company, companyName, actor, permissions, year, years, controlReport, inventoryReport, taxReport, analyticsReport, financeReport, initialRun, initialParty, trialBalanceRun }: Props) {
  const control=!!controlReport, finance=!!financeReport||control, managed=finance||!!analyticsReport;
  const stock = book === 'stock-summary';
  const analytics = !!analyticsReport;
  const tax = book === 'tax-report' && !analytics, enhanced=stock||tax||analytics||finance;
  const defaultColumns = (columns: readonly Schemas['Column'][], code: string) => finance ? Object.fromEntries(columns.map(column=>[column.key,!column.key.endsWith('_id')])) : analytics&&isAnalyticsReport(code) ? Object.fromEntries(columns.map(column=>[column.key,analyticsDefaultColumns.has(column.key)||column.key==='period'&&['BUYER_PROFIT','PRODUCT_PROFIT'].includes(code)])) : tax&&isTaxReport(code)?Object.fromEntries(columns.map(column=>[column.key,(code==='INVOICE_CREDIT_REGISTER'&&columns.some(item=>item.key==='event_amount')&&!columns.some(item=>item.key==='recorded_tax')?['period','posting_date','event_date','bill_reference','account_name','tax_code','action','reference','event_amount','currency']:taxWorkspaces[code].columns).includes(column.key)])):columnVisibility(columns, code, stock);
  const config = controlReport ? controlWorkspaces[controlReport] : financeReport ? financeWorkspaces[financeReport] : analyticsReport ? analyticsWorkspaces[analyticsReport] : book === 'tax-report' ? taxWorkspaces[taxReport??'INVOICE_TAX_REGISTER'] : stock ? inventoryReport ? inventoryWorkspaces[inventoryReport] : stockSummary : nativeBooks[book];
  const base = '/v2/companies/' + company;
  const displayConfig = useDisplayConfig();
  const yearStart = year?.startDate, yearEnd = year?.endDate;
  const format = useFormatters();
  const preferenceKey = bookPreferencesKey(actor, company, book) + (controlReport?':'+controlReport:financeReport?':'+financeReport:analyticsReport?':'+analyticsReport:taxReport?':'+taxReport:inventoryReport && inventoryReport !== 'STOCK_SUMMARY' ? ':' + inventoryReport : '');
  const [runDefinition,setRunDefinition]=useState<Definition|null>(null);
  const [queryRoot,setQueryRoot]=useState<Job|null>(null),[search,setSearch]=useState(''),[sort,setSort]=useState('ordinal'),[queryField,setQueryField]=useState(''),[queryValue,setQueryValue]=useState('');
  const [definition, setDefinition] = useState<Definition | null>(null);
  const [generation, setGeneration] = useState('');
  const [sourceStart, setSourceStart] = useState<string | null>(null);
  const [verifiedAt,setVerifiedAt]=useState<string|null>(null);
  const [inventoryMissing, setInventoryMissing] = useState(false);
  const [inventoryCoverage, setInventoryCoverage] = useState<Schemas['StockReferencePage']['coverage'] | null>(null);
  const [stockSources, setStockSources] = useState<{id:string; coverage:Schemas['StockReferencePage']['coverage']}[]>([]);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [history, setHistory] = useState<Schemas['JobListItem'][]>([]);
  const [historyCursor, setHistoryCursor] = useState<string | null>(null);
  const [filters, setFilters] = useState<Filters>({});
  const [activeFilters, setActiveFilters] = useState<Filters | null>(null);
  const [view, setView] = useState('default');
  const [run, setRun] = useState<Job | null>(null);
  const [rows, setRows] = useState<ResultRow[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [pageCursors, setPageCursors] = useState<(string | null)[]>([null]);
  const [page, setPage] = useState(0);
  const [busy, setBusy] = useState(true);
  const [candidate,setCandidate]=useState<Job|null>(null),[denied,setDenied]=useState(false),[financeFilters,setFinanceFilters]=useState(false);
  const candidateSource=useRef<Schemas['SourceGenerationDetail']|null>(null);
  const downloaded=useRef(new Set<string>());
  const [operation, setOperation] = useState<'load' | 'run' | 'page' | 'export' | 'source'>('load');
  const [message, setMessage] = useState('');
  const [exportJob, setExportJob] = useState<Job | null>(null);
  const [exportFormat, setExportFormat] = useState<ReportExportFormat | null>(null);
  const [delivery, setDelivery] = useState<'SINGLE' | 'PACKAGE'>('SINGLE');
  const [visible, setVisible] = useState<Record<string, boolean>>({});
  const [referenceReady, setReferenceReady] = useState<Record<string, string | null>>({});
  const [saved, setSaved] = useState<SavedView[]>([]);
  const [selectedSaved, setSelectedSaved] = useState('');
  const [saveName, setSaveName] = useState('');
  const [advanced, setAdvanced] = useState(false);
  const [viewsOpen, setViewsOpen] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const retryExport = useRef<(() => void) | null>(null);
  const retryLoad = useRef<(() => void) | null>(null);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);
  const started = useRef(false);
  const keys = useRef(new Map<string, string>());
  const parentSelections = useRef(new Map<string, ParentSelection>());
  const pendingTaxColumns = useRef<Record<string, boolean> | null>(null);

  const command = useCallback(async <T,>(path: string, body: unknown, signal?: AbortSignal) => {
    const payload = JSON.stringify({ path, body });
    if (!keys.current.has(payload)) keys.current.set(payload, crypto.randomUUID());
    const result = await request<T>('reports', 'POST', base + path, body, keys.current.get(payload), signal);
    keys.current.delete(payload);
    signal?.throwIfAborted();
    return result;
  }, [base]);

  function failure(error:unknown,fallback:string){
    if(managed&&error&&typeof error==='object'&&'status' in error&&[401,403].includes(Number(error.status))){
      setDenied(true);setRun(null);setRows([]);setExportJob(null);controller.current?.abort();
    }
    setMessage(error instanceof Error?error.message:fallback);
  }
  const prepareFinance=useCallback(async(previous:string,signal:AbortSignal)=>{
    setOperation('source');
    const source=await prepareFinanceSource(base,previous,signal,command,candidateSource,()=>setOperation('source'));
    const info=await snapshotInfo(base,source.id,signal);signal.throwIfAborted();return {id:source.id,info};
  },[base,command]);
  async function stopFinance(){
    if(!candidate||!pending(candidate))return;
    const stopping=candidate;controller.current?.abort();const abort=new AbortController();controller.current=abort;setBusy(true);
    try{await command('/report-runs/'+stopping.id+'/cancel',{},abort.signal);setCandidate(null);setMessage('Report stopped. Apply filters to run it again.');}
    catch(error){if(!abort.signal.aborted)failure(error,'Unable to stop this report.');}
    finally{if(!abort.signal.aborted)setBusy(false);}
  }

  const discover = useCallback(async (signal: AbortSignal) => {
    const found = await request<Definition>('reports', 'GET', base + '/report-definitions/' + config.code, undefined, undefined, signal);
    let ready = initialRun && managed ? undefined : (await readySnapshots(base, signal, stock))[0];
    if(managed&&!initialRun&&(!ready||financeSourceStale(ready.info.verifiedAt))&&found.run_enabled&&permissions.includes('report.definition.manage'))ready=await prepareFinance(ready?.id??'',signal);
    const source = ready?.info ?? null;
    const initial = initialFilters(found, stock && source?.inventory ? source.inventory.as_of : businessToday(displayConfig.timezone), yearStart && yearEnd ? { startDate: yearStart, endDate: yearEnd } : undefined, source?.start);
    if (stock && source?.inventory) { initial.as_of = source.inventory.as_of; if(config.code==='STOCK_REORDER'&&source.inventory.reservations_complete===false) initial.quantity_basis='ELIGIBLE'; }
    if(finance&&initialParty&&(found.parameter_schema.properties as Record<string,unknown>|undefined)?.party_id)initial.party_id=initialParty;
    const allowed = new Set(Object.keys(found.parameter_schema.properties ?? {}));
    let storedRaw:string|null=null;try{storedRaw=window.localStorage.getItem(preferenceKey);}catch{/* Browser preferences are optional. */}
    const stored = safeViews(storedRaw).map(item => ({ ...item, filters: Object.fromEntries(Object.entries(item.filters).filter(([key]) => allowed.has(key))) }));
    setDefinition(found);
    setSourceStart(source?.start ?? null);setVerifiedAt(source?.verifiedAt??null);
    setInventoryMissing(source?.inventoryMissing ?? false);
    setInventoryCoverage(source?.inventory ?? null);
    if (stock) setStockSources(ready && source?.inventory ? [{ id: ready.id, coverage: source.inventory }] : []);
    started.current = false;
    parentSelections.current.clear();
    pendingTaxColumns.current = null;
    setGeneration(ready?.id ?? '');
    setFilters(initial);if(finance)setFinanceFilters(((found.parameter_schema.required??[]) as string[]).some(key=>!initial[key]));
    setView(found.definition.views[0]?.key ?? 'default');
    setSaved(stored);
    setVisible(defaultColumns(found.definition.views[0]?.columns ?? [], config.code));
  }, [base, config.code, displayConfig.timezone, preferenceKey, yearStart, yearEnd, stock, finance, managed, initialRun, initialParty, prepareFinance, permissions.join('|')]);

  useEffect(() => {
    let active: AbortController | null = null;
    const load = () => {
      active?.abort(); const abort = new AbortController(); active = abort; controller.current = abort;
      retryLoad.current = null; setOperation('load'); setBusy(true); setMessage('');
      void discover(abort.signal)
        .then(() => { if (!abort.signal.aborted) retryLoad.current = null; })
        .catch(error => { if (!abort.signal.aborted) { retryLoad.current = load; failure(error,'This book is unavailable.'); } })
        .finally(() => { if (!abort.signal.aborted) setBusy(false); });
    };
    load();
    return () => { active?.abort(); controller.current?.abort(); timers.current.forEach(clearTimeout); };
  }, [discover]);

  async function loadRows(identity: string, cursor: string | null, signal: AbortSignal) {
    return request<Schemas['ResultPage']>('reports', 'GET', base + '/report-runs/' + identity + '/rows?limit=50' + (cursor ? '&cursor=' + encodeURIComponent(cursor) : ''), undefined, undefined, signal);
  }

  async function runReport(nextFilters = filters, nextView = view, source = generation, trustSavedReferences = false, continueBusy = false) {
    if (!definition || !source || busy && !continueBusy) return;
    if (config.code === 'ITEM_LEDGER' && inventoryMissing && source === generation) return;
    if (stock && source === generation && nextFilters.as_of !== inventoryCoverage?.as_of) { setMessage('Choose a date with a verified stock snapshot. Load snapshot dates to find earlier reports.'); return; }
    const coverageError=stock?inventoryCoverageHint(config.code,inventoryCoverage,nextFilters):undefined;
    if(coverageError){setMessage(coverageError);return;}
    if (stock && nextFilters.date_from && inventoryCoverage && nextFilters.date_from < inventoryCoverage.history_start) { setMessage('Choose a From date within the retained stock history.'); return; }
    const properties = (definition.parameter_schema.properties ?? {}) as Record<string, ReportParameter>;
    const required = (definition.parameter_schema.required ?? []) as string[];
    const missing = required.find(key => !nextFilters[String(key)]);
    if (missing) { if(finance)setFinanceFilters(true);setMessage('Choose ' + String(missing).replaceAll('_', ' ') + ' before preparing this book.'); return; }
    if (nextFilters.date_from && nextFilters.date_to && nextFilters.date_from > nextFilters.date_to || nextFilters.date_from && nextFilters.as_of && nextFilters.date_from > nextFilters.as_of) { setMessage('The start date must be on or before the end date.'); return; }
    if (properties.comparative_from && ((nextFilters.comparative_from && !nextFilters.comparative_to) || (!nextFilters.comparative_from && nextFilters.comparative_to))) { setMessage('Choose both comparative dates or clear both.'); return; }
    if (nextFilters.comparative_from && nextFilters.comparative_to && nextFilters.comparative_from > nextFilters.comparative_to) { setMessage('The comparative start date must be on or before its end date.'); return; }
    if (nextFilters.basis === 'TRANSACTION' && !/^[A-Z]{3}$/.test(nextFilters.currency ?? '')) { setMessage('Choose a three-letter transaction currency.'); return; }
    const invalidIdentifier = Object.entries(nextFilters).find(([key, value]) => key.endsWith('_id') && value && !references[key] && !/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(value));
    if (invalidIdentifier) { setMessage('Choose a valid ' + invalidIdentifier[0].replace('_id', '').replaceAll('_', ' ') + '.'); return; }
    if(finance&&nextFilters.invoice_id&&referenceReady.invoice_id!==nextFilters.invoice_id&&!trustSavedReferences){setMessage('Wait for the selected invoice to be verified.');return;}
    if(finance&&nextFilters.session_id&&referenceReady.session_id!==nextFilters.session_id&&!trustSavedReferences){setMessage('Wait for the selected reconciliation session to be verified.');return;}
    if (!trustSavedReferences && Object.keys(referenceSources).some(key => nextFilters[key] && referenceReady[key] !== nextFilters[key])) { setMessage('Wait for the selected reference to be verified.'); return; }
    setOperation('run'); setBusy(true); setMessage(''); setExportJob(null);setCandidate(null);
    controller.current?.abort(); const abort = new AbortController(); controller.current = abort;
    try {
      if(managed&&source===generation&&financeSourceStale(verifiedAt)&&permissions.includes('report.definition.manage')){const fresh=await prepareFinance(source,abort.signal);source=fresh.id;setGeneration(source);setSourceStart(fresh.info.start);setVerifiedAt(fresh.info.verifiedAt??null);setOperation('run');}
      const parameters = reportParameters(properties, nextFilters);
      let result = await command<Job>('/report-runs', { code: config.code, version: definition.definition.version, generation_id: source, parameters, view: nextView }, abort.signal);
      let recovered=false;
      const accept = async (): Promise<void> => {
        if(managed&&result.code!==config.code)throw new Error('The report response does not match this workspace. Retry.');
        if(managed)setCandidate(result);
        if (abort.signal.aborted) return;
        if (pending(result)) {
          await new Promise<void>(resolve => { const timer = setTimeout(resolve, 1500); timers.current.push(timer); });
          result = await request<Job>('reports', 'GET', base + '/report-runs/' + result.id, undefined, undefined, abort.signal);
          return accept();
        }
        if(managed&&result.status==='BLOCKED'&&result.failure_code==='REPORT_VERIFICATION_FAILED'&&!recovered&&permissions.includes('report.definition.manage')){
          recovered=true;const prepared=await prepareFinance(source,abort.signal);
          setGeneration(prepared.id);setSourceStart(prepared.info.start);setVerifiedAt(prepared.info.verifiedAt??null);setOperation('run');
          result=await command<Job>('/report-runs',{code:config.code,version:definition.definition.version,generation_id:prepared.id,parameters,view:nextView},abort.signal);
          return accept();
        }
        if (result.status !== 'COMPLETE') throw new Error(managed?financeRunFailure(result.failure_code,config.title):errors[result.failure_code ?? ''] ?? 'The book could not be prepared. Retry or adjust the filters.');
        const resultPage = await loadRows(result.id, null, abort.signal);
        abort.signal.throwIfAborted();setCandidate(null);if(finance)setFinanceFilters(false);
        setRunDefinition(null);setQueryRoot(null);setSearch('');setSort('ordinal');setQueryField('');setQueryValue('');setRun(result); setRows(resultPage.items); setNextCursor(resultPage.page.next_cursor ?? null);
        const preparedColumns = tax||managed ? pendingTaxColumns.current : null;
        setPageCursors([null]); setPage(0); setActiveFilters(nextFilters); setVisible(current => ({ ...defaultColumns(result.views.find(item => item.key === nextView)?.columns ?? [], result.code), ...(preparedColumns ?? current) }));
        pendingTaxColumns.current = null;
      };
      await accept();
    } catch (error) { if (!abort.signal.aborted) failure(error,'The report is unavailable.'); }
    finally { if (!abort.signal.aborted) {setBusy(false);setCandidate(null);} }
  }

  async function refreshLatest() {
    if (!definition || busy) return;
    setOperation('load'); setBusy(true); setMessage('');
    const abort = new AbortController(); controller.current?.abort(); controller.current = abort;
    try {
      const prepared = (await readySnapshots(base, abort.signal, stock))[0];
      if (!prepared) { if (!stock) { setGeneration(''); setSourceStart(null); } setMessage(stock ? 'No complete stock snapshot is available. Select Refresh stock data to prepare one.' : 'There is no prepared snapshot yet.'); return; }
      const latest = prepared.id, source = prepared.info;
      setSourceStart(source.start);setVerifiedAt(source.verifiedAt??null); setInventoryMissing(source.inventoryMissing);
      setInventoryCoverage(source.inventory);
      if (stock && !source.inventory) { setMessage('This source has no complete stock snapshot. Select Refresh stock data to prepare one.'); return; }
      if (stock && source.inventory) { setStockSources(previous => [{id:latest,coverage:source.inventory!},...previous.filter(item=>item.id!==latest)]); setFilters(previous => ({...previous,as_of:source.inventory!.as_of})); }
      if (config.code === 'ITEM_LEDGER' && source.inventoryMissing) { setGeneration(latest); return; }
      setGeneration(latest); await runReport(stock && source.inventory ? {...filters,as_of:source.inventory.as_of} : filters, view, latest, false, true);
    } catch (error) { if (!abort.signal.aborted) failure(error,'Unable to refresh this book.'); }
    finally { if (!abort.signal.aborted) setBusy(false); }
  }

  async function navigate(target: number) {
    if (!run || busy || target < 0) return;
    const cursor = target > page ? nextCursor : pageCursors[target];
    if (target > page && !cursor || target > 0 && cursor === undefined) return;
    setOperation('page'); setBusy(true); setMessage('');
    controller.current?.abort(); const abort = new AbortController(); controller.current = abort;
    try {
      const result = await loadRows(run.id, cursor ?? null, abort.signal);
      setRows(result.items); setNextCursor(result.page.next_cursor ?? null); setPage(target);
      setPageCursors(previous => { const next = [...previous]; next[target] = cursor ?? null; return next; });
    } catch (error) { if (!abort.signal.aborted) failure(error,'Unable to load this page.'); }
    finally { if (!abort.signal.aborted) setBusy(false); }
  }

  async function selectRun(next: Job, signal: AbortSignal, selection?: ParentSelection) {
    setExportJob(null); retryExport.current = null;
    let result = next;
    while (pending(result) && !signal.aborted) {
      if(managed)setCandidate(result);
      await new Promise<void>(resolve => { const timer = setTimeout(resolve, 1500); timers.current.push(timer); });
      result = await request<Job>('reports', 'GET', base + '/report-runs/' + result.id, undefined, undefined, signal);
    }
    if (result.status !== 'COMPLETE') throw new Error(errors[result.failure_code ?? ''] ?? 'The drill-down could not be prepared.');
    if(managed&&result.code!==config.code){const detail=await request<Definition>('reports','GET',base+'/report-definitions/'+result.code,undefined,undefined,signal);if(detail.definition.code!==result.code)throw new Error('The drill-down definition differs. Retry.');setRunDefinition(detail);}else setRunDefinition(null);
    const resultPage = await loadRows(result.id, selection?.cursors[selection.page] ?? null, signal);
    signal.throwIfAborted();setCandidate(null);
    const nextView = result.view ?? result.views[0]?.key ?? 'default';
    pendingTaxColumns.current = null;
    setRun(result); if (!enhanced || result.code === config.code) setView(nextView);
    setRows(resultPage.items); setNextCursor(resultPage.page.next_cursor ?? null);
    setPageCursors(selection?.cursors ?? [null]); setPage(selection?.page ?? 0);
    const allowedColumns = result.views.find(item => item.key === nextView)?.columns ?? [];
    setVisible(selection ? Object.fromEntries(allowedColumns.map(column => [column.key, selection.columns[column.key] !== false])) : defaultColumns(allowedColumns, result.code));
  }

  async function openDrilldown(link: Schemas['DrilldownLink']) {
    if (!run || busy || link.method !== 'POST') return;
    setOperation('run'); setBusy(true); setMessage('');
    controller.current?.abort(); const abort = new AbortController(); controller.current = abort;
    try {
      setQueryRoot(null);setSearch('');setSort('ordinal');setQueryField('');setQueryValue('');
      const child = await command<Job>('/report-runs/' + run.id + '/drilldowns', { token: link.token }, abort.signal);
      if (enhanced) {
        parentSelections.current.set(run.id, { title: run.title, page, cursors: [...pageCursors], columns: { ...visible } });
        if (parentSelections.current.size > 20) parentSelections.current.delete(parentSelections.current.keys().next().value!);
      }
      await selectRun(child, abort.signal);
    }
    catch (error) { if (!abort.signal.aborted) failure(error,'Drill-down unavailable.'); }
    finally { if (!abort.signal.aborted) setBusy(false); }
  }

  async function returnToParent() {
    if (!run?.origin || busy) return;
    setOperation('page'); setBusy(true); setMessage('');
    controller.current?.abort(); const abort = new AbortController(); controller.current = abort;
    try {
      setQueryRoot(null);setSearch('');setSort('ordinal');setQueryField('');setQueryValue('');
      const identity = run.origin.parent_id;
      await selectRun(await request<Job>('reports', 'GET', base + '/report-runs/' + identity, undefined, undefined, abort.signal), abort.signal, parentSelections.current.get(identity));
      parentSelections.current.delete(identity);
    }
    catch (error) { if (!abort.signal.aborted) failure(error,'The parent book is unavailable.'); }
    finally { if (!abort.signal.aborted) setBusy(false); }
  }

  async function exportReport(formatName: ReportExportFormat, resume?: Job, selectedDelivery = delivery) {
    if (!run || busy) return;
    setOperation('export'); setExportFormat(formatName); setBusy(true); setMessage(''); setExportJob(null);
    retryExport.current = () => { void exportReport(formatName, resume, selectedDelivery); };
    controller.current?.abort(); const abort = new AbortController(); controller.current = abort;
    try {
      const packaged = selectedDelivery === 'PACKAGE' && ['PDF', 'HTML'].includes(formatName);
      const first = resume ?? await command<Job>('/report-runs/' + run.id + '/exports', { format: formatName, view:run.view??view, delivery: packaged ? 'PACKAGE' : 'SINGLE' }, abort.signal);
      let latest = first; setExportJob(first);
      retryExport.current = () => { void exportReport(formatName, latest, selectedDelivery); };
      const result = await trackReportExport(company, first, abort.signal, value => { latest = value; setExportJob(value); });
      if (result.status !== 'COMPLETE') {
        retryExport.current = () => { void exportReport(formatName, undefined, selectedDelivery); };
        throw new Error(reportExportFailure(result));
      }
      setExportJob(result); retryExport.current = null;
      if(managed&&!downloaded.current.has(result.id)){
        downloaded.current.add(result.id);const link=document.createElement('a');link.href=reportDownloadHref(company,result.id);link.download='';document.body.append(link);try{link.click();}finally{link.remove();}
      }
    } catch (error) { if (!abort.signal.aborted) failure(error,'Export unavailable.'); }
    finally { if (!abort.signal.aborted) setBusy(false); }
  }

  async function refreshSource() {
    if (busy) return;
    setOperation('source'); setBusy(true); setMessage('');
    controller.current?.abort(); const abort = new AbortController(); controller.current = abort;
    try {
      if(managed){const prepared=await prepareFinance(generation,abort.signal);setGeneration(prepared.id);setSourceStart(prepared.info.start);setVerifiedAt(prepared.info.verifiedAt??null);await runReport(filters,view,prepared.id,false,true);return;}
      let source = await command<Schemas['SourceGenerationDetail']>('/report-generations', !stock && config.code !== 'ITEM_LEDGER' && generation ? { strategy: 'REFRESH', base_generation_id: generation } : { strategy: 'FRESH' }, abort.signal);
      if (enhanced) {
        while (['PENDING','BUILDING','QUEUED','RUNNING'].includes(source.status) && !abort.signal.aborted) {
          await new Promise<void>(resolve => { const timer = setTimeout(resolve, 1500); timers.current.push(timer); });
          source = await request('reports','GET',base+'/report-generations/'+source.id,undefined,undefined,abort.signal);
        }
        if (source.status !== 'READY') throw new Error(tax?'The tax snapshot could not be prepared. Retry Refresh tax data.':'The inventory snapshot could not be prepared. Retry Refresh stock data.');
        const info = await snapshotInfo(base,source.id,abort.signal,stock);
        if (stock&&!info.inventory) throw new Error('The stock owner has not published complete inventory coverage.');
        setGeneration(source.id);setSourceStart(info.start);setVerifiedAt(info.verifiedAt??null);setInventoryCoverage(info.inventory??null);setInventoryMissing(false);
        if(stock&&info.inventory)setStockSources(previous=>[{id:source.id,coverage:info.inventory!},...previous.filter(item=>item.id!==source.id)]);
        const nextFilters=stock&&info.inventory?{...filters,as_of:info.inventory.as_of}:filters;setFilters(nextFilters);
        await runReport(nextFilters,view,source.id,false,true);
      } else setMessage('Accounting data refresh requested. Refresh this book after the snapshot is ready.');
    } catch (error) { if (!abort.signal.aborted) failure(error,'Unable to refresh accounting data.'); }
    finally { if (!abort.signal.aborted) setBusy(false); }
  }

  function saveView() {
    const name = saveName.trim(); if (!name || name.length > 80) { setMessage('Enter a saved-view name of up to 80 characters.'); return; }
    if (saved.length >= 20) { setMessage('You can save up to 20 views. Delete an unused view first.'); return; }
    const item = { id: crypto.randomUUID(), name, filters, view, ...(enhanced?{columns:tax||managed?pendingTaxColumns.current??visible:visible}:{}) };
    const next = [...saved, item]; setSaved(next); setSelectedSaved(item.id); setSaveName('');
    window.localStorage.setItem(preferenceKey, JSON.stringify({ views: next }));
  }
  function deleteView() {
    const next = saved.filter(item => item.id !== selectedSaved); setSaved(next); setSelectedSaved('');
    window.localStorage.setItem(preferenceKey, JSON.stringify({ views: next }));
  }
  function chooseView(id: string) {
    setSelectedSaved(id); const item = saved.find(entry => entry.id === id); if (!item) return;
    setFilters(stock ? {...item.filters,as_of:inventoryCoverage?.as_of??filters.as_of} : item.filters); setView(item.view); setViewsOpen(false);
    if (enhanced) {
      const savedColumns = definition?.definition.views.find(entry => entry.key === item.view)?.columns ?? [];
      const preferences = item.columns && Object.values(item.columns).every(value => typeof value === 'boolean') ? item.columns : {};
      const restored = { ...defaultColumns(savedColumns, config.code), ...Object.fromEntries(Object.entries(preferences).filter(([key]) => savedColumns.some(column => column.key === key))) };
      if (tax||managed) pendingTaxColumns.current = restored;
      else setVisible(restored);
    }
    if (!stock) void runReport(item.filters, item.view, generation, true);
  }

  const properties = (definition?.parameter_schema.properties ?? {}) as Record<string, ReportParameter>;
  const required = (definition?.parameter_schema.required ?? []) as string[];
  const displayedView = run?.view ?? view;
  const currentView = run?.views.find(item => item.key === displayedView) ?? definition?.definition.views.find(item => item.key === displayedView);
  const columns = (currentView?.columns ?? []).filter(column => visible[column.key] !== false);
  const columnLabel = (column: Schemas['Column']) => isDimensionProfit(run?.code??config.code)?profitColumnLabels[column.key]??bookColumnLabel(column.key,column.title):finance ? financeLabels[column.key]??bookColumnLabel(column.key,column.title) : tax&&(run?.code??config.code)==='TAX_GL_BRIDGE'&&column.key==='account_name'?'Tax ledger':(run?.code ?? config.code) === 'STOCK_SUMMARY' ? ({ quantity:'Closing stock', carrying_value:'Stock value' } as Record<string,string>)[column.key] ?? bookColumnLabel(column.key,column.title) : bookColumnLabel(column.key,column.title);
  const bookSummary = (run && (run.result?.evidence as { book_summary?: BookSummary } | undefined)?.book_summary?.code === run.code
    ? (run?.result?.evidence as { book_summary: BookSummary }).book_summary : null);
  const pinnedResult = (run?.result as { plan?: { mode?: string } } | null)?.plan?.mode === 'PINNED_QUERY';
  const totalRows = bookSummary?.record_count ?? (run ? pinnedResult ? null : run.completed_rows : null);
  const dirty = activeFilters !== null && (JSON.stringify(filters) !== JSON.stringify(activeFilters) || (!enhanced || !run?.origin) && view !== run?.view || stock && generation !== run?.generation_id);
  const stockSourceUnavailable = config.code === 'ITEM_LEDGER' && inventoryMissing;
  const coverageHint=stock?inventoryCoverageHint(config.code,inventoryCoverage,filters):undefined;
  const sourceHint = coverageHint??(stockSourceUnavailable && !run ? 'Stock Ledger needs a complete inventory snapshot before print or export. Update accounting data after the stock source is prepared.' : undefined);
  const missingParameter = required.find(key => !filters[key]);
  const stockDateUnavailable = stock && !!filters.as_of && filters.as_of !== inventoryCoverage?.as_of;
  const preparationHint = !run && !sourceHint && generation && missingParameter ? 'Choose ' + bookParameterLabel(book, missingParameter, properties[missingParameter]?.title) + ' to prepare this book for print and export.' : undefined;
  const canExport = permissions.includes('report.export');
  const emptyDescription = stock && config.code === 'STOCK_REORDER' && (run?.result?.evidence as { inventory_metrics?: { configured_count?: number } } | undefined)?.inventory_metrics?.configured_count === 0
    ? 'No reorder levels are configured for this selection. Configure replenishment settings for the relevant products and warehouses, then refresh stock data.'
    : config.empty;
  const selectedDefinition=runDefinition??definition;
  const queryCapabilities=selectedDefinition?.navigation as {method?:string;search_fields?:string[];sort_fields?:string[];filters?:Record<string,string>}|undefined;
  const selection=run?.result?.selection;
  const exportItems = reportExportOptions({
    run, limits: selectedDefinition?.export_limits, view: displayedView, formats: primaryExportFormats, delivery,
    packageLimits: selectedDefinition?.package_limits, rowCount: totalRows,
  });
  const printUnavailable = reportExportOptions({
    run, limits: selectedDefinition?.export_limits, view: displayedView, formats: ['PDF'], delivery: 'SINGLE',
    packageLimits: selectedDefinition?.package_limits, rowCount: totalRows,
  })[0]?.disabledReason;
  const packagePdfUnavailable = reportExportOptions({
    run, limits: selectedDefinition?.export_limits, view: displayedView, formats: ['PDF'], delivery: 'PACKAGE',
    packageLimits: selectedDefinition?.package_limits, rowCount: totalRows,
  })[0]?.disabledReason;
  const printReason = dirty ? 'Apply the changed filters before printing.' : sourceHint ?? preparationHint ?? printUnavailable ?? 'Export all matching rows as a printable PDF';
  const showPackageDelivery = delivery === 'PACKAGE' || (!!printUnavailable && !packagePdfUnavailable);
  const referenceSources = useMemo<Record<string, 'accounts' | 'account-groups' | 'parties' | 'items' | 'item-groups' | 'warehouses' | 'batches'>>(() => ({ ...references, group_id: config.code === 'ITEM_LEDGER' || config.code === 'PRODUCT_PROFIT' || stock ? 'item-groups' : 'account-groups' }), [config.code, stock]);
  const taxReferencePending = tax && Object.keys(referenceSources).some(key => filters[key] && referenceReady[key] !== filters[key]);
  useEffect(() => {
    if (started.current || busy || run || message || !definition) return;
    if(managed&&initialRun){started.current=true;void openHistory(initialRun,true);return;}
    if(stockSourceUnavailable || coverageHint || !definition.run_enabled || !generation)return;
    if(finance&&filters.session_id&&referenceReady.session_id!==filters.session_id)return;
    if (required.some(key => !filters[key]) || Object.keys(referenceSources).some(key => filters[key] && referenceReady[key] !== filters[key])) return;
    started.current = true;
    void runReport();
  }, [busy, run, message, stockSourceUnavailable, coverageHint, definition, generation, required, filters, referenceSources, referenceReady, runReport]);
  function cell(column: Schemas['Column'], row: ResultRow) {
    if(finance&&typeof row.data[column.key]==='string'&&['row_kind','period','direction','role','kind','voucher_kind','invoice_kind','mode','status','side','purpose','scope','effect','recognition','state','aging_bucket'].includes(column.key))return financeValue(String(row.data[column.key]));
    if(finance&&column.kind==='BOOLEAN')return row.data[column.key]===true?'Yes':row.data[column.key]===false?'No':'Unknown';
    if(analytics && row.data[column.key]==null && ['cost','gross_profit','margin_percent','change_percent',...(isDimensionProfit(run?.code)?['comparison_amount','change_amount']:[])].includes(column.key)) return 'Unavailable';
    if(analytics && column.key.endsWith('_percent') && typeof row.data[column.key]==='string') return formatQuantity(String(row.data[column.key]),frozenDisplay)+'%';
    if(analytics&&column.key==='direction')return row.data.direction==='CREDIT'?'Unapplied credit':row.data.direction==='DEBT'?'Outstanding bill':String(row.data.direction??'—');
    if((tax||analytics)&&typeof row.data[column.key]==='string'&&['period','row_kind','action','invoice_kind','direction','tax_purpose','treatment','credit_state','side','segment','exception','classification','cost_status','stock_status','movement_kind'].includes(column.key))return taxValueLabel(String(row.data[column.key]));
    if (stock && column.key === 'action' && row.data.row_kind === 'OPENING') return 'Opening balance';
    const value = row.data[column.key];
    if(managed&&typeof value==='string'&&run?.display){const frozen=resolvedDisplay(run.display);if(column.kind==='MONEY')return formatMoney(value,frozen,{display:'none'});if(column.kind==='DATE')return formatDate(value,frozen);if(column.kind==='DECIMAL')return formatQuantity(value,frozen);} if(stock&&column.kind==='BOOLEAN'&&value==null)return 'Unknown'; if (value === null || value === undefined || value === '') return '—';
    if (stock && column.kind==='BOOLEAN') return value===true?'Yes':value===false?'No':'Unknown';
    if (stock && typeof value === 'string' && ['owner','custody','reservation_status','valuation_status','action','status','row_kind','costing_method','provenance','orders_status'].includes(column.key)) return ({RECEIPT:'Receipt',SALE:'Sale',CUSTOMER_RETURN:'Customer return',SUPPLIER_RETURN:'Supplier return',TRANSFER_IN:'Transfer in',TRANSFER_OUT:'Transfer out',ADJUSTMENT:'Adjustment',CONSUMPTION:'Consumption',PRODUCTION:'Production',OWN:'Company owned',THIRD_PARTY:'Third party',LOCAL:'In warehouse',TRANSIT:'In transit',EXTERNAL:'External custody',COMPLETE:'Verified',UNAVAILABLE:'Unavailable',EXPIRED:'Expired',NEAR_EXPIRY:'Near expiry',UNKNOWN_EXPIRY:'Missing expiry',BATCH_POSITION:'Current balance',POSITION:'Stock position',GL_CONTROL:'Control reconciliation',COST_LAYER:'FIFO layer',COST_POOL:'Cost pool',BATCH_MOVEMENT:'Batch movement',UNIT_MOVEMENT:'Serial movement',MOVING_AVERAGE:'Moving average',KNOWN:'Known',UNKNOWN:'Unknown',ASSUMED:'Assumed',NOT_INCLUDED:'Not included'} as Record<string,string>)[value] ?? value.replaceAll('_',' ').toLowerCase();
    if (typeof value === 'string') {
      if (column.kind === 'MONEY') return format.money(value, { display: 'none' });
      if (column.kind === 'DECIMAL') return format.quantity(value);
      if (column.kind === 'DATE') return format.date(value);
    }
    return typeof value === 'object' ? JSON.stringify(value) : String(value);
  }
  const progress = busy ? ({ load: 'Loading book…', run: 'Preparing verified results…', page: 'Loading report page…', export: exportFormat ? 'Preparing ' + reportExportLabels[exportFormat] + '…' : 'Preparing private export…', source: 'Requesting fresh accounting data…' }[operation]) : '';
  const loadingReport = busy && operation !== 'export';
  const parameterEntries = Object.entries(properties);
  const primaryEntries = parameterEntries.filter(([key]) => config.primaryFilters.includes(key)).sort(([a],[b])=>config.primaryFilters.indexOf(a)-config.primaryFilters.indexOf(b));
  const advancedEntries = parameterEntries.filter(([key]) => !config.primaryFilters.includes(key));
  const advancedCount = advancedEntries.filter(([key, raw]) => {
    const value = filters[key] ?? '', defaultValue = parameterText(raw.default);
    return value !== '' && value !== defaultValue;
  }).length;
  const currencies = Object.entries(bookSummary?.amounts ?? {});
  const oneCurrency = currencies.length === 1 ? currencies[0] : null;
  const frozenDisplay = managed && run?.display ? resolvedDisplay(run.display) : displayConfig;
  const resultDate = (value:string) => formatDate(value,frozenDisplay);
  const amount = (key: string) => oneCurrency?.[1][key] ? formatMoney(oneCurrency[1][key], frozenDisplay, { display: 'none' }) : currencies.length > 1 ? 'Multiple' : '—';
  const amountNote = oneCurrency?.[0] ?? (currencies.length > 1 ? 'Multiple currencies; see report rows' : 'No monetary activity');
  const summaryCode = run?.code ?? config.code;
  const summaryFigures = bookSummary ? summaryCode === 'DAY_BOOK' ? [
    { label: 'Posted entries', value: bookSummary.entry_count, note: 'Current period journal lines' },
    { label: 'Total debit', value: amount('debit'), note: amountNote },
    { label: 'Total credit', value: amount('credit'), note: amountNote },
  ] : summaryCode === 'CASH_BOOK' ? [
    { label: 'Cash entries', value: bookSummary.entry_count, note: 'Posted movements' },
    { label: 'Receipts', value: amount('debit'), note: amountNote },
    { label: 'Payments', value: amount('credit'), note: amountNote },
    { label: 'Closing cash', value: amount('closing'), note: amountNote },
  ] : summaryCode === 'BANK_BOOK' ? [
    { label: 'Bank entries', value: bookSummary.entry_count, note: 'Posted movements' },
    { label: 'Money in', value: amount('debit'), note: amountNote },
    { label: 'Money out', value: amount('credit'), note: amountNote },
    { label: 'Closing book balance', value: amount('closing'), note: amountNote },
  ] : ['ACCOUNT_LEDGER', 'PARTY_LEDGER'].includes(summaryCode) ? [
    { label: 'Ledger entries', value: bookSummary.entry_count, note: 'Posted movements' },
    { label: 'Total debit', value: amount('debit'), note: amountNote },
    { label: 'Total credit', value: amount('credit'), note: amountNote },
    { label: 'Closing balance', value: amount('closing'), note: amountNote },
  ] : ['SALES_REGISTER', 'PURCHASE_REGISTER'].includes(summaryCode) ? [
    { label: config.code === 'SALES_REGISTER' ? 'Sales documents' : 'Purchase documents', value: bookSummary.entry_count, note: (bookSummary.reduction_count ?? 0) + ' reductions' },
    { label: 'Net commercial', value: amount('commercial_total'), note: amountNote },
    { label: 'Net tax', value: amount('tax_total'), note: amountNote },
    { label: 'Net payable', value: amount('payable'), note: amountNote },
  ] : ['PAYMENT_REGISTER', 'RECEIPT_REGISTER'].includes(summaryCode) ? [
    { label: config.code === 'PAYMENT_REGISTER' ? 'Payments' : 'Receipts', value: bookSummary.voucher_count ?? 0, note: 'Posted vouchers, including reversals' },
    { label: 'Net amount', value: amount('amount'), note: amountNote },
    { label: 'Tender lines', value: bookSummary.entry_count, note: 'Cash, bank and instrument allocations' },
    { label: 'Instrument references', value: bookSummary.instrument_count ?? 0, note: 'Cheque or electronic references' },
  ] : [
    { label: 'Stock movements', value: bookSummary.entry_count, note: 'Opening rows excluded' },
    { label: 'Inward', value: format.quantity(bookSummary.quantities?.inward), note: bookSummary.unit ?? 'Selected item unit' },
    { label: 'Outward', value: format.quantity(bookSummary.quantities?.outward), note: bookSummary.unit ?? 'Selected item unit' },
    { label: 'Closing quantity', value: format.quantity(bookSummary.quantities?.closing), note: bookSummary.unit ?? 'Selected item unit' },
  ] : [];
  function parameterField([key, raw]: [string, ReportParameter]) {
    const item = parameterType(raw), label = (stock&&key==='search'&&inventoryReport?inventoryWorkspaces[inventoryReport].searchLabel:undefined)??(finance?(key==='date_to'&&properties.date_from?'To date':financeLabels[key]):analytics?analyticsLabels[key]:tax?(config.code==='INVOICE_CREDIT_REGISTER'&&key==='date_to'?'As of':taxParameterLabels[key]):stock?inventoryParameterLabels[key]:undefined)??bookParameterLabel(book, key, raw.title), value = filters[key] ?? '';
    if (key === 'currency' && properties.basis && filters.basis !== 'TRANSACTION') return null;
    const change = (next: string) => { if (enhanced) setSelectedSaved(''); setFilters(previous => ({ ...previous, [key]: key === 'currency' ? next.toUpperCase() : next, ...(key === 'item_id' && properties.lot_id ? { lot_id: '' } : {}),...(finance&&key==='account_id'&&properties.session_id?{session_id:''}:{}) })); };
    if(finance&&key==='invoice_id')return <FinanceInvoiceReference key={key} company={company} value={value} from={filters.date_basis==='DOCUMENT'?undefined:filters.date_from} to={filters.date_basis==='DOCUMENT'?undefined:filters.date_to} disabled={busy} onChange={change} onReady={ready=>setReferenceReady(previous=>({...previous,invoice_id:ready?value:null}))}/>;
    if(finance&&key==='session_id')return <FinanceSessionReference key={key} company={company} account={filters.account_id??''} value={value} disabled={busy} onChange={change} onScope={session=>setFilters(previous=>({...previous,date_from:session.period_from,date_to:session.period_to,currency:session.currency}))} onReady={ready=>setReferenceReady(previous=>({...previous,session_id:ready?value:null}))}/>;
    const source = referenceSources[key];
    if(stock&&key==='as_of') {
      const dates=stockSources.map(item=>item.coverage.as_of).sort();
      return <TextField key={key} label={label} type="date" value={value} required disabled={busy||!stockSources.length} min={dates[0]} max={dates.at(-1)} error={stockDateUnavailable?'No verified snapshot for this date. Load snapshot dates to find earlier reports.':undefined} onChange={event=>{const date=event.target.value;const selected=stockSources.find(item=>item.coverage.as_of===date);if(selected){setGeneration(selected.id);setInventoryCoverage(selected.coverage);}change(date);}} />;
    }
    if (source) return <ReportReference key={key} company={company} code={config.code} source={source} generation={stock||config.code==='PRODUCT_PROFIT'?generation:undefined} item={key === 'lot_id' ? filters.item_id : undefined} label={isDimensionProfit(config.code)?({group_id:'Product group',item_id:'Product',party_id:'Buyer'} as Record<string,string>)[key]??label:label} value={value} disabled={busy||(stock||config.code==='PRODUCT_PROFIT')&&!generation} required={required.includes(key)} onChange={change} onStateChange={ready => setReferenceReady(previous => ({ ...previous, [key]: ready ? value : null }))} />;
    if (item.type === 'boolean') return <Checkbox key={key} checked={value === 'true'} disabled={busy} onChange={event => change(String(event.target.checked))}>{label}</Checkbox>;
    if (item.enum) return <Select key={key} label={label} value={value} disabled={busy} options={[...(!required.includes(key) ? [{ value: '', label: 'All' }] : []), ...item.enum.map(option => ({ value: option, label: key==='quantity_basis'?(option==='ELIGIBLE'?'Eligible stock (before reservations)':'Available stock (after reservations)'):tax&&key==='date_basis'?({POSTING:'Posting date',DOCUMENT:'Document date',TAX_POINT:'Recorded tax point'} as Record<string,string>)[option]??option:option.replaceAll('_', ' ').toLowerCase() }))]} onChange={change} />;
    return <TextField key={key} label={label} value={value} type={item.format === 'date' ? 'date' : item.type === 'integer' ? 'number' : 'text'} required={required.includes(key)} pattern={item.pattern} min={key==='date_from'?(stock?inventoryCoverage?.history_start:tax||analytics&&!['PROFIT_MARGIN_ANALYSIS','EXPENSE_PROFIT_LEAKAGE'].includes(config.code)?sourceStart??undefined:item.minimum):item.minimum} max={key==='date_from'?(stock?filters.as_of:tax||analytics?filters.date_to:item.maximum):item.maximum} disabled={busy||finance&&!!filters.session_id&&['date_from','date_to','currency'].includes(key)} onChange={event => change(event.target.value)} />;
  }
  function resetAdvanced() {
    if (enhanced) setSelectedSaved('');
    setFilters(previous => ({ ...previous, ...Object.fromEntries(advancedEntries.map(([key, raw]) => [key, parameterText(raw.default)])) }));
    setReferenceReady(previous => ({ ...previous, ...Object.fromEntries(advancedEntries.map(([key]) => [key, null])) }));
  }

  async function queryRows(clear=false){
    const root=queryRoot??run;if(!root||busy)return;
    if(!clear&&search.trim()&&search.trim().length<2){setMessage('Enter at least two characters to search.');return;}
    setBusy(true);setOperation('run');setMessage('');controller.current?.abort();const abort=new AbortController();controller.current=abort;
    try{
      if(clear){await selectRun(root,abort.signal);setQueryRoot(null);setSearch('');setSort('ordinal');setQueryField('');setQueryValue('');return;}
      const selected=await command<Job>('/report-runs/'+root.id+'/queries',{q:search.trim()||null,sort,filters:queryField&&queryValue?{[queryField]:queryValue}:{}},abort.signal);
      setQueryRoot(root);await selectRun(selected,abort.signal);
    }catch(error){if(!abort.signal.aborted)failure(error,'Unable to search this report.');}
    finally{if(!abort.signal.aborted){setBusy(false);setCandidate(null);}}
  }

  async function loadHistory(cursor: string | null = null) {
    setHistoryOpen(true); if (busy) return;
    setBusy(true);setOperation('load');setMessage('');
    const abort=new AbortController();controller.current?.abort();controller.current=abort;
    try {
      const result=await request<Schemas['JobPage']>('reports','GET',base+'/report-runs?code='+config.code+'&limit=20'+(cursor?'&cursor='+encodeURIComponent(cursor):''),undefined,undefined,abort.signal);
      if(result.items.some(item=>item.code!==config.code))throw new Error(config.title+' history could not be verified.');
      setHistory(previous=>cursor?[...previous,...result.items]:result.items);setHistoryCursor(result.page.next_cursor);
    } catch(error){if(!abort.signal.aborted)failure(error,config.title+' history is unavailable.');}
    finally{if(!abort.signal.aborted)setBusy(false);}
  }

  async function openHistory(identity:string,allowPending=false) {
    if(busy)return;setBusy(true);setOperation('run');setMessage('');
    const abort=new AbortController();controller.current?.abort();controller.current=abort;
    try{
      const job=await request<Job>('reports','GET',base+'/report-runs/'+identity,undefined,undefined,abort.signal);
      if(job.id!==identity||job.kind!=='RUN'||job.code!==config.code||(job.status!=='COMPLETE'&&!(allowPending&&pending(job))))throw new Error('Choose a completed '+config.title+'.');
      setQueryRoot(null);setSearch('');setSort('ordinal');setQueryField('');setQueryValue('');
      const info=await snapshotInfo(base,job.generation_id,abort.signal,stock);
      if(stock&&!info.inventory)throw new Error('The historical inventory snapshot is unavailable.');
      setGeneration(job.generation_id);setInventoryCoverage(info.inventory??null);setSourceStart(info.start);setVerifiedAt(info.verifiedAt??null);
      if(stock&&info.inventory)setStockSources(previous=>[{id:job.generation_id,coverage:info.inventory!},...previous.filter(item=>item.id!==job.generation_id)]);
      const restored=Object.fromEntries(Object.entries(job.parameters).map(([key,value])=>[key,parameterText(value)]));
      setFilters(restored);setActiveFilters(restored);await selectRun(job,abort.signal);setHistoryOpen(false);if(finance)setFinanceFilters(false);
    }catch(error){if(!abort.signal.aborted)failure(error,'This '+config.title+' is unavailable.');}
    finally{if(!abort.signal.aborted)setBusy(false);}
  }

  async function loadStockDates() {
    if(busy)return;setBusy(true);setOperation('load');setMessage('');
    const abort=new AbortController();controller.current?.abort();controller.current=abort;
    try{
      const sources = (await readySnapshots(base, abort.signal, true, 20)).flatMap(source => source.info.inventory ? [{id:source.id,coverage:source.info.inventory}] : []);
      setStockSources(previous=>[...sources,...previous.filter(item=>!sources.some(source=>source.id===item.id))]);
      if(!sources.length)setMessage('No complete historical inventory snapshots are available. Refresh stock data to retain today’s snapshot.');
    }catch(error){if(!abort.signal.aborted)setMessage(error instanceof Error?error.message:'Historical inventory snapshots are unavailable.');}
    finally{if(!abort.signal.aborted)setBusy(false);}
  }

  const analyticsSummary=(run?.result?.evidence as {analytics?:AnalyticsSummary}|undefined)?.analytics;
  const inventorySummary=(run?.code==='STOCK_SUMMARY' ? run.result?.evidence as {stock_summary?:{item_count:number;row_count:number;currency:string;owned_value:string|null;quantities:{unit:string;owner:string;custody:string;opening:string;inward:string;outward:string;quantity:string;eligible:string;available:string|null}[];unavailable_availability_rows:number;unavailable_value_rows:number}} : undefined)?.stock_summary;
  const inventoryMetrics=(stock ? run?.result?.evidence as {inventory_metrics?:{code:string;[key:string]:unknown;item_count:number;row_count:number;entry_count?:number;location_count?:number;currency:string;owned_value:string|null;quantities:Record<string,string|null>[]}} : undefined)?.inventory_metrics;
  const taxSummary=(tax?run?.result?.evidence as {tax_summary?:TaxSummary}|null:undefined)?.tax_summary;
  const quantitySummary=inventorySummary??inventoryMetrics;
  const quantityKeys=inventorySummary?['opening','inward','outward','quantity','eligible','available']:['opening','inward','outward','quantity','eligible','available'].filter(key=>key in (inventoryMetrics?.quantities[0]??{}));
  const shownCoverage=(run?.result?.evidence as {inventory_coverage?:Schemas['StockReferencePage']['coverage']}|undefined)?.inventory_coverage??inventoryCoverage;
  const stockFigures=inventorySummary?[
    {label:'Stock items',value:inventorySummary.item_count,note:'Distinct items in the full selection'},
    {label:'Owned stock value',value:inventorySummary.owned_value===null?'Unavailable':format.money(inventorySummary.owned_value,{display:'none'}),note:inventorySummary.currency+' · Recorded carrying value'},
    {label:'Stock rows',value:inventorySummary.row_count,note:'Items by ownership and custody'},
    {label:'Availability',value:inventorySummary.unavailable_availability_rows?'Unavailable':'Verified',note:inventorySummary.unavailable_availability_rows?'Reservation coverage is incomplete':'Eligible stock less reservations'},
  ]:inventoryMetrics?(inventorySummaryFields[config.code as InventoryReportCode]??[]).map(([key,label,note])=>{
    const value=inventoryMetrics[key];return {label,value:value===null||value===undefined?'Unavailable':key==='owned_value'?format.money(String(value),{display:'none'}):key==='quantity_basis'?(value==='ELIGIBLE'?'Eligible stock':'Available stock'):String(value),note:key==='owned_value'?inventoryMetrics.currency+' · '+note:note};
  }):[];

  if(denied)return <p role="alert">Your report access is unavailable. Reload after checking permissions.</p>;
  return <div className={"janso-page janso-day-book janso-native-book"+(managed?" janso-finance":"")}>
    {finance&&trialBalanceRun&&<a className="janso-link" href={'/reports/workspace?'+new URLSearchParams({report:'TRIAL_BALANCE',run:trialBalanceRun})}>Back to Trial Balance</a>}
    <PageNavigation back={finance&&!control?{href:'/reports/finance',label:'Finance reports'}:analytics||control?{href:'/reports/analytics',label:'Analytics'}:tax?{href:'/reports/tax',label:'Tax reports'}:stock?{href:'/reports/inventory',label:'Inventory reports'}:undefined} breadcrumbs={finance&&!control?[{label:'Reports',href:'/reports'},{label:'Finance',href:'/reports/finance'},{label:config.title}]:analytics||control?[{label:'Reports',href:'/reports'},{label:'Analytics',href:'/reports/analytics'},{label:config.title}]:tax?[{label:'Reports',href:'/reports'},{label:'Tax',href:'/reports/tax'},{label:config.title}]:stock?[{label:'Reports',href:'/reports'},{label:'Inventory',href:'/reports/inventory'},{label:config.title}]:[{ label: 'Books', href: '/books' }, { label: config.title }]} />
    <PageHeader overline={companyName + (year ? ' · ' + year.code : '')} title={config.title} lede={managed?undefined:config.lede} actions={<>
      {finance&&<Button variant="ghost" aria-expanded={financeFilters} onClick={()=>setFinanceFilters(current=>!current)}>Filters</Button>}
      {enhanced && <Button variant="ghost" disabled={busy || !definition?.run_enabled} onClick={() => void refreshLatest()}>Refresh</Button>}
      {enhanced && permissions.includes('report.definition.manage') && <Button variant="ghost" disabled={busy} onClick={() => void refreshSource()}>{finance||analytics?'Refresh accounting data':tax?'Refresh tax data':'Refresh stock data'}</Button>}
      {canExport && <Menu label={'Export ' + config.title} triggerLabel="Export" disabled={busy || dirty} items={exportItems} onSelect={value => void exportReport(value as ReportExportFormat)} />}
      {canExport && <Button variant="ghost" title={printReason} disabled={busy || dirty || !!printUnavailable} onClick={() => void exportReport('PDF', undefined, 'SINGLE')}>Print / PDF</Button>}
    </>} />

    {managed&&<section className="janso-finance-status" aria-label={config.title+' activity'}>
      {progress&&<PreparationProgress label="Report progress" title={candidate?.status==='QUEUED'?'Report queued':candidate?.status==='RUNNING'?'Calculating report':progress} detail={operation==='source'?'Preparing accounting data automatically.':'Completed results remain visible until this finishes.'} action={pending(candidate)&&<Button variant="ghost" className="janso-profit-stop" onClick={()=>void stopFinance()} aria-label="Stop report"><svg aria-hidden="true" width="12" height="12" viewBox="0 0 12 12"><rect width="12" height="12" rx="2" fill="currentColor"/></svg> Stop</Button>}/>}
      {canExport&&exportJob?.status==='COMPLETE'&&<div className="janso-profit-export" role="status"><strong>{String(exportJob.parameters?.format??exportFormat)} ready</strong><a className="janso-btn janso-btn--primary" download href={reportDownloadHref(company,exportJob.id)}>Download report</a>{canPreviewReportExport(exportJob)&&<a target="_blank" rel="noopener noreferrer" href={reportDownloadHref(company,exportJob.id,true)}>Print preview</a>}</div>}
    </section>}
    {finance&&definition&&definition.definition.views.length>1&&<SegmentedControl label={config.title+' view'} value={view} disabled={busy} options={definition.definition.views.map(item=>({value:item.key,label:item.title}))} onChange={next=>{setView(next);pendingTaxColumns.current=defaultColumns(definition.definition.views.find(item=>item.key===next)?.columns??[],config.code);void runReport(filters,next);}}/>}
    {finance&&run&&config.code!=='SOURCE_RECONCILIATION'&&<p className="janso-day-book__muted">{run.parameters.date_from&&!['BANK_RECONCILIATION','INVOICE_SETTLEMENT_REGISTER'].includes(run.code)?resultDate(String(run.parameters.date_from))+' to ':'As of '}{resultDate(String(run.parameters.date_to??''))}{run.parameters.comparative_to?' / Comparison: '+(run.parameters.comparative_from&&!['BANK_RECONCILIATION','INVOICE_SETTLEMENT_REGISTER'].includes(run.code)?resultDate(String(run.parameters.comparative_from))+' to ':'As of ')+resultDate(String(run.parameters.comparative_to)):''} / {run.parameters.basis==='TRANSACTION'?'Transaction currency '+String(run.parameters.currency):['SALES_REGISTER','PURCHASE_REGISTER','INVOICE_COMPONENT_REGISTER','INVOICE_SETTLEMENT_REGISTER'].includes(run.code)?'Document currencies':'Company currency'}{verifiedAt&&run.generation_id===generation?' / Snapshot verified '+format.dateTime(verifiedAt):''}</p>}
    {analytics&&<details className="janso-finance-scope"><summary>Business analytics / About this report{verifiedAt?' / Verified '+format.dateTime(verifiedAt):''}</summary><p>{config.lede}</p><p>{sourceStart?'Detailed history starts '+format.date(sourceStart)+'. ':''}New calculations refresh a known snapshot older than five minutes when permitted. Retained results stay frozen.</p></details>}
    {controlReport&&<details className="janso-finance-scope"><summary>{config.overline} / About this report</summary><p>{controlWorkspaces[controlReport].note}</p><p>{verifiedAt?'Snapshot verified '+format.dateTime(verifiedAt):'Snapshot verification time unavailable.'}</p></details>}
    {financeReport&&<details className="janso-finance-scope"><summary>{config.overline}{sourceStart?" / History from "+format.date(sourceStart):""} / About this report</summary><p>{financeWorkspaces[financeReport].note}</p><p>{verifiedAt?"Snapshot verified "+format.dateTime(verifiedAt)+". New reports refresh accounting data after five minutes when permitted.":"Snapshot age is unavailable. Use Refresh accounting data to verify recent activity."}</p><p>Balances come from a verified accounting snapshot. Earlier activity requires a source covering that period.</p></details>}
    <div className="janso-day-book__scope-row" hidden={managed}><div><strong>{config.overline}</strong><span className="janso-day-book__muted"> · Frozen verified snapshot{stock&&shownCoverage?' · As of '+format.date(shownCoverage.as_of):''}</span></div>{!enhanced && <div className="janso-day-book__freshness"><Button variant="ghost" disabled={busy || !definition?.run_enabled} onClick={() => void refreshLatest()}>Refresh</Button>{permissions.includes('report.definition.manage') && <Button variant="ghost" disabled={busy} onClick={() => void refreshSource()}>Update accounting data</Button>}</div>}</div>
    {stock&&shownCoverage?<p className="janso-day-book__muted">{['STOCK_SUMMARY','ITEM_LEDGER','LOCATION_STOCK','STOCK_MOVEMENT','STOCK_GROUP_SUMMARY'].includes(config.code)?<>Opening and movements cover {format.date(['ITEM_LEDGER','STOCK_MOVEMENT'].includes(config.code)?activeFilters?.date_from??shownCoverage.history_start:shownCoverage.history_start)} to {format.date(shownCoverage.as_of)}</>:<>Balances use the verified stock snapshot dated {format.date(shownCoverage.as_of)}</>}. {shownCoverage.captured_at?'Stock data captured '+format.dateTime(shownCoverage.captured_at)+'. ':''}Quantities use each item's base unit. Owned value uses recorded costs.</p>:!managed&&sourceStart && <p className="janso-day-book__muted">This snapshot covers activity from {format.date(sourceStart)}. Earlier history requires a snapshot covering that period.</p>}

    <section className="janso-day-book__surface" aria-label="Filters and saved views" hidden={finance&&!financeFilters}>
      <form className="janso-day-book__filters" onSubmit={event => { event.preventDefault(); void runReport(); }} aria-label={config.title + ' filters'}>
        <div className="janso-day-book__filter-grid">
          {controlReport==='BALANCE_CONTINUITY'&&!!years?.length&&<Select label="Financial year to review" value={years.find(item=>item.startDate===filters.date_from&&item.endDate===filters.date_to)?.id??''} disabled={busy} options={[{value:'',label:'Choose a complete financial year'},...years.map(item=>({value:item.id,label:item.code+' · '+format.date(item.startDate)+' – '+format.date(item.endDate)}))]} onChange={value=>{const selected=years.find(item=>item.id===value);if(selected)setFilters(previous=>({...previous,date_from:selected.startDate,date_to:selected.endDate}));}}/>}
          {primaryEntries.map(parameterField)}
          {!finance && definition && definition.definition.views.length > 1 && <Select label={enhanced?'Report view':'Book view'} value={view} disabled={busy} options={definition.definition.views.map(item => ({ value: item.key, label: item.title }))} onChange={next => { if (enhanced) setSelectedSaved(''); setView(next); const nextColumns = defaultColumns(definition.definition.views.find(item => item.key === next)?.columns ?? [], config.code); if (tax||managed) pendingTaxColumns.current = nextColumns; else setVisible(nextColumns); }} />}
        </div>
        <div className="janso-day-book__search-row"><span className="janso-day-book__muted">{config.focus}</span><IconButton label="Saved views" icon={<BookIcon size={18} />} disabled={busy} aria-expanded={viewsOpen} onClick={() => { setAdvanced(false); setViewsOpen(true); }} />{advancedEntries.length > 0 && <Button type="button" variant="ghost" disabled={busy} onClick={() => { setViewsOpen(false); setAdvanced(true); }}>More filters{advancedCount ? ' · ' + advancedCount : ''}</Button>}<Button type="submit" disabled={busy || taxReferencePending || stockSourceUnavailable || !!coverageHint || stockDateUnavailable || !generation || !definition?.run_enabled}>Apply</Button></div>
      </form>
      {preparationHint && <p className="janso-day-book__muted">{preparationHint}</p>}
    </section>
    <Drawer open={advanced} title={config.title + ' filters'} onClose={() => setAdvanced(false)} footer={<><Button variant="ghost" disabled={busy} onClick={resetAdvanced}>Reset advanced</Button><Button disabled={busy || taxReferencePending || stockSourceUnavailable || !!coverageHint || stockDateUnavailable || !generation || !definition?.run_enabled} onClick={() => { setAdvanced(false); void runReport(); }}>Apply filters</Button></>}><div className="janso-day-book__drawer-fields">{advancedEntries.map(parameterField)}</div></Drawer>
    <Drawer open={viewsOpen} title="Saved views" onClose={() => setViewsOpen(false)} footer={<Button variant="ghost" onClick={() => setViewsOpen(false)}>Done</Button>}><div className="janso-day-book__drawer-fields"><Select label="Choose saved view" value={selectedSaved} options={[{ value: '', label: 'Choose a saved view…' }, ...saved.map(item => ({ value: item.id, label: item.name }))]} onChange={chooseView} disabled={busy || !saved.length} /><TextField label="New view name" value={saveName} maxLength={80} onChange={event => setSaveName(event.target.value)} disabled={busy} /><Button disabled={busy || !saveName.trim()} onClick={saveView}>Save current view</Button><Button variant="ghost" disabled={busy || !selectedSaved} onClick={deleteView}>Delete selected view</Button>{!saved.length && <p className="janso-day-book__muted">Save the current filters to make them available here.</p>}</div></Drawer>
    {enhanced&&<Drawer open={historyOpen} title={config.title+' history'} onClose={()=>setHistoryOpen(false)} footer={<Button variant="ghost" onClick={()=>setHistoryOpen(false)}>Done</Button>}><div className="janso-day-book__drawer-fields">{history.map(item=><Button key={item.id} variant="ghost" disabled={busy||item.status!=='COMPLETE'} onClick={()=>void openHistory(item.id)}>{format.dateTime(item.created_at)} · {item.status==='COMPLETE'?'Completed':item.status.toLowerCase()}</Button>)}{!history.length&&!busy&&<p>No previous {config.title} reports.</p>}{historyCursor&&<Button disabled={busy} onClick={()=>void loadHistory(historyCursor)}>Older reports</Button>}</div></Drawer>}

    {!managed&&progress && <div className="janso-day-book__progress" role="status" aria-label={config.title + ' progress'} aria-atomic="true"><span className="janso-spinner" aria-hidden="true" /><div><strong>{progress}</strong><span>{operation === 'export' ? 'Your report remains available while the file is prepared.' : 'Current completed results remain visible while this finishes.'}</span></div></div>}
    {message && <Notice tone={message.includes('requested') ? 'success' : ((operation === 'export' && retryExport.current) || (operation === 'load' && retryLoad.current)) ? 'danger' : undefined}>{message}{operation === 'export' && retryExport.current && <Button variant="ghost" disabled={busy} onClick={() => retryExport.current?.()}>Retry export</Button>}{operation === 'load' && retryLoad.current && <Button variant="ghost" disabled={busy} onClick={() => retryLoad.current?.()}>Retry loading book</Button>}</Notice>}
    {stock&&config.code==='STOCK_REORDER'&&filters.quantity_basis==='ELIGIBLE'&&<Notice>Eligible stock excludes held, expired or unusable stock. Reservations are not deducted; review commitments before ordering.</Notice>}
    {sourceHint && !busy && <Notice>{sourceHint}</Notice>}
    {stock && ['STOCK_SUMMARY', 'LOCATION_STOCK'].includes(config.code) && inventoryCoverage?.reservations_complete === false && <Notice>Sale eligibility includes warehouse and product operation rules. Reserved and available stock are unavailable until the stock owner supplies verified reservation evidence; a dash does not mean zero.</Notice>}
    {definition && !generation && !busy && <Notice>There is no prepared {stock?'inventory ':tax?'tax ':finance||analytics?'accounting ':''}snapshot. {permissions.includes('report.definition.manage') ? finance||analytics?'Select Refresh accounting data to prepare one.':stock?'Select Refresh stock data to prepare one.':tax?'Select Refresh tax data to prepare one.':'Select Update accounting data to request one.' : 'Ask an administrator to prepare report data.'}</Notice>}
    {dirty && !busy && <Notice>Filters changed. Select Apply to update this {enhanced?'report':'book'}.</Notice>}
    {!managed&&canExport && exportJob?.status === 'COMPLETE' && <Notice tone="success" live="polite">Your report is ready. <a className="janso-link" href={reportDownloadHref(company, exportJob.id)}>Download report</a> All matching rows from the applied filters are included.{canPreviewReportExport(exportJob) && <> · <a className="janso-link" target="_blank" rel="noopener noreferrer" href={reportDownloadHref(company, exportJob.id, true)}>Open print preview</a></>}</Notice>}

    {summaryFigures.length > 0 && <dl className="janso-day-book__summary" aria-label={config.title + ' summary'}>{summaryFigures.map(item => <div key={item.label}><dt>{item.label}</dt><dd>{item.value}</dd><span>{item.note}</span></div>)}</dl>}
    {analytics&&analyticsSummary&&<DisplayConfigProvider config={frozenDisplay}><AnalyticsInsights summary={analyticsSummary} parameters={run?.parameters}/></DisplayConfigProvider>}
    {taxSummary&&<TaxReportTotals title={config.title} summary={taxSummary}/>}
    {stockFigures.length>0&&<dl className="janso-day-book__summary" aria-label={config.title+' totals'}>{stockFigures.map(item=><div key={item.label}><dt>{item.label}</dt><dd>{item.value}</dd><span>{item.note}</span></div>)}</dl>}
    {!!quantitySummary?.quantities.length&&<section className="janso-day-book__surface" aria-label="Quantity totals by unit"><div className="janso-day-book__table-scroll" tabIndex={0}><table className="janso-day-book__table"><caption>Full selection quantities by base unit, ownership and custody</caption><thead><tr><th scope="col">Unit</th><th scope="col">Ownership</th><th scope="col">Custody</th>{quantityKeys.map(key=><th key={key} scope="col">{key==='quantity'?'Closing':key[0].toUpperCase()+key.slice(1)}</th>)}</tr></thead><tbody>{quantitySummary.quantities.map(item=><tr key={[item.unit,item.owner,item.custody].join(':')}><th scope="row">{item.unit}</th><td>{item.owner==='OWN'?'Company owned':'Third party'}</td><td>{item.custody==='LOCAL'?'In warehouse':item.custody==='TRANSIT'?'In transit':'External custody'}</td>{quantityKeys.map(key=><td key={key} className="janso-day-book__amount">{(item as Record<string,string|null>)[key]==null?'Unavailable':format.quantity((item as Record<string,string|null>)[key])}</td>)}</tr>)}</tbody></table></div></section>}

    {inventoryMetrics?.code==='STOCK_AGEING'&&Array.isArray(inventoryMetrics.age_buckets)&&inventoryMetrics.age_buckets.length>0&&<section className="janso-day-book__surface" aria-label="Stock ageing by band"><div className="janso-day-book__table-scroll" tabIndex={0}><table className="janso-day-book__table"><caption>Remaining quantities by age band; different units and ownership stay separate</caption><thead><tr><th scope="col">Unit</th><th scope="col">Ownership</th><th scope="col">Custody</th><th scope="col">Age band (days)</th><th scope="col">Quantity</th></tr></thead><tbody>{(inventoryMetrics.age_buckets as {unit:string;owner:string;custody:string;band:string;quantity:string}[]).map(row=><tr key={[row.unit,row.owner,row.custody,row.band].join(':')}><th scope="row">{row.unit}</th><td>{row.owner==='OWN'?'Company owned':'Third party'}</td><td>{row.custody==='LOCAL'?'In warehouse':row.custody==='TRANSIT'?'In transit':'External custody'}</td><td>{row.band==='UNKNOWN'?'Unknown age':row.band}</td><td className="janso-day-book__amount">{format.quantity(row.quantity)}</td></tr>)}</tbody></table></div></section>}

    {canExport && run?.status === 'COMPLETE' && showPackageDelivery && (definition?.package_limits?.max_parts ?? 0) > 1 && <div className="janso-day-book__scope-row"><Select label="PDF delivery" value={delivery} disabled={busy || dirty} options={[{ value: 'SINGLE', label: 'Single printable PDF' }, { value: 'PACKAGE', label: 'PDF parts (ZIP)' }]} onChange={value => setDelivery(value as 'SINGLE' | 'PACKAGE')} /><span className="janso-day-book__muted">This result is too large for one printable PDF. Split delivery supports up to {definition?.package_limits?.max_rows?.toLocaleString('en-IN')} rows in {definition?.package_limits?.max_parts} parts. Excel and CSV remain single files.</span></div>}

    {enhanced&&<div className="janso-day-book__scope-row"><div><Button variant="ghost" disabled={busy} onClick={()=>void loadHistory()}>{config.title} history</Button>{stock&&<Button variant="ghost" disabled={busy} onClick={()=>void loadStockDates()}>Load snapshot dates</Button>}</div><span className="janso-day-book__muted">Saved views are private to your user and company.</span></div>}
    {finance&&run?.status==='COMPLETE'&&queryCapabilities?.method==='POST'&&<form className="janso-finance-query" aria-label="Search report rows" onSubmit={event=>{event.preventDefault();void queryRows();}}>
      <TextField label="Search report" hideLabel placeholder="Account or reference prefix" maxLength={200} value={search} disabled={busy} onChange={event=>setSearch(event.target.value)}/>
      <Select label="Sort rows" hideLabel value={sort} disabled={busy} onChange={setSort} options={[{value:'ordinal',label:'Original order'},...(queryCapabilities.sort_fields??[]).filter(key=>key!=='ordinal'&&!key.endsWith('_id')&&currentView?.columns.some(column=>column.key===key)).flatMap(key=>[{value:key,label:(financeLabels[key]??bookColumnLabel(key,key.replaceAll('_',' ')))+' ↑'},{value:'-'+key,label:(financeLabels[key]??bookColumnLabel(key,key.replaceAll('_',' ')))+' ↓'}])]} />
      <Select label="Filter rows by" hideLabel value={queryField} disabled={busy} onChange={value=>{setQueryField(value);setQueryValue('');}} options={[{value:'',label:'All rows'},...Object.keys(queryCapabilities.filters??{}).filter(key=>['row_kind','status','mode','direction','currency'].includes(key)).map(key=>({value:key,label:financeLabels[key]??bookColumnLabel(key,key.replaceAll('_',' '))}))]}/>
      {queryField&&<TextField label="Exact value" hint="Use the recorded code, for example PARTIAL or INR." value={queryValue} maxLength={200} disabled={busy} onChange={event=>setQueryValue(event.target.value.toUpperCase())}/>}
      <Button type="submit" disabled={busy||dirty}>Search / sort</Button>{queryRoot&&<Button type="button" variant="ghost" disabled={busy} onClick={()=>void queryRows(true)}>Clear row selection</Button>}
    </form>}
    {finance&&!!selection&&<p className="janso-day-book__muted" role="note">Selected rows from the frozen report. Running balances retain the original calculation; this selection does not recalculate totals. Exports include these selected rows.</p>}
    <section className="janso-day-book__report" aria-label={config.title + ' report'} aria-busy={loadingReport}>
      <div className="janso-day-book__report-toolbar"><div><strong>{run?.title ?? config.title}</strong><p className="janso-day-book__muted">{run ? (totalRows ?? 'Verified') + ' ' + (run.origin ? 'drill-down rows' : config.resultNoun) : 'Apply filters to prepare this book.'}</p></div><div>{run?.origin && <Button variant="ghost" disabled={busy} onClick={() => void returnToParent()}>Back to {enhanced ? parentSelections.current.get(run.origin.parent_id)?.title ?? config.title : config.title}</Button>}{currentView && <Menu label="Visible columns" triggerLabel="Columns" items={currentView.columns.map(column => ({ id: column.key, label: columnLabel(column), checked: visible[column.key] !== false }))} onSelect={key => { if (enhanced) setSelectedSaved(''); setVisible(previous => ({ ...previous, [key]: previous[key] === false })); }} />}</div></div>
      {loadingReport && !run ? <div className="janso-day-book__loading" aria-hidden="true"><span className="janso-day-book__loading-line" /><span className="janso-day-book__loading-line" /><span className="janso-day-book__loading-line" /></div> : run?.status === 'COMPLETE' && rows.length ? <div className="janso-day-book__table-scroll" tabIndex={0} role="region" aria-label={config.title + ' rows'}><table className="janso-day-book__table"><caption className="janso-visually-hidden">{config.title} verified rows</caption><thead><tr>{columns.map(column => <th scope="col" key={column.key} className={column.kind === 'MONEY' || column.kind === 'DECIMAL' ? 'janso-day-book__amount' : undefined}>{columnLabel(column)}</th>)}<th scope="col">Details</th></tr></thead><tbody>{rows.map(row => <tr key={row.ordinal} data-kind={finance?String(row.data.row_kind):undefined}>{columns.map(column => <td key={column.key} className={column.kind === 'MONEY' || column.kind === 'DECIMAL' ? 'janso-day-book__amount' : undefined}>{cell(column, row)}</td>)}<td>{row.drilldowns?.length ? enhanced ? <ReportRowActions key={run.id + ":" + row.ordinal} company={company} run={run} row={row} busy={busy} onDrilldown={openDrilldown} columns={currentView?.columns ?? []} renderCell={cell} columnLabel={columnLabel} /> : row.drilldowns.map(link => link.method === 'GET' ? <RowDetail key={link.key} company={company} run={run} row={row} link={link} /> : <Button key={link.key} variant="ghost" disabled={busy} onClick={() => void openDrilldown(link)}>{link.title}</Button>) : '—'}</td></tr>)}</tbody></table></div> : <div className="janso-day-book__empty"><span aria-hidden="true">▤</span><h2>{run ? tax ? 'No matching tax records' : stock ? 'No matching stock records' : 'No transactions found' : config.title + ' is ready to explore'}</h2><p>{run ? emptyDescription : 'Choose the period and filters, then apply them to prepare verified results.'}</p></div>}
      <footer className="janso-day-book__report-footer"><div><strong>{run ? rows.length ? page * 50 + 1 + '–' + (page * 50 + rows.length) + (totalRows !== null ? ' of ' + totalRows : '') : totalRows !== null ? '0 of ' + totalRows : 'No rows on this page' : 'Results pending'}</strong><span>Frozen results from one verified source snapshot</span></div><div><Button variant="ghost" disabled={busy || page === 0} onClick={() => void navigate(page - 1)}>Previous</Button><Button variant="ghost" disabled={busy || !nextCursor} onClick={() => void navigate(page + 1)}>Next</Button></div></footer>
    </section>
  </div>;
}

function ReportRowActions({ company, run, row, busy, onDrilldown, columns, renderCell, columnLabel }: { company: string; run: Job; row: ResultRow; busy: boolean; onDrilldown: (link: Schemas['DrilldownLink']) => Promise<void>; columns: readonly Schemas['Column'][]; renderCell: (column: Schemas['Column'], row: ResultRow) => string; columnLabel: (column: Schemas['Column']) => string }) {
  const [selected, setSelected] = useState<Schemas['DrilldownLink'] | null>(null);
  const [detail, setDetail] = useState<ResultRow | null>(null);
  const [error, setError] = useState('');
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  const close = () => { controller.current?.abort(); setSelected(null); setDetail(null); setError(''); };
  async function choose(key: string) {
    const link = row.drilldowns?.find(item => item.key === key);
    if (!link || busy) return;
    if (link.method === 'POST') { await onDrilldown(link); return; }
    controller.current?.abort(); const abort = new AbortController(); controller.current = abort;
    setSelected(link); setDetail(null); setError('');
    try { setDetail(await request<ResultRow>('reports', 'GET', '/v2/companies/' + company + '/report-runs/' + run.id + '/rows/' + row.ordinal + '?token=' + encodeURIComponent(link.token), undefined, undefined, abort.signal)); }
    catch (failure) { if (!abort.signal.aborted) setError(failure instanceof Error ? failure.message : 'Row details are unavailable.'); }
  }
  return <><Menu label={'Actions for ' + String(row.data.bill_reference ?? row.data.label ?? row.data.item_name ?? row.data.account_name ?? row.data.item_code ?? 'row ' + row.ordinal)} size="sm" disabled={busy} items={(row.drilldowns ?? []).map(link => ({id:link.key,label:link.title}))} onSelect={key => void choose(key)} /><Drawer open={selected !== null} title={selected?.title ?? 'Row details'} onClose={close}>{error ? <Notice tone="danger">{error}</Notice> : detail ? <dl className="janso-day-book__expanded">{Object.entries(detail.data).map(([key,value]) => {
    const column = columns.find(item => item.key === key) ?? (isDimensionProfit(run.code)?profitDetailColumns.find(item=>item.key===key):undefined);
    return <Fragment key={key}><dt>{column ? columnLabel(column) : bookColumnLabel(key,key.replaceAll('_',' '))}</dt><dd>{column ? renderCell(column,detail) : value === null ? '—' : typeof value === 'object' ? JSON.stringify(value) : String(value)}</dd></Fragment>;
  })}</dl> : <p role="status">Loading row details…</p>}</Drawer></>;
}

function RowDetail({ company, run, row, link }: { company: string; run: Job; row: ResultRow; link: Schemas['DrilldownLink'] }) {
  const [open, setOpen] = useState(false), [detail, setDetail] = useState<ResultRow | null>(null), [error, setError] = useState('');
  async function toggle() {
    if (open) { setOpen(false); return; }
    setOpen(true); if (detail) return;
    try { setDetail(await request<ResultRow>('reports', 'GET', '/v2/companies/' + company + '/report-runs/' + run.id + '/rows/' + row.ordinal + '?token=' + encodeURIComponent(link.token))); }
    catch (failure) { setError(failure instanceof Error ? failure.message : 'Row detail is unavailable.'); }
  }
  return <div><Button variant="ghost" aria-expanded={open} onClick={() => void toggle()}>{open ? 'Hide detail' : link.title}</Button>{open && <div className="janso-day-book__expanded">{error ? <p role="alert">{error}</p> : detail ? <dl>{Object.entries(detail.data).map(([key, value]) => <Fragment key={key}><dt>{bookColumnLabel(key, key.replaceAll('_', ' '))}</dt><dd>{value === null ? '—' : typeof value === 'object' ? JSON.stringify(value) : String(value)}</dd></Fragment>)}</dl> : <p role="status">Loading detail…</p>}</div>}</div>;
}
