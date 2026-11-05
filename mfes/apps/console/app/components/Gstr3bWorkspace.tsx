'use client';
import { useEffect, useRef, useState, useId, type ComponentProps } from 'react';
import { Button, FilterBar, Notice, PageHeader, PageNavigation, SectionHeader, Select, TableSearch, TextField as UiTextField, Menu, Drawer, ColumnPicker, useColumnPreferences, type Column } from '@janso/ui';
import type { components } from '@janso/api-client/reports';
import { productFieldRequest as request } from '../lib/product-fields';
import { reportDownloadHref, trackReportExport } from '../lib/report-exports';
import {Gstr1Tables,Gstr1TableFilter,gstr1Columns} from './Gstr1Tables';

type Schemas = components['schemas'];
type Job = Schemas['JobDetail'];
type Registration = {
    id: string;
    number: string;
    legal_name: string;
    filing_preferences: {
        id?: string;
        frequency: string;
        valid_from: string;
        valid_to: string | null;
    }[];
};
type Context = {
    calculation_version?: number;
    registrations: Registration[];
    can_configure: boolean;
    can_capture: boolean;
    can_review: boolean;
    can_prepare: boolean;
    rule_version: string;
};
type Preparation = {
    calculation_version?: number;
    registration: Registration;
    date_from: string;
    date_to: string;
    financial_year: string;
    status: string;
    nil: boolean;
    currency: string;
    form: Record<string, Record<string, string | null>>;
    row_order?: string[];
    labels: Record<string, string>;
    pos_rows: {
        recipient: string;
        place_of_supply: string;
        taxable: string;
        igst: string;
    }[];
    payment: Record<string, Record<string, string>>;
    payment_rows: Record<string, string>[];
    inward_rows: {
        nature: string;
        interstate: string;
        intrastate: string;
    }[];
    prior_liability_rows: Record<string, string>[];
    issues: {
        code: string;
        message: string;
        source_id: string;
    }[];
    reconciliation: {
        source: string;
        head: string;
        return_amount: string;
        source_amount: string;
        difference: string;
    }[];
    portal_json_reason: string;
    source_count: number;
    bridge?:Record<string,Record<string,string>>;
    bridge_labels?:Record<string,string>;
    table_counts?:Record<string,number>;
    iff_count?:number;
    document_count?:number;
    hsn_min_digits?:number|null;
};
const heads = ['taxable', 'igst', 'cgst', 'sgst', 'cess'];
const labels = ['Taxable value', 'Integrated tax', 'Central tax', 'State / UT tax', 'Cess'];
const recordColumns: Column<Schemas['ResultRow']>[] = [
    { key: 'category', header: 'Table', type: 'text', locked: true },
    { key: 'reference', header: 'Source reference', type: 'text', locked: true },
    { key: 'return_date', header: 'Return date', type: 'date' },
    { key: 'taxable', header: 'Taxable value', type: 'money' },
    ...heads.slice(1).map((key, index) => ({ key, header: labels[index + 1], type: 'money' as const, hidden: true })),
    { key: 'event_date', header: 'Source date', type: 'date', hidden: true },
    { key: 'source_id', header: 'Source ID', type: 'code', hidden: true },
];
const pending = (job: Job | null) => !!job && ['QUEUED', 'RUNNING'].includes(job.status);
function coversFilingPeriod(registration: Registration | undefined, period: string, frequency: string) {
    const match = period.match(frequency === 'QRMP' ? /^(20\d{2})-Q([1-4])$/ : /^(20\d{2})-(0[1-9]|1[0-2])$/);
    if (!registration || !match) return false;
    const year = Number(match[1]), lastMonth = Number(match[2]) * (frequency === 'QRMP' ? 3 : 1);
    const firstMonth = lastMonth - (frequency === 'QRMP' ? 2 : 0);
    const start = `${year}-${String(firstMonth).padStart(2,'0')}-01`;
    const end = new Date(Date.UTC(year,lastMonth,0)).toISOString().slice(0,10);
    return registration.filing_preferences.filter(value => value.frequency === frequency && value.valid_from <= start && (!value.valid_to || value.valid_to > end)).length === 1;
}
function TextField({ onChange, multiline, label, ...props }: Omit<ComponentProps<typeof UiTextField>, 'onChange'> & {
    onChange: (value: string) => void;
    multiline?: boolean;
}) {
    const id = useId();
    if (multiline)
        return <div className="janso-field"><label className="janso-label" htmlFor={id}>{label}</label><textarea className="janso-input" id={id} value={props.value} onChange={event => onChange(event.target.value)} rows={8}/></div>;
    return <UiTextField {...props} label={label} onChange={event => onChange(event.target.value)}/>;
}
export function Gstr3bWorkspace(props:{company:string;permissions:readonly string[]}) { return <GstReturnWorkspace {...props} report="GSTR3B"/>; }
export function GstReturnWorkspace({ company, permissions, report }: {
    report: 'GSTR3B'|'GSTR1';
    company: string;
    permissions: readonly string[];
}) {
    return <GstReturnWorkspaceContent key={company+':'+report} company={company} permissions={permissions} report={report}/>;
}
function GstReturnWorkspaceContent({ company, permissions, report }: {
    report: 'GSTR3B'|'GSTR1'; company: string; permissions: readonly string[];
}) {
    const isGstr1=report==='GSTR1', title=isGstr1?'GSTR-1':'GSTR-3B', contextPath=isGstr1?'gstr1-context':'gst-return-context', recordsPath=isGstr1?'gstr1-records':'gst-records', reviewPath=isGstr1?'gstr1-review':'gst-review', sourcePath=isGstr1?'gst-outward-records':'gst-return-records';
    const base = '/v2/companies/' + company;
    const [context, setContext] = useState<Context | null>(null), [definition, setDefinition] = useState<Schemas['DefinitionDetail'] | null>(null);
    const [registration, setRegistration] = useState(''), [period, setPeriod] = useState(''), [frequency, setFrequency] = useState('MONTHLY');
    const [history, setHistory] = useState<Schemas['JobListItem'][]>([]), [historyNext, setHistoryNext] = useState<string | null>(null), [savedRun, setSavedRun] = useState('');
    const [year, setYear] = useState(String(new Date().getFullYear())), [quarter, setQuarter] = useState('4');
    const [proofName, setProofName] = useState('');
    const [sources, setSources] = useState<Schemas['ListItem'][]>([]), [generation, setGeneration] = useState('');
    const [job, setJob] = useState<Job | null>(null), [exportJob, setExportJob] = useState<Job | null>(null);
    const [rows, setRows] = useState<Schemas['ResultRow'][]>([]), [next, setNext] = useState<string | null>(null), [search, setSearch] = useState('');
    const [category, setCategory] = useState(''), [recordView, setRecordView] = useState('STATUTORY');
    const [comparisons, setComparisons] = useState<Schemas['JobListItem'][]>([]), [comparison, setComparison] = useState('');
    const columns = useColumnPreferences(report+'-records:'+company+':'+category, isGstr1?gstr1Columns(category):recordColumns);
    const [section, setSection] = useState('3.1'), [busy, setBusy] = useState(false), [error, setError] = useState(''), [message, setMessage] = useState('');
    const [setup, setSetup] = useState(false), [effective, setEffective] = useState(''), [evidence, setEvidence] = useState('');
    const [reviewReference, setReviewReference] = useState(''), [reviewHash, setReviewHash] = useState(''), [filedDate, setFiledDate] = useState('');
    const [reviewState, setReviewState] = useState(''), [detail, setDetail] = useState<Schemas['ResultRow'] | null>(null);
    const proofVersion = useRef(0);
    const controller = useRef<AbortController | null>(null), retry = useRef<{
        payload: string;
        key: string;
    } | null>(null);
    const preparation = (job?.result?.evidence as Record<string,Preparation> | undefined)?.[isGstr1?'gstr1':'gstr3b'];
    const stalePreparation = !!preparation && (!context?.calculation_version || preparation.calculation_version !== context.calculation_version);
    const unsettledPayment = !isGstr1 && !!preparation && Object.values(preparation.payment ?? {}).some(values => ['normal_unpaid','rcm_unpaid','eco_unpaid','interest_unpaid','late_fee_unpaid'].some(key => values[key] !== undefined && !/^-?0+(?:\.0+)?$/.test(values[key])));
    const selected = context?.registrations.find(row => row.id === registration);
    const filingReady = coversFilingPeriod(selected, period, frequency);
    function resetResult() {
        proofVersion.current++;
        setJob(null); setExportJob(null); setRows([]); setNext(null); setDetail(null);
        setReviewState(''); setReviewReference(''); setReviewHash(''); setProofName('');
        setFiledDate(''); setCategory(''); setError(''); setMessage('');
    }
    function selectChanged(update: () => void) {
        resetResult(); update();
    }
    async function act(work: () => Promise<void>) { setBusy(true); setError(''); setMessage(''); try {
        await work();
    }
    catch (value) {
        setError(value instanceof Error ? value.message : 'The action could not complete.');
    }
    finally {
        setBusy(false);
    } }
    async function readProof(file?: File) {
        const version = ++proofVersion.current;
        setReviewHash(''); setProofName('');
        if (!file) return;
        await act(async () => {
            if (file.size > 10 * 1024 * 1024) throw new Error('Choose evidence up to 10 MB.');
            const digest = await crypto.subtle.digest('SHA-256', await file.arrayBuffer());
            if (proofVersion.current !== version) return;
            setReviewHash(Array.from(new Uint8Array(digest), value => value.toString(16).padStart(2, '0')).join(''));
            setProofName(file.name);
        });
    }
    async function create<T>(service: 'reports' | 'identity' | 'accounting', path: string, body: unknown): Promise<T> {
        const payload = JSON.stringify({ service, path, body });
        if (retry.current?.payload !== payload)
            retry.current = { payload, key: crypto.randomUUID() };
        const result = await request<T>(service, 'POST', path, body, retry.current.key);
        retry.current = null;
        return result;
    }
    async function load(signal?: AbortSignal) {
        const [config, catalogue, source, previous] = await Promise.all([
            request<Context>('reports', 'GET', base + '/'+contextPath, undefined, undefined, signal),
            request<Schemas['DefinitionCatalog']>('reports', 'GET', base + '/report-definitions', undefined, undefined, signal),
            request<Schemas['ResourcePage']>('reports', 'GET', base + '/report-generations?limit=50', undefined, undefined, signal),
            request<Schemas['JobPage']>('reports', 'GET', base + '/report-runs?code='+report+'&limit=20', undefined, undefined, signal)
        ]);
        if (signal?.aborted)
            return;
        setHistory(previous.items);
        if (isGstr1) {
            const compared = await request<Schemas['JobPage']>('reports', 'GET', base + '/report-runs?code=GSTR3B&limit=50', undefined, undefined, signal);
            if (!signal?.aborted) setComparisons(compared.items.filter(row => row.status === 'COMPLETE'));
        }
        setHistoryNext(previous.page.next_cursor);
        setContext(config);
        setDefinition(catalogue.items.find(row => row.definition.code === report) ?? null);
        const ready = source.items.filter(row => row.status === 'READY');
        setSources(ready);
        setGeneration(current => ready.some(row => row.id === current) ? current : ready[0]?.id ?? '');
        setRegistration(current => config.registrations.some(row => row.id === current) ? current : config.registrations[0]?.id ?? '');
    }
    async function readRows(id: string, cursor: string | null, query = search, signal?: AbortSignal) {
        const page = await request<Schemas['ResultPage']>('reports', 'GET', base + '/report-runs/' + id + '/'+recordsPath+'?limit=50&q=' + encodeURIComponent(query) + '&category=' + encodeURIComponent(category) + (isGstr1 ? '&view=' + recordView : '') + (cursor ? '&cursor=' + encodeURIComponent(cursor) : ''), undefined, undefined, signal);
        if (!signal?.aborted) {
            setRows(page.items);
            setNext(page.page.next_cursor);
        }
    }
    useEffect(() => { const abort = new AbortController(); void act(() => load(abort.signal)); return () => { abort.abort(); controller.current?.abort(); }; }, [base]);
    useEffect(() => {
        if (!pending(job))
            return;
        const abort = new AbortController();
        let timer: ReturnType<typeof setTimeout>;
        const poll = async () => {
            try {
                const value = await request<Job>('reports', 'GET', base + '/report-runs/' + job!.id, undefined, undefined, abort.signal);
                if (abort.signal.aborted)
                    return;
                setJob(value);
                if (value.status === 'COMPLETE')
                    await readRows(value.id, null);
                else if (pending(value))
                    timer = setTimeout(() => void poll(), 1500);
            }
            catch (value) {
                if (!abort.signal.aborted)
                    setError(value instanceof Error ? value.message : 'Report status could not be read.');
            }
        };
        timer = setTimeout(() => void poll(), 1500);
        return () => { abort.abort(); clearTimeout(timer); };
    }, [base, job?.id, job?.status]);
    useEffect(() => {
        if (job?.status !== 'COMPLETE')
            return;
        const abort = new AbortController();
        const timer = setTimeout(() => { void readRows(job.id, null, search, abort.signal).catch(value => { if (!abort.signal.aborted)
            setError(value instanceof Error ? value.message : 'Search could not complete.'); }); }, 300);
        return () => { abort.abort(); clearTimeout(timer); };
    }, [base, job?.id, job?.status, search, category, recordView]);
    function contributors(key: string) {
        setCategory(key); setRecordView('STATUTORY'); setSearch(''); setNext(null); setRows([]);
        setSection('Contributing records');
    }
    const groups = ['3.1', '3.1.1', '3.2', '4', '5', '5.1', '6.1', 'Reconciliation', 'Contributing records'];
    const keys = !isGstr1 && preparation ? (preparation.row_order ?? Object.keys(preparation.form).sort()).filter(key => section === '3.1' ? key.startsWith('3.1') && !key.startsWith('3.1.1') : section === '3.1.1' ? key.startsWith('3.1.1') : section === '4' ? key.startsWith('4') : section === '5' ? false : section === '5.1' ? ['INTEREST', 'LATE_FEE'].includes(key) : false) : [];
    async function readReview(id: string) {
        const value = await request<{
            items: {
                state: string;
            }[];
        }>('reports', 'GET', base + '/report-runs/' + id + '/'+reviewPath);
        setReviewState(value.items.at(-1)?.state ?? '');
    }
    async function openSaved() {
        const value = await request<Job>('reports', 'GET', base + '/report-runs/' + savedRun);
        resetResult();
        if (typeof value.parameters.registration_id === 'string')
            setRegistration(value.parameters.registration_id);
        if (typeof value.parameters.period === 'string') {
            setPeriod(value.parameters.period);
            setFrequency(value.parameters.period.includes('-Q') ? 'QRMP' : 'MONTHLY');
            if (value.parameters.period.includes('-Q')) {
                setYear(value.parameters.period.slice(0, 4));
                setQuarter(value.parameters.period.slice(-1));
            }
        }
        setComparison(typeof value.parameters.comparison_job_id === 'string' ? value.parameters.comparison_job_id : '');
        if (value.generation_id) setGeneration(value.generation_id);
        setJob(value);
        setExportJob(null);
        setDetail(null);
        setSearch('');
        if (value.status === 'COMPLETE') {
            await readReview(value.id);
        }
    }
    async function run() {
        resetResult();
        setDetail(null);
        setRows([]);
        setReviewState('');
        setExportJob(null);
        const value = await create<Job>('reports', base + '/report-runs', { code: report, generation_id: generation, parameters: { registration_id: registration, period, ...(isGstr1 && comparison ? {comparison_job_id: comparison} : {}) } });
        setJob(value);
        if (value.status === 'COMPLETE') {
            await readReview(value.id);
        }
        await load();
    }
    async function exportFile(format: 'PDF' | 'XLSX' | 'CSV') {
        if (!job)
            return;
        controller.current?.abort();
        const abort = new AbortController();
        controller.current = abort;
        const initial = await create<Job>('reports', base + '/report-runs/' + job.id + '/exports', { format, view: 'default' });
        setExportJob(initial);
        const completed = await trackReportExport(company, initial, abort.signal, setExportJob);
        if (completed.status !== 'COMPLETE')
            throw new Error('The export could not complete. Check its status and retry.');
    }
    async function review(state: 'REVIEWED' | 'EXTERNALLY_FILED') {
        if (!job)
            return;
        const body = { state, reference: reviewReference, evidence_hash: reviewHash, ...(state === 'EXTERNALLY_FILED' ? { filed_date: filedDate } : {}) };
        await create('reports', base + '/report-runs/' + job.id + '/'+reviewPath, body);
        setReviewState(state);
    }
    return <div className="janso-page">
  <PageNavigation back={{ href: '/reports/tax', label: 'tax reports' }} breadcrumbs={[{ label: 'Reports', href: '/reports' }, { label: 'Tax reports', href: '/reports/tax' }, { label: title }]}/>
  <PageHeader title={title} lede="Prepare one GSTIN’s statutory return, review its source evidence and record external filing."/>
  {error && <Notice tone="warning">{error}</Notice>}{message && <Notice>{message}</Notice>}
  {context?.can_configure&&<a className="janso-link" href={'/companies/'+company+'/gst-settings'}>Company GST settings</a>}
  {!context ? <Notice>Loading GST return configuration…</Notice> : !context.registrations.length ? <Notice>{title} requires an Indian GST registration under a supported filing regime. Configure the company’s tax registration first.</Notice> : <>
   <FilterBar>
    <Select label="GSTIN" disabled={busy || pending(job)} value={registration} onChange={value => selectChanged(() => setRegistration(value))} options={context.registrations.map(row => ({ value: row.id, label: row.number + ' — ' + row.legal_name }))}/>
    <Select label="Filing frequency" disabled={busy || pending(job)} value={frequency} onChange={value => selectChanged(() => { setFrequency(value); setPeriod(value === 'QRMP' ? year + '-Q' + quarter : ''); })} options={[{ value: 'MONTHLY', label: 'Monthly' }, { value: 'QRMP', label: 'Quarterly (QRMP)' }]}/>
    {frequency === 'MONTHLY' ? <TextField label="Return month" disabled={busy || pending(job)} type="month" value={period} onChange={value => selectChanged(() => setPeriod(value))}/> : <>
     <Select label="Return year" disabled={busy || pending(job)} value={year} onChange={value => selectChanged(() => { setYear(value); setPeriod(value + '-Q' + quarter); })} options={Array.from({ length: Math.max(2, new Date().getFullYear() - 2024) }, (_, i) => ({ value: String(2025 + i), label: String(2025 + i) }))}/>
     <Select label="Return quarter" disabled={busy || pending(job)} value={quarter} onChange={value => selectChanged(() => { setQuarter(value); setPeriod(year + '-Q' + value); })} options={[{ value: '1', label: 'January – March' }, { value: '2', label: 'April – June' }, { value: '3', label: 'July – September' }, { value: '4', label: 'October – December' }]}/>
    </>}
    <Select label="Verified source" disabled={busy || pending(job)} value={generation} onChange={value => selectChanged(() => setGeneration(value))} options={[{ value: '', label: 'Choose verified source' }, ...sources.map(row => ({ value: row.id, label: row.id }))]}/>
    {isGstr1 && <Select label="Optional GSTR-3B comparison" disabled={busy || pending(job)} value={comparison} onChange={value => selectChanged(() => setComparison(value))} options={[{value:'',label:'No comparison'}, ...comparisons.map(row=>({value:row.id,label:'GSTR-3B · '+row.created_at.slice(0,16).replace('T',' ')+' UTC · '+row.id.slice(-8)}))]}/>}
   </FilterBar>
   {isGstr1 && comparison && <Notice>The comparison must use the same GSTIN, period, and verified source. Differences appear under Reconciliation.</Notice>}
   <div className="janso-report-actions">
    {context.can_prepare && <Button disabled={busy || pending(job) || reviewState === 'EXTERNALLY_FILED' || !definition?.run_enabled || !registration || !period || !generation || !filingReady} onClick={() => void act(run)}>Prepare {title}</Button>}
    <Button variant="ghost" disabled={busy} onClick={() => void act(() => load())}>Refresh</Button>
    {permissions.includes('report.definition.manage') && <Button variant="ghost" disabled={busy} onClick={() => void act(async () => { await create('reports', base + '/report-generations', generation ? { strategy: 'REFRESH', base_generation_id: generation } : { strategy: 'FRESH' }); setMessage('Source refresh requested. Refresh this workspace after verification completes.'); })}>Refresh GST data</Button>}
    {context.can_configure && <Button variant="ghost" onClick={() => setSetup(!setup)}>GST filing setup</Button>}
    {permissions.includes('report.export') && (['XLSX', 'CSV', 'PDF'] as const).map(format => <Button key={format} disabled={busy || job?.status !== 'COMPLETE' || !definition?.formats?.includes(format)} onClick={() => void act(() => exportFile(format))}>{format === 'PDF' ? 'Print / PDF' : format === 'XLSX' ? 'Export Excel' : 'Export CSV'}</Button>)}
   </div>
   <FilterBar><Select label="Saved preparations" value={savedRun} onChange={setSavedRun} options={[{ value: '', label: 'Choose a frozen preparation' }, ...history.map(row => ({ value: row.id, label: row.created_at.slice(0, 16).replace('T', ' ') + ' · ' + row.status }))]}/><Button variant="ghost" disabled={busy || !savedRun} onClick={() => void act(openSaved)}>Open preparation</Button><Button variant="ghost" disabled={busy || !historyNext} onClick={() => void act(async () => { const page = await request<Schemas['JobPage']>('reports', 'GET', base + '/report-runs?code='+report+'&limit=20&cursor=' + encodeURIComponent(historyNext!)); setHistory(page.items); setHistoryNext(page.page.next_cursor); setSavedRun(''); })}>Older preparations</Button></FilterBar>
   {!selected?.filing_preferences.length && <Notice tone="warning">This GSTIN needs a dated Monthly or QRMP filing preference before preparation.</Notice>}
   {period && !!selected?.filing_preferences.length && !filingReady && <Notice tone="warning">The dated filing preference must cover the complete selected return period and frequency.</Notice>}
   {setup && <section className="janso-flow" aria-label="GST filing setup"><SectionHeader title="Dated filing preference" description="Use the frequency confirmed for this GSTIN on the GST Portal. Previous preferences remain available for historical returns."/>
    <TextField label="Effective from" type="date" value={effective} onChange={setEffective}/>
    <p>To change frequency, close the current preference at the next period boundary, then save the next preference from the same date.</p>
    {selected?.filing_preferences.map(row => <div key={row.valid_from}>{row.frequency} · {row.valid_from} to {row.valid_to ?? 'ongoing'}{!row.valid_to && row.id && <Button variant="ghost" disabled={busy || !effective} onClick={() => void act(async () => { await request('identity', 'PATCH', '/v1/companies/' + company + '/gst-filing-preferences/' + row.id, { valid_to: effective }, crypto.randomUUID()); await load(); setMessage('Filing preference closed at the selected boundary. Save the new frequency from that date.'); })}>Close at effective date</Button>}</div>)}
    <Button disabled={busy || !effective || !registration} onClick={() => void act(async () => { await create('identity', '/v1/companies/' + company + '/gst-filing-preferences', { registration_id: registration, frequency, valid_from: effective }); await load(); setMessage('GST filing preference saved.'); })}>Save filing preference</Button>
   </section>}
   {pending(job) && <Notice>Preparing the frozen return…</Notice>}
   {job && !pending(job) && job.status !== 'COMPLETE' && <Notice tone="warning">Preparation {job.status.toLowerCase()}. {job.failure_code ?? 'Retry after checking source readiness.'}</Notice>}
   {exportJob && <Notice>{pending(exportJob) ? 'Preparing export…' : exportJob.status === 'COMPLETE' ? <><a className="janso-link" href={reportDownloadHref(company, exportJob.id)}>Download {exportJob.parameters.format as string}</a>{exportJob.parameters.format === 'PDF' && <> · <a className="janso-link" target="_blank" rel="noopener" href={reportDownloadHref(company, exportJob.id, true)}>Preview PDF</a></>}</> : 'Export ' + exportJob.status.toLowerCase()}</Notice>}
   {preparation && <>
    <Notice tone={preparation.issues.length ? 'warning' : undefined}>{reviewState || preparation.status} · GSTIN {preparation.registration.number} · {preparation.date_from} to {preparation.date_to} · FY {preparation.financial_year} · INR · {preparation.nil ? 'Nil return' : 'Return with activity'}</Notice>
    {preparation.issues.length > 0 && <section className="janso-flow"><SectionHeader title="Readiness and exceptions" description="Resolve these in the source records, refresh GST data and prepare a new frozen return."/><ul>{preparation.issues.slice(0, 100).map((issue, index) => <li key={index}>{issue.message}{issue.source_id && ' Source: ' + issue.source_id}</li>)}</ul></section>}
    {stalePreparation && <Notice tone="warning">This saved preparation predates the final calculation review. Prepare a current copy from its verified source before review or filing. Filed history remains an archive.</Notice>}
    {isGstr1 && <Gstr1Tables evidence={preparation} onContributors={contributors}/>}
    {!isGstr1 && <nav className="janso-report-actions" aria-label="GSTR-3B sections">{groups.map(group => <Button variant={section === group ? 'primary' : 'ghost'} key={group} aria-pressed={section === group} onClick={() => setSection(group)}>{group}</Button>)}</nav>}
    {!!keys.length && <div className="janso-gst-table-scroll"><table className="janso-gst-table"><caption>Table {section} — amounts in INR</caption><thead><tr><th scope="col">Nature of supplies</th>{labels.map(label => <th scope="col" key={label}>{label}</th>)}</tr></thead><tbody>{keys.map(key => <tr key={key}><th scope="row">{key} {preparation.labels[key]}</th>{heads.map(head => <td key={head} data-amount>{preparation.form[key][head] == null ? '—' : <button type="button" className="janso-gst-amount-link" aria-label={'Contributors for ' + key + ' ' + labels[heads.indexOf(head)]} onClick={() => contributors(key)}>{preparation.form[key][head]}</button>}</td>)}</tr>)}</tbody></table></div>}
    {!isGstr1 && section === '3.2' && <div className="janso-gst-table-scroll"><table className="janso-gst-table"><caption>Interstate supplies — advances excluded from October 2025</caption><thead><tr><th>Recipient class</th><th>Place of supply</th><th>Taxable value</th><th>Integrated tax</th></tr></thead><tbody>{preparation.pos_rows.map((row, index) => <tr key={index}><td>{row.recipient}</td><td>{row.place_of_supply}</td><td>{row.taxable}</td><td>{row.igst}</td></tr>)}</tbody></table>{!preparation.pos_rows.length && <Notice>No recorded interstate disclosures for this period.</Notice>}</div>}
    {!isGstr1 && section === '5' && <div className="janso-gst-table-scroll"><table className="janso-gst-table"><caption>Table 5 — Exempt, nil rated and non-GST inward supplies</caption><thead><tr><th>Nature of supplies</th><th>Interstate supplies</th><th>Intrastate supplies</th></tr></thead><tbody>{preparation.inward_rows.map(row => <tr key={row.nature}><th scope="row">{row.nature}</th><td>{row.interstate}</td><td>{row.intrastate}</td></tr>)}</tbody></table></div>}
    {!isGstr1 && section === '6.1' && <><Notice>Cash deposits and available ITC are separate from actual tax offsets. RCM, ECO section 9(5), interest and late fee require cash.</Notice>{['OTHER_THAN_REVERSE_CHARGE', 'REVERSE_CHARGE'].map(kind => <div className="janso-gst-table-scroll" key={kind}><table className="janso-gst-table"><caption>Table 6.1 — {kind === 'REVERSE_CHARGE' ? 'Reverse charge' : 'Other than reverse charge (including ECO)'}</caption><thead><tr>{['Tax head', 'Tax payable', 'ITC: Integrated', 'ITC: Central', 'ITC: State / UT', 'ITC: Cess', 'Paid in cash', 'Interest paid', 'Late fee paid'].map(label => <th scope="col" key={label}>{label}</th>)}</tr></thead><tbody>{preparation.payment_rows.filter(row => row.liability_kind === kind).map(row => <tr key={row.tax_head}><th scope="row">{row.tax_head}</th>{['tax_payable', 'paid_igst', 'paid_cgst', 'paid_sgst', 'paid_cess', 'paid_cash', 'interest_paid', 'late_fee_paid'].map(key => <td key={key} data-amount>{row[key]}</td>)}</tr>)}</tbody></table></div>)}<details><summary>Prior-period liability breakup</summary><div className="janso-gst-table-scroll"><table className="janso-gst-table"><thead><tr>{['Source period date', 'Reference', ...labels.slice(1)].map(label => <th key={label}>{label}</th>)}</tr></thead><tbody>{(preparation.prior_liability_rows ?? []).map((row, index) => <tr key={index}><td>{row.event_date}</td><td>{row.reference}</td>{heads.slice(1).map(head => <td key={head} data-amount>{row[head]}</td>)}</tr>)}</tbody></table></div></details><details><summary>Cash and credit ledger workings</summary><div className="janso-gst-table-scroll"><table className="janso-gst-table"><thead><tr><th>Tax head</th>{Object.keys(preparation.payment.IGST).map(key => <th key={key}>{key.replaceAll('_', ' ')}</th>)}</tr></thead><tbody>{Object.entries(preparation.payment).map(([head, values]) => <tr key={head}><th>{head}</th>{Object.values(values).map((value, index) => <td key={index}>{value}</td>)}</tr>)}</tbody></table></div></details></>}
    {section === 'Reconciliation' && <div className="janso-gst-table-scroll"><table className="janso-gst-table"><caption>{isGstr1?'Portal and GSTR-3B comparisons':'GSTR-1 and GSTR-2B source comparisons'}</caption><thead><tr>{['Source', ...(isGstr1 ? ['Category'] : []), 'Tax head', 'Return amount', 'Source amount', 'Difference'].map(label => <th key={label}>{label}</th>)}</tr></thead><tbody>{preparation.reconciliation.map((row, index) => <tr key={index}>{['source', ...(isGstr1 ? ['category'] : []), 'head', 'return_amount', 'source_amount', 'difference'].map(key => <td key={key}>{(row as unknown as Record<string,string>)[key]}</td>)}</tr>)}</tbody></table>{!preparation.reconciliation.length && <Notice>No imported comparison evidence. Completeness exceptions remain visible above.</Notice>}</div>}
    {isGstr1 && <div className="janso-report-actions"><Button variant={section==='Contributing records'?'primary':'ghost'} onClick={()=>setSection('Contributing records')}>Contributing records</Button><Button variant={section==='Reconciliation'?'primary':'ghost'} onClick={()=>setSection('Reconciliation')}>Reconciliation</Button></div>}
    {section === 'Contributing records' && <><FilterBar>{isGstr1&&<Gstr1TableFilter evidence={preparation} value={category} onChange={setCategory}/>}<TableSearch label="Search contributing records" value={search} onChange={setSearch} minLength={0}/>{isGstr1 && <Select label="Record view" value={recordView} onChange={setRecordView} options={[{value:'STATUTORY',label:'Statutory table rows'},{value:'SOURCES',label:'Source contributions'}]}/>}<ColumnPicker columns={columns.choices} hidden={columns.hidden} onToggle={columns.toggle} onReset={columns.reset}/>{category && <Button variant="ghost" onClick={() => setCategory('')}>Clear table filter ({category})</Button>}</FilterBar><Notice>Search includes all contributing records. Exports include the complete frozen preparation{isGstr1?' with its statutory tables':''}.</Notice>
     <div className="janso-gst-table-scroll"><table className="janso-gst-table"><caption>{title} records</caption><thead><tr>{columns.columns.map(column => <th key={column.key}>{column.header}</th>)}<th>Actions</th></tr></thead><tbody>{rows.map(row => <tr key={row.ordinal}>{columns.columns.map(column => <td key={column.key} data-amount={column.type === 'money' || undefined}>{String(row.data[column.key] ?? '—')}</td>)}<td><Menu label={'Actions for ' + (row.data.document_number || row.data.reference || row.ordinal)} items={[{ id: 'detail', label: 'Source and allocation details' }]} onSelect={() => setDetail(row)}/></td></tr>)}</tbody></table></div>
     <div className="janso-report-actions"><Button variant="ghost" disabled={busy} onClick={() => void act(() => readRows(job!.id, null))}>First page</Button><Button disabled={busy || !next} onClick={() => void act(() => readRows(job!.id, next))}>Next page</Button></div>
    </>}
    {detail && <Drawer open={!!detail} title="Source and allocation details" onClose={() => setDetail(null)}>{permissions.includes('voucher.read') && typeof detail.data.voucher_id === 'string' && /^[0-9a-f-]{36}$/i.test(detail.data.voucher_id) && <a className="janso-btn janso-btn--ghost" href={'/vouchers/' + detail.data.voucher_id}>Open source voucher</a>}<dl>{Object.entries(detail.data).map(([key, value]) => <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd>{typeof value === 'object' && value !== null ? JSON.stringify(value, null, 2) : String(value ?? '—')}</dd></div>)}</dl></Drawer>}
    {context.can_review && <section className="janso-flow" aria-label="Return review"><SectionHeader title="Review and external filing evidence"/>{unsettledPayment && <Notice tone="warning">GSTR-3B liabilities must be fully offset before recording external filing. Review the payment section and capture the verified offsets.</Notice>}<TextField label="Review / portal acknowledgement reference" value={reviewReference} onChange={setReviewReference}/><label className="janso-field">Review / filing evidence file<input className="janso-input" type="file" onChange={event => { void readProof(event.target.files?.[0]); }}/></label>{proofName && <p>Evidence: {proofName}. Keep the original file with the return working papers.</p>}<div className="janso-report-actions"><Button disabled={busy || stalePreparation || !!reviewState || !!preparation.issues.length || !reviewReference || !/^[a-f0-9]{64}$/.test(reviewHash)} onClick={() => void act(() => review('REVIEWED'))}>Mark reviewed</Button><TextField label="External filing date" type="date" value={filedDate} onChange={setFiledDate}/><Button disabled={busy || stalePreparation || unsettledPayment || reviewState !== 'REVIEWED' || !filedDate || !reviewReference || !/^[a-f0-9]{64}$/.test(reviewHash)} onClick={() => void act(() => review('EXTERNALLY_FILED'))}>Record external filing</Button></div></section>}
    <Notice>{preparation.portal_json_reason}</Notice>
   </>}
   {context.can_capture && reviewState!=='EXTERNALLY_FILED' && <section className="janso-flow" aria-label="GST source evidence"><SectionHeader title="Statutory source evidence" description="Import reviewed statutory document evidence and source references. Native supply amounts are checked against committed Accounting records."/><label className="janso-field">Import reviewed allocations<input className="janso-input" type="file" accept=".json,application/json" onChange={event => { const file = event.target.files?.[0]; if (!file)
            return; void act(async () => { if (file.size > 1024 * 1024)
            throw new Error('Use a JSON evidence batch up to 1 MB.'); const text = await file.text(); const data = JSON.parse(text); if (!Array.isArray(data.records) || data.records.length < 1 || data.records.length > 200)
            throw new Error('Import 1–200 reviewed records per batch.'); setEvidence(JSON.stringify(data, null, 2)); setMessage(file.name + ' loaded: ' + data.records.length + ' records. Review the allocation preview before capture.'); }); }}/></label><details><summary>Allocation preview / advanced entry</summary><TextField label="Evidence batch JSON" multiline value={evidence} onChange={setEvidence}/></details><Button variant="ghost" disabled={busy} onClick={() => void act(async () => { const fields = await request('accounting', 'GET', '/v1/companies/' + company + '/finance/field-sets/'+sourcePath); const url = URL.createObjectURL(new Blob([JSON.stringify(fields, null, 2)], { type: 'application/json' })); const link = document.createElement('a'); link.href = url; link.download = 'gst-allocation-fields.json'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); })}>Download allocation field guide</Button><Button disabled={busy || !evidence} onClick={() => void act(async () => { const body = JSON.parse(evidence); if (!Array.isArray(body.records) || body.records.length < 1 || body.records.length > 200)
            throw new Error('Use an evidence batch with 1–200 records.'); await create('accounting', '/v1/companies/' + company + '/'+sourcePath, body); setEvidence(''); setMessage('Statutory evidence captured. Refresh GST data before preparing a new return.'); })}>Validate and capture evidence</Button></section>}
  </>}
 </div>;
}
