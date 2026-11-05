'use client';

import {Fragment,useEffect,useRef,useState} from 'react';
import {Button,Checkbox,Select,TextField,formatDate,formatMoney,formatQuantity,resolvedDisplay,useFormatters} from '@janso/ui';
import type {components} from '@janso/api-client/reports';
import {productFieldRequest as request} from '../lib/product-fields';
import {ReportReference} from './ReportReference';
import {ReportSources} from './ReportSources';
import {trackingId} from '../lib/stock-tracking-resources';
import type {ReportReferenceSource} from '../lib/report-references';
import {FinancialReports} from './FinancialReports';
import type {FiscalYearChoice} from '../lib/company-context';
import {ReportYearRange,useReportYearDates} from './ReportYearRange';
import {reportRowLabel} from '../lib/report-labels';
import {canPreviewReportExport,reportDownloadHref,reportExportOptions,trackReportExport} from '../lib/report-exports';
import {parameterText,parameterType as property,reportParameters,type ReportParameter as Property} from '../lib/report-parameters';

type Schemas=components['schemas'];
type Job=Schemas['JobDetail'];
type Definition=Schemas['DefinitionDetail'];
type Row=Schemas['ResultRow'];
const pending=(job:Job|null)=>!!job&&['QUEUED','RUNNING'].includes(job.status);
const errorText:Record<string,string>={
  AUTHORITY_REVOKED:'Your access changed. Request a new report after checking your permissions.',
  REPORT_VERIFICATION_FAILED:'This report could not be verified within its supported limits. Narrow the selection or check its source.',
  DEPENDENCY_UNAVAILABLE:'A required service or storage location is unavailable. You can retry this job.',
  REPORT_CAPACITY_EXCEEDED:'This selection exceeds the report limit. Choose a shorter period or a bulk report.',
};
function initial(definition:Definition):Record<string,string>{
  return Object.fromEntries(Object.entries(definition.parameter_schema.properties??{}).map(([key,item])=>{
    const value=(item as Property).default;return [key,parameterText(value)];
  }));
}

type WorkspaceProps={company:string;permissions:readonly string[];year?:FiscalYearChoice|null;years?:readonly FiscalYearChoice[];initialReport?:string;initialParty?:string;initialRun?:string};
export function ReportWorkspace({company,permissions,year,years=[],initialReport,initialParty,initialRun}:WorkspaceProps){
  const [classic,setClassic]=useState(false);
  return <><nav className="janso-report-actions" aria-label="Report workspace">
    <Button variant={!classic?'primary':'ghost'} onClick={()=>setClassic(false)} aria-pressed={!classic}>Report workspace</Button>
    <Button variant={classic?'primary':'ghost'} onClick={()=>setClassic(true)} aria-pressed={classic}>Classic reports and banking</Button>
  </nav>{classic?<FinancialReports company={company} permissions={permissions} year={year} years={years}/>:<FrameworkReports key={[company,initialReport,initialParty,initialRun].join(':')} company={company} permissions={permissions} year={year} years={years} initialReport={initialReport} initialParty={initialParty} initialRun={initialRun}/>}</>;
}

export function FrameworkReports({company,permissions,year,years=[],initialReport,initialParty,initialRun}:WorkspaceProps){
  const format=useFormatters();
  const range=useReportYearDates(company,year,years);
  const base='/v2/companies/'+company;
  const [definitions,setDefinitions]=useState<Definition[]>([]),[code,setCode]=useState(initialReport??'');
  const [generations,setGenerations]=useState<Schemas['ListItem'][]>([]),[generation,setGeneration]=useState('');
  const [parameters,setParameters]=useState<Record<string,string>>({}),[view,setView]=useState('default');
  const [referencesReady,setReferencesReady]=useState<Record<string,boolean>>({});
  const [execution,setExecution]=useState<'STANDARD'|'BULK'>('STANDARD'),[delivery,setDelivery]=useState<'SINGLE'|'PACKAGE'>('SINGLE');
  const [run,setRun]=useState<Job|null>(null),[exportJob,setExportJob]=useState<Job|null>(null);
  const [rows,setRows]=useState<Row[]>([]),[cursor,setCursor]=useState<string|null>(null);
  const [rowDetail,setRowDetail]=useState<Row|null>(null);
  const [history,setHistory]=useState<Schemas['JobListItem'][]>([]),[historyCursor,setHistoryCursor]=useState<string|null>(null);
  const [exports,setExports]=useState<Schemas['JobListItem'][]>([]),[exportCursor,setExportCursor]=useState<string|null>(null);
  const [busy,setBusy]=useState(false),[message,setMessage]=useState(''),[loaded,setLoaded]=useState(false);
  const retry=useRef<{payload:string;key:string}|null>(null);
  const selected=definitions.find(item=>item.definition.code===code);
  const canExport=permissions.includes('report.export');
  async function act(work:()=>Promise<void>){setBusy(true);setMessage('');try{await work();}catch(error){setMessage(error instanceof Error?error.message:'Unable to complete report action');}finally{setBusy(false);}}
  async function create<T>(path:string,body:unknown={}){
    const payload=JSON.stringify({path,body});if(retry.current?.payload!==payload)retry.current={payload,key:crypto.randomUUID()};
    const value=await request<T>('reports','POST',base+path,body,retry.current.key);retry.current=null;return value;
  }
  async function page(identity:string,next:string|null,signal?:AbortSignal){
    const result=await request<Schemas['ResultPage']>('reports','GET',base+'/report-runs/'+identity+'/rows?limit=50'+(next?'&cursor='+encodeURIComponent(next):''),undefined,undefined,signal);
    if(signal?.aborted)return;
    setRows(result.items);setCursor(result.page.next_cursor);
  }
  function selectRun(result:Job){
    setRowDetail(null);
    setRun(result);setCode(result.code);setGeneration(result.generation_id);
    setParameters(Object.fromEntries(Object.entries(result.parameters).map(([key,value])=>[key,parameterText(value)])));
    if(typeof result.parameters.date_to==='string')range.restore(typeof result.parameters.date_from==='string'?result.parameters.date_from:range.from,result.parameters.date_to);
    setView(result.view??result.views[0]?.key??'default');setExecution(result.execution??'STANDARD');
  }
  async function readRun(identity:string,signal?:AbortSignal){
    const result=await request<Job>('reports','GET',base+'/report-runs/'+identity,undefined,undefined,signal);if(signal?.aborted)return;selectRun(result);setExportJob(null);
    if(result.status==='COMPLETE')await page(identity,null,signal);else{setRows([]);setCursor(null);}
  }
  async function historyPage(next:string|null){
    const result=await request<Schemas['JobPage']>('reports','GET',base+'/report-runs?limit=20'+(next?'&cursor='+encodeURIComponent(next):''));
    setHistory(result.items);setHistoryCursor(result.page.next_cursor);
  }
  async function exportHistoryPage(next:string|null){
    const result=await request<Schemas['JobPage']>('reports','GET',base+'/report-exports?limit=20'+(next?'&cursor='+encodeURIComponent(next):''));
    setExports(result.items);setExportCursor(result.page.next_cursor);
  }
  async function load(signal?:AbortSignal){
    const [catalog,sources,recent,exported]=await Promise.all([
      request<Schemas['DefinitionCatalog']>('reports','GET',base+'/report-definitions',undefined,undefined,signal),
      request<Schemas['ResourcePage']>('reports','GET',base+'/report-generations?limit=50',undefined,undefined,signal),
      request<Schemas['JobPage']>('reports','GET',base+'/report-runs?limit=20',undefined,undefined,signal),
      canExport?request<Schemas['JobPage']>('reports','GET',base+'/report-exports?limit=20',undefined,undefined,signal):Promise.resolve(null),
    ]);
    if(signal?.aborted)return;
    if(!Array.isArray(catalog.items)||!Array.isArray(sources.items)||sources.items.length>50||!Array.isArray(recent.items))throw new Error('The report workspace could not be read. Refresh and retry.');
    setDefinitions(catalog.items);setGenerations(sources.items);setHistory(recent.items);setHistoryCursor(recent.page.next_cursor);
    if(exported){setExports(exported.items);setExportCursor(exported.page.next_cursor);}
    if(!loaded&&initialReport){
      const requested=catalog.items.find(item=>item.definition.code===initialReport);
      setCode(requested?initialReport:'');
      setParameters(requested?{...initial(requested),...(initialReport==='PARTY_LEDGER'&&trackingId.test(initialParty??'')&&(requested.parameter_schema.properties as Record<string,unknown>|undefined)?.party_id?{party_id:initialParty!}:{})}:{});
      if(!requested)setMessage('The selected report is not available with your current access. Choose another available report.');
    }
    setLoaded(true);
    if(initialRun&&!loaded)await readRun(initialRun,signal);
  }
  useEffect(()=>{
    const controller=new AbortController();setBusy(true);setMessage('');
    void load(controller.signal).catch(error=>{if(!controller.signal.aborted)setMessage(error instanceof Error?error.message:'Unable to load the report workspace.');}).finally(()=>{if(!controller.signal.aborted)setBusy(false);});
    return()=>controller.abort();
  },[base,initialReport,initialParty,initialRun,canExport]);
  useEffect(()=>{
    if(!pending(run))return;
    let cancelled=false;
    const controller=new AbortController();
    let timer:ReturnType<typeof setTimeout>;
    async function poll(){
      try{
        const result=await request<Job>('reports','GET',base+'/report-runs/'+run!.id,undefined,undefined,controller.signal);
        if(cancelled)return;
        if(result.status==='COMPLETE'){
          const resultPage=await request<Schemas['ResultPage']>('reports','GET',base+'/report-runs/'+result.id+'/rows?limit=50',undefined,undefined,controller.signal);
          if(cancelled)return;
          setRows(resultPage.items);setCursor(resultPage.page.next_cursor);
        }
        setRun(result);
      }catch(error){if(!cancelled){setMessage(error instanceof Error?error.message:'Report status unavailable');timer=setTimeout(()=>void poll(),5000);}}
    }
    timer=setTimeout(()=>void poll(),2500);
    return()=>{cancelled=true;controller.abort();clearTimeout(timer);};
  },[base,run]);
  useEffect(()=>{
    if(!canExport||!pending(exportJob))return;
    const controller=new AbortController();
    void trackReportExport(company,exportJob!,controller.signal,setExportJob).catch(error=>{
      if(!controller.signal.aborted)setMessage(error instanceof Error?error.message:'Export status unavailable');
    });
    return()=>controller.abort();
  },[company,canExport,exportJob?.id,exportJob?.status]);
  const properties=(selected?.parameter_schema.properties??{}) as Record<string,Property>;
  useEffect(()=>{
    setParameters(current=>{
      const next={...current};if(properties.date_from)next.date_from=range.from;if(properties.date_to)next.date_to=range.to;
      return next;
    });
  },[code,!!properties.date_from,!!properties.date_to,range.from,range.to]);
  const required=(selected?.parameter_schema.required??[]) as string[];
  const referenceSources:Record<string,ReportReferenceSource>={account_id:'accounts',group_id:selected?.definition.datasets?.includes('inventory')?'item-groups':'account-groups',party_id:'parties',item_id:'items',location_id:'warehouses',lot_id:'batches'};
  const referencesBlocked=Object.keys(properties).some(key=>referenceSources[key]&&!!parameters[key]&&referencesReady[key]!==true);
  const createDisabled=busy||!generation||!selected?.run_enabled||referencesBlocked;
  const columns=run?.views.find(item=>item.key===view)?.columns??run?.views[0]?.columns??[];
  const exportOptions=reportExportOptions({run,limits:selected?.export_limits,view,delivery,packageLimits:selected?.package_limits});
  const retainedView=run?.views.find(item=>item.key===(run.view??'default'));
  const exportCompatible=!run||((run.views.find(item=>item.key===view)?.calculation??'detail')===(retainedView?.calculation??'detail'));
  const display=run?.display?resolvedDisplay(run.display):null;
  function cell(column:Schemas['Column'],row:Row){
    const value=row.data[column.key];if(value===null||value===undefined)return '—';
    if(column.key==='row_kind'&&typeof value==='string')return reportRowLabel(value);
    if(display&&typeof value==='string'){
      if(column.kind==='MONEY')return formatMoney(value,display,{display:'none'});
      if(column.kind==='DECIMAL')return formatQuantity(value,display);
      if(column.kind==='DATE')return formatDate(value,display);
    }
    return typeof value==='object'?JSON.stringify(value):String(value);
  }
  function jobStatus(job:Job,isExport=false){
    const resource=isExport?'/report-exports/':'/report-runs/',set=isExport?setExportJob:setRun;
    return <section className="janso-report-status" aria-label={isExport?'Export status':'Report status'}>
      <p role="status">{isExport?'Export':'Report'}: {job.status}{job.completed_rows>0?` · ${job.completed_rows} rows`:''}</p>
      {job.failure_code&&<p role="alert">{errorText[job.failure_code]??'This job could not be completed. Check its parameters and source before trying again.'}</p>}
      <div className="janso-report-actions">
        <Button variant="ghost" disabled={busy} onClick={()=>void act(async()=>{if(isExport)set(await request<Job>('reports','GET',base+resource+job.id));else await readRun(job.id);})}>Refresh {isExport?'export':'report'}</Button>
        {pending(job)&&<Button disabled={busy} onClick={()=>void act(async()=>set(await create<Job>(resource+job.id+'/cancel')))}>Cancel {isExport?'export':'report'}</Button>}
        {job.status==='FAILED'&&<Button disabled={busy} onClick={()=>void act(async()=>set(await create<Job>(resource+job.id+'/retry')))}>Retry {isExport?'export':'report'}</Button>}
        {isExport&&job.status==='COMPLETE'&&canExport&&<><a href={reportDownloadHref(company,job.id)}>Download export</a>{canPreviewReportExport(job)&&<a href={reportDownloadHref(company,job.id,true)} target="_blank" rel="noopener noreferrer">Open print preview</a>}</>}
      </div>
    </section>;
  }
  return <section className="janso-report-workspace" aria-label="Report framework">
    <header className="janso-report-header"><div><h1>Reports</h1><p>Choose a report, review the details and export the result.</p></div>
      <Button variant="ghost" disabled={busy} onClick={()=>void act(load)}>Load report workspace</Button>
    </header>
    {busy&&!loaded&&<p role="status">Loading report definitions, sources and recent history</p>}
    {loaded&&definitions.length===0&&<p>No reports are available with your current permissions.</p>}
    <Select label="Report" value={code} disabled={busy} options={definitions.map(item=>({value:item.definition.code,label:item.definition.title}))} onChange={value=>{
      setCode(value);const item=definitions.find(item=>item.definition.code===value);setParameters(item?initial(item):{});setView(item?.definition.views[0]?.key??'default');setExecution('STANDARD');setDelivery('SINGLE');setRun(null);setRows([]);setCursor(null);setExportJob(null);
    }}/>
    {selected&&<section aria-label="Report settings"><h2>Report settings</h2><p>{selected.definition.description}</p>
      {!selected.run_enabled&&<p>New reports are not enabled for this deployment. Completed results remain available.</p>}
<ReportSources company={company} sources={generations} value={generation} onChange={setGeneration} disabled={busy} inventory={!!selected.definition.datasets?.includes('inventory')}/>
      <Select label="Report view" value={view} disabled={busy} options={selected.definition.views.map(item=>({value:item.key,label:item.title}))} onChange={setView}/>
      {(properties.date_from||properties.date_to)&&<ReportYearRange range={range} disabled={busy}/>}
      {code==='BALANCE_SHEET'&&<p>Previous-year accumulated earnings and current-year profit are calculated separately from posted history. These displayed earnings are derived balances.</p>}
      {selected.execution_limits?.BULK&&<Select label="Report size" value={execution} disabled={busy} options={[{value:'STANDARD',label:'Standard'},{value:'BULK',label:'Bulk'}]} onChange={value=>setExecution(value as 'STANDARD'|'BULK')}/>}
      {selected.execution_limits&&<p>Up to {selected.execution_limits[execution]?.toLocaleString('en-IN')} result rows.</p>}
      <form className="janso-form-grid" onSubmit={event=>{event.preventDefault();if(createDisabled)return;void act(async()=>{
        const values=reportParameters(properties,parameters);
        const next=await create<Job>('/report-runs',{code,version:selected.definition.version,generation_id:generation,parameters:values,view,execution});setRun(next);setRows([]);setCursor(null);setExportJob(null);
      });}}>
        {Object.entries(properties).map(([key,raw])=>{
          const item=property(raw),label=raw.title??key.replaceAll('_',' '),value=parameters[key]??'';
          if(key==='currency'&&properties.basis&&parameters.basis!=='TRANSACTION')return null;
          const change=(value:string)=>{if(key==='date_from'||key==='date_to')range.custom(key==='date_from'?'from':'to',value);if(referenceSources[key])setReferencesReady(current=>({...current,[key]:!value}));setParameters(previous=>({...previous,[key]:value,...(key==='item_id'&&properties.lot_id?{lot_id:''}:{})}));};
          if(referenceSources[key])return <ReportReference key={key} company={company} code={code} source={referenceSources[key]} item={key==='lot_id'?parameters.item_id:undefined} label={label} value={value} disabled={busy} required={required.includes(key)} onChange={change} onStateChange={ready=>setReferencesReady(current=>current[key]===ready?current:{...current,[key]:ready})}/>;
          if(item.type==='boolean')return <Checkbox key={key} checked={value==='true'} disabled={busy} onChange={event=>change(String(event.target.checked))}>{label}</Checkbox>;
          if(item.enum)return <Select key={key} label={label} value={value} disabled={busy} options={[...(!required.includes(key)?[{value:'',label:'All'}]:[]),...item.enum.map(value=>({value,label:value.replaceAll('_',' ')}))]} onChange={change}/>;
          return <TextField key={key} label={label} value={value} type={item.format==='date'?'date':item.type==='integer'?'number':'text'} min={item.minimum} max={item.maximum} hint={item.type==='array'?'Separate whole-number day limits with commas.':undefined} required={required.includes(key)||(key==='currency'&&parameters.basis==='TRANSACTION')||(key==='comparative_from'&&!!parameters.comparative_to)||(key==='comparative_to'&&!!parameters.comparative_from)} pattern={item.pattern} disabled={busy} onChange={event=>change(event.target.value)}/>;
        })}
        <Button type="submit" disabled={createDisabled}>Create report</Button>
      </form>
      {permissions.includes('report.definition.manage')&&<Button disabled={busy} onClick={()=>void act(async()=>{await create('/report-generations',generation?{strategy:'REFRESH',base_generation_id:generation}:{strategy:'FRESH'});setMessage('Source refresh requested. Reload the workspace to check progress.');})}>Refresh report sources</Button>}
    </section>}
    {run&&<section aria-label="Report result"><h2>{run.title}</h2><p className="janso-report-source">Source snapshot: {run.generation_id}</p>{jobStatus(run)}
      {run.origin&&<Button disabled={busy} onClick={()=>void act(()=>readRun(run.origin!.parent_id))}>Back to parent report</Button>}
      {run.status==='COMPLETE'&&<>
        {rows.length===0?<p>No rows for the selected parameters.</p>:<div className="janso-table-shell" role="region" aria-label="Report rows" tabIndex={0}>
          <table className="janso-table"><caption>{run.title} · rows {rows[0].ordinal}–{rows.at(-1)!.ordinal}</caption>
            <thead><tr>{columns.map(column=><th scope="col" key={column.key}>{column.title}</th>)}<th scope="col">Details</th></tr></thead>
            <tbody>{rows.map(row=><tr key={row.ordinal}>{columns.map(column=><td key={column.key}>{cell(column,row)}</td>)}
              <td>{(row.drilldowns??[]).map(link=><Button key={link.key} disabled={busy} onClick={()=>void act(async()=>{
                if(link.method==='GET'){
                  setRowDetail(await request<Row>('reports','GET',base+'/report-runs/'+run.id+'/rows/'+row.ordinal+'?token='+encodeURIComponent(link.token)));
                  return;
                }
                const child=await create<Job>('/report-runs/'+run.id+'/drilldowns',{token:link.token});selectRun(child);setRows([]);setCursor(null);setExportJob(null);
              })}>{link.title}</Button>)}</td>
            </tr>)}</tbody>
          </table>
        </div>}
        {rowDetail&&<section aria-label="Row detail"><h3>Row {rowDetail.ordinal} details</h3><dl>{Object.entries(rowDetail.data).map(([key,value])=>{
          const column=columns.find(item=>item.key===key);
          return <Fragment key={key}><dt>{column?.title??key.replaceAll('_',' ')}</dt><dd>{column?cell(column,rowDetail):value===null?'—':String(value)}</dd></Fragment>;
        })}</dl><Button onClick={()=>setRowDetail(null)}>Close row detail</Button></section>}
        {rows.length>0&&rows[0].ordinal>1&&<Button disabled={busy} onClick={()=>void act(()=>page(run.id,null))}>First report page</Button>}
        {cursor&&<Button disabled={busy} onClick={()=>void act(()=>page(run.id,cursor))}>Next report page</Button>}
        {canExport&&selected?.package_limits?.max_parts&&<Select label="PDF and HTML delivery" value={delivery} disabled={busy} options={[{value:'SINGLE',label:'Single document'},{value:'PACKAGE',label:'Document parts (ZIP)'}]} onChange={value=>setDelivery(value as 'SINGLE'|'PACKAGE')}/>}
        {!exportCompatible&&<p>Create a new report to use this calculation view.</p>}
        <div className="janso-report-actions" aria-label="Export formats">{canExport&&exportOptions.map(option=>
          <Button variant="ghost" key={option.id} disabled={busy||pending(exportJob)||!!option.disabledReason} title={option.disabledReason??'Export all matching rows as '+option.label} onClick={()=>void act(async()=>setExportJob(await create<Job>('/report-runs/'+run.id+'/exports',{format:option.id,view,delivery:option.delivery})))}>Export {option.id}</Button>
        )}</div>
      </>}
    </section>}
    {canExport&&exportJob&&jobStatus(exportJob,true)}
    {history.length>0&&<section className="janso-report-history" aria-label="Report history"><h2>Recent reports</h2><ul>{history.map(item=><li key={item.id}><Button variant="ghost" disabled={busy} onClick={()=>void act(()=>readRun(item.id))}>{item.code.replaceAll('_',' ')} · {item.status} · {format.dateTime(item.created_at)} · {item.id}</Button></li>)}</ul>{historyCursor&&<Button disabled={busy} onClick={()=>void act(()=>historyPage(historyCursor))}>Older reports</Button>}</section>}
    {exports.length>0&&<section className="janso-report-history" aria-label="Export history"><h2>Recent exports</h2>
      <ul>{exports.map(item=><li key={item.id}><Button variant="ghost" disabled={busy} onClick={()=>void act(async()=>setExportJob(await request<Job>('reports','GET',base+'/report-exports/'+item.id)))}>{item.code.replaceAll('_',' ')} · {item.status} · {format.dateTime(item.created_at)} · {item.id}</Button></li>)}</ul>
      {exportCursor&&<Button disabled={busy} onClick={()=>void act(()=>exportHistoryPage(exportCursor))}>Older exports</Button>}
    </section>}
    {message&&<p role="alert">{message}</p>}
  </section>;
}
