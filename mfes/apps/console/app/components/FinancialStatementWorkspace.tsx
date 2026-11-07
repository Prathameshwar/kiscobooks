'use client';
import {prepareFinanceSource,financeRunFailure,financeSourceStale,FinanceSourceError} from '../lib/finance-source';

import {useCallback,useEffect,useId,useRef,useState} from 'react';
import {Button,Checkbox,FilterIcon,PageNavigation,PreparationProgress,SegmentedControl,Select,SplitButton,TextField,businessToday,formatDate,formatMoney,resolvedDisplay,useDisplayConfig,useFormatters} from '@janso/ui';
import type {components} from '@janso/api-client/reports';
import type {FiscalYearChoice} from '../lib/company-context';
import {productFieldRequest as request,ProductFieldError} from '../lib/product-fields';
import {goTo} from '../lib/navigate';
import {trackingId} from '../lib/stock-tracking-resources';
import {canPreviewReportExport,reportDownloadHref,reportExportFailure,reportExportOptions,trackReportExport,type ReportExportFormat} from '../lib/report-exports';
import {comparisonDates,type ComparisonPreset,type ProfitMode,type ProfitRow,type ProfitSummary} from '../lib/profit-loss';
import {balanceComparisonDate,type BalanceComparisonPreset} from '../lib/balance-sheet';
import {ReportWorkspace} from './ReportWorkspace';

type S=components['schemas'];
type Job=S['JobDetail'];
type Row=S['ResultRow'];
export type FinancialStatementProps={company:string;companyName:string;actor:string;permissions:readonly string[];year?:FiscalYearChoice|null;years?:readonly FiscalYearChoice[];initialRun?:string};
const pending=(job:Job)=>job.status==='QUEUED'||job.status==='RUNNING';
const coverage=(source:S['SourceGenerationDetail'])=>{
  const control=source.manifest?.control as {coverage_start?:unknown}|undefined;
  return typeof control?.coverage_start==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(control.coverage_start)?control.coverage_start:'';
};
function wait(signal:AbortSignal){return new Promise<void>((resolve,reject)=>{
  const abort=()=>{clearTimeout(timer);reject(signal.reason);};
  const timer=setTimeout(()=>{signal.removeEventListener('abort',abort);resolve();},1500);
  signal.addEventListener('abort',abort,{once:true});
});}

function StatementTable({rows,mode,currency,busy,collapsed,money,onToggle,onDrill,title,balance=false,currentDate,previousDate}:{
  title:string;balance?:boolean;currentDate?:string;previousDate?:string;rows:Row[];mode:ProfitMode;currency:string;busy:boolean;collapsed:string[];
  money:(value:string)=>string;onToggle:(id:string)=>void;onDrill:(row:Row,previous?:boolean)=>void;
}){
  return <div className="janso-profit-scroll" role="region" aria-label={title+' statement'} tabIndex={0} aria-busy={busy} data-view={mode}>
    <table>
      <caption className="janso-visually-hidden">{title} {mode==='comparison'?(balance?'as-of comparison':'period comparison'):'statement'}, {currency}. Group and section rows contain totals; account rows are their detail.</caption>
      <thead><tr><th scope="col">Account / group</th><th scope="col">Current{currentDate&&<small className="janso-balance-column-date"> As at {currentDate}</small>}</th>{mode==='comparison'&&<><th scope="col">Previous{previousDate&&<small className="janso-balance-column-date"> As at {previousDate}</small>}</th><th scope="col">Change</th><th scope="col">Change %</th></>}</tr></thead>
      <tbody>{rows.filter(item=>item.data.row_kind!=='ACCOUNT'||!collapsed.includes(String(item.data.group_id))).map(item=>{
        const value=item.data as ProfitRow,kind=value.row_kind,group=kind==='GROUP',account=kind==='ACCOUNT';
        const groupId=String(value.group_id),isCollapsed=collapsed.includes(groupId);
        const priorLink=account&&item.drilldowns?.some(link=>link.key===(balance?'balance_comparison_entries':'comparison_account_entries'));
        return <tr key={item.ordinal} data-kind={kind} data-negative={(kind==='GROSS_PROFIT'||kind==='NET_PROFIT')&&value.amount.startsWith('-')&& !/^-0\.0+$/.test(value.amount)}>
          <th scope="row"><span className="janso-profit-row-label">
            {group?<button className="janso-profit-disclosure" type="button" aria-expanded={!isCollapsed} aria-label={(isCollapsed?'Expand ':'Collapse ')+value.label} onClick={()=>onToggle(groupId)}>{isCollapsed?'▸':'▾'}</button>:account?<span className="janso-profit-indent" aria-hidden="true"/>:null}
            {account&&item.drilldowns?.some(link=>link.key===(balance?'balance_account_entries':'account_entries'))?<button className="janso-profit-account" disabled={busy} onClick={()=>onDrill(item)}>{value.label}</button>:<span>{value.label}</span>}
            {account&&<small>{value.account_code} · {value.group_name}</small>}
            {account&&(value.imported_ytd_amount||value.previous_imported_ytd_amount)&&<small>Imported YTD: current {money(value.imported_ytd_amount??'0.0000')}{mode==='comparison'?' · previous '+money(value.previous_imported_ytd_amount??'0.0000'):''}</small>}
            {group&&<small>{value.group_code}</small>}
          </span></th>
          <td title={'Exact amount: '+value.amount}>{money(value.amount)}</td>
          {mode==='comparison'&&<>
            <td title={'Exact amount: '+value.previous_amount}>{priorLink?<button className="janso-profit-account" disabled={busy} aria-label={'View previous entries for '+value.label} onClick={()=>onDrill(item,true)}>{money(value.previous_amount??'0.0000')}</button>:money(value.previous_amount??'0.0000')}</td>
            <td title={'Exact amount: '+value.change_amount}>{money(value.change_amount??'0.0000')}</td>
            <td>{value.change_percent??'—'}</td>
          </>}
        </tr>;
      })}</tbody>
    </table>
    {rows.length===0&&!busy&&<p>No detail rows on this page.</p>}
  </div>;
}

export function FinancialStatementWorkspace({company,companyName,actor,permissions,year,years=[],initialRun,reportCode}:FinancialStatementProps & {reportCode:'PROFIT_LOSS'|'BALANCE_SHEET'}){
  const balance=reportCode==='BALANCE_SHEET',title=balance?'Balance Sheet':'Profit and Loss';
  const standardLabel=balance?'Standard':'Statement',comparisonLabel=balance?'Comparative':'Period comparison';
  const displayConfig=useDisplayConfig(),format=useFormatters(),today=businessToday(displayConfig.timezone),base='/v2/companies/'+company;
  const [from,setFrom]=useState(year?.startDate??today.slice(0,8)+'01');
  const [to,setTo]=useState(year?.current&&today<=year.endDate?today:year?.endDate??today);
  const [mode,setMode]=useState<ProfitMode>('default'),[preset,setPreset]=useState<ComparisonPreset|BalanceComparisonPreset>(balance?'YEAR_END':'PREVIOUS');
  const [comparisonFrom,setComparisonFrom]=useState(''),[comparisonTo,setComparisonTo]=useState('');
  const [showZero,setShowZero]=useState(false),[filtersOpen,setFiltersOpen]=useState(false);
  const retainedSource=useRef(false);
  const [sourceRetry,setSourceRetry]=useState(false);
  const [verifiedAt,setVerifiedAt]=useState<string|null>(null);
  const [periodNotice,setPeriodNotice]=useState('');
  const [definition,setDefinition]=useState<S['DefinitionDetail']|null>(null),[generation,setGeneration]=useState(''),[coverageStart,setCoverageStart]=useState('');
  const [run,setRun]=useState<Job|null>(null),[candidate,setCandidate]=useState<Job|null>(null),[rows,setRows]=useState<Row[]>([]);
  const [cursors,setCursors]=useState<(string|null)[]>([null]),[page,setPage]=useState(0),[next,setNext]=useState<string|null>(null);
  const [collapsed,setCollapsed]=useState<string[]>([]),[exportJob,setExportJob]=useState<Job|null>(null),[exportFormat,setExportFormat]=useState<ReportExportFormat>('PDF');
  const [exportSubmitting,setExportSubmitting]=useState(false),[busy,setBusy]=useState(('Loading '+title)),[error,setError]=useState(''),[blocked,setBlocked]=useState(false),[stopped,setStopped]=useState(false),[reload,setReload]=useState(0),[legacy,setLegacy]=useState(false);
  const [owner,setOwner]=useState(company+':'+actor),[history,setHistory]=useState<S['JobPage']|null>(null);
  const [filterFocus,setFilterFocus]=useState<string|null>(null);
  const filterForm=useRef<HTMLFormElement>(null);
  useEffect(()=>{if(filtersOpen&&filterFocus){(filterForm.current?.elements.namedItem(filterFocus) as HTMLElement|null)?.focus();setFilterFocus(null);}},[filtersOpen,filterFocus]);
  const filtersId=useId(),filterTrigger=useRef<HTMLButtonElement>(null),controller=useRef<AbortController|null>(null),exportController=useRef<AbortController|null>(null),downloaded=useRef(new Set<string>()),keys=useRef(new Map<string,string>()),candidateSource=useRef<S['SourceGenerationDetail']|null>(null);
  const canRead=permissions.includes('report.read'),canExport=permissions.includes('report.export'),canPrepare=permissions.includes('report.definition.manage');
  const display=run?.display?resolvedDisplay(run.display):displayConfig;
  const resultDate=(raw:string)=>formatDate(raw,display);
  const money=(value:string)=>formatMoney(value,display,{display:'none'});
  const summary=((run?.result as {evidence?:{profit_summary?:ProfitSummary;balance_summary?:ProfitSummary}}|null)?.evidence?.[balance?'balance_summary':'profit_summary']);
  const priorDate=preset==='CUSTOM'?comparisonTo:balanceComparisonDate(to,preset as Exclude<BalanceComparisonPreset,'CUSTOM'>,years.length?years:year?[year]:[]);
  const selectedComparison=balance?{from:priorDate,to:priorDate}:preset==='CUSTOM'?{from:comparisonFrom,to:comparisonTo}:from&&to&&from<=to?comparisonDates(from,to,preset as 'PREVIOUS'|'LAST_YEAR'):{from:'',to:''};
  const resultMode:ProfitMode=run?.view==='comparison'?'comparison':'default';
  const exportOptions=reportExportOptions({run,limits:definition?.export_limits,view:resultMode,formats:['PDF','XLSX','CSV','HTML']});
  const primary=exportOptions.find(item=>item.id===exportFormat)!;
  const exportBusy=exportSubmitting||!!exportJob&&pending(exportJob);
  const stage=stopped?'stopped':busy&&candidate&&pending(candidate)?candidate.status:busy==='Updating accounting data'?'source':busy?'preparing':null;
  const stageText=stage==='stopped'?['Report stopped','Apply the filters to run it again.']:stage==='QUEUED'?['Report queued','Waiting for a report worker.']:stage==='RUNNING'?['Calculating report',balance?'Checking assets, liabilities and equity.':'Grouping income and expenses.']:stage==='source'?['Preparing accounting data','Verifying the accounting snapshot.']:['Preparing report','Checking dates and report settings.'];

  const fail=useCallback((value:unknown)=>{
    setSourceRetry(value instanceof FinanceSourceError);
    if(value instanceof ProductFieldError&&(value.status===401||value.status===403)){
      setBlocked(true);setRun(null);setRows([]);setExportJob(null);controller.current?.abort();exportController.current?.abort();
    }
    setError(value instanceof Error?value.message:(''+title+' is unavailable. Retry the report.'));
  },[title]);
  const command=useCallback(async<T,>(path:string,body:unknown,signal:AbortSignal)=>{
    const payload=JSON.stringify({path,body});
    if(!keys.current.has(payload))keys.current.set(payload,crypto.randomUUID());
    const value=await request<T>('reports','POST',base+path,body,keys.current.get(payload),signal);
    keys.current.delete(payload);signal.throwIfAborted();return value;
  },[base]);
  const work=useCallback(async(label:string,action:(signal:AbortSignal)=>Promise<void>)=>{
    controller.current?.abort();const active=new AbortController();controller.current=active;setBusy(label);setError('');
    try{await action(active.signal);}catch(value){if(!active.signal.aborted)fail(value);}
    finally{if(controller.current===active)setBusy('');}
  },[fail]);
  const sourceReady=useCallback(async(signal:AbortSignal)=>{
    let cursor:string|null=null;
    for(let i=0;i<20;i++){
      const page:S['ResourcePage']=await request('reports','GET',base+'/report-generations?limit=50'+(cursor?'&cursor='+encodeURIComponent(cursor):''),undefined,undefined,signal);
      const item=page.items.find(row=>row.status==='READY');
      if(item){const detail=await request<S['SourceGenerationDetail']>('reports','GET',base+'/report-generations/'+item.id,undefined,undefined,signal);if(detail.id!==item.id||detail.status!=='READY')throw new Error('The selected accounting snapshot changed. Retry the report.');return detail;}
      cursor=page.page.next_cursor;if(!cursor)break;
    }
    return null;
  },[base]);
  const prepare=useCallback(async(previous:string,signal:AbortSignal)=>{
    return prepareFinanceSource(base,previous,signal,command,candidateSource,()=>setBusy('Updating accounting data'));
  },[base,command]);
  const readPage=useCallback(async(job:Job,cursor:string|null,index:number,signal:AbortSignal)=>{
    const result=await request<S['ResultPage']>('reports','GET',base+'/report-runs/'+job.id+'/rows?limit=200'+(cursor?'&cursor='+encodeURIComponent(cursor):''),undefined,undefined,signal);
    signal.throwIfAborted();setRows(result.items);setCollapsed([]);setNext(result.page.next_cursor);setPage(index);
  },[base]);
  const finish=useCallback(async(initial:Job,signal:AbortSignal,recovered=false,restoreComparison=false,automaticFloor=''):Promise<void>=>{
    let current=initial;setCandidate(current);
    while(pending(current)){
      setBusy(current.status==='QUEUED'?(''+title+' queued'):('Calculating '+title+''));await wait(signal);
      current=await request<Job>('reports','GET',base+'/report-runs/'+initial.id,undefined,undefined,signal);signal.throwIfAborted();
      if(current.id!==initial.id)throw new Error('The report response changed. Retry the report.');
      setCandidate(current);
    }
    if(current.status==='BLOCKED'&&current.failure_code==='INSUFFICIENT_ACCOUNTING_HISTORY'&&!balance&&!recovered&&automaticFloor&&current.view!=='comparison'&&String(current.parameters.date_from)<automaticFloor&&automaticFloor<=String(current.parameters.date_to)){
      setFrom(automaticFloor);
      setPeriodNotice('Showing available accounting history from '+format.date(automaticFloor)+'. This is a partial financial-year report.');
      const retry=await command<Job>('/report-runs',{code:reportCode,version:6,generation_id:current.generation_id,parameters:{...current.parameters,date_from:automaticFloor},view:'default'},signal);
      await finish(retry,signal,true);return;
    }
    if(current.status==='BLOCKED'&&current.failure_code==='INSUFFICIENT_ACCOUNTING_HISTORY'){
      setFiltersOpen(true);setFilterFocus(current.view==='comparison'?'comparisonPreset':'from');
      const floor=automaticFloor||coverageStart;
      throw new Error(floor?'Accounting history is available from '+format.date(floor)+'. Set From and comparison From to this date or later. Earlier periods need verified imported year-to-date balances.':financeRunFailure(current.failure_code,title));
    }
    if(current.status==='BLOCKED'&&current.failure_code==='REPORT_VERIFICATION_FAILED'&&canPrepare&&!recovered){
      const source=await prepare(current.generation_id,signal),floor=coverage(source),start=balance?String(current.parameters.date_to):String(current.parameters.date_from);
      if((floor&&(start<floor||String(current.parameters[balance?'comparative_to':'comparative_from']??start)<floor))||start>String(current.parameters.date_to))throw new Error('Accounting records begin on '+format.date(floor)+'. Choose a later period.');
      setGeneration(source.id);setCoverageStart(floor);setFrom(start);setVerifiedAt(source.verified_at??null);
      const parameters=balance?current.parameters:{...current.parameters,date_from:start};
      const retry=await command<Job>('/report-runs',{code:reportCode,version:6,generation_id:source.id,parameters,view:current.view??'default'},signal);
      await finish(retry,signal,true,restoreComparison);return;
    }
    if(current.status!=='COMPLETE')throw new Error(financeRunFailure(current.failure_code,title));
    if(restoreComparison){setVerifiedAt(null);retainedSource.current=true;}
    if(current.code!==reportCode||current.kind!=='RUN')throw new Error(('The selected report differs. Retry '+title+'.'));
    if(current.version<6){setLegacy(true);setRun(current);setCandidate(null);return;}
    exportController.current?.abort();setExportJob(null);
    await readPage(current,null,0,signal);setCursors([null]);setCollapsed([]);setRun(current);setCandidate(null);setStopped(false);setLegacy(false);
    setGeneration(current.generation_id);setFrom(String(balance?current.parameters.date_to:current.parameters.date_from));setTo(String(current.parameters.date_to));setMode(current.view==='comparison'?'comparison':'default');setShowZero(Boolean(current.parameters.show_zero));
    if(restoreComparison&&typeof current.parameters.comparative_to==='string'){setPreset('CUSTOM');setComparisonFrom(String(current.parameters.comparative_from??current.parameters.comparative_to));setComparisonTo(String(current.parameters.comparative_to));}
  },[base,balance,reportCode,title,canPrepare,prepare,command,readPage,format,coverageStart]);
  const launch=useCallback(async(source:string,start:string,end:string,view:ProfitMode,zero:boolean,comparative:{from:string;to:string}|null,signal:AbortSignal,automaticFloor='')=>{
    const invalid=(message:string,field='comparisonPreset'):never=>{if(balance){setFiltersOpen(true);setFilterFocus(field);}throw new Error(message);};
    if(balance&&!end)invalid('Choose an as-of date.','asOf');
    if(!source)throw new Error('Accounting data is being prepared. Retry shortly.');
    if(!end||(!balance&&(!start||start>end)))throw new Error('From date must be on or before To date.');
    if(view==='comparison'&&(!comparative?.from||!comparative.to||comparative.from>comparative.to))invalid(balance?'Choose an available comparison date in Filters.':'Choose a valid comparison period.');
    if(balance&&view==='comparison'&&comparative!.to>=end)invalid('Comparison date must be earlier than the as-of date.');
    if(balance&&coverageStart&&(end<coverageStart||(view==='comparison'&&comparative!.to<coverageStart)))invalid('Accounting records begin on '+format.date(coverageStart)+'. Choose a date within available history.',end<coverageStart?'asOf':'comparisonPreset');
    if(canPrepare&&!automaticFloor&&(retainedSource.current||financeSourceStale(verifiedAt))){const fresh=await prepare(source,signal);retainedSource.current=false;source=fresh.id;setGeneration(source);setCoverageStart(coverage(fresh));setVerifiedAt(fresh.verified_at??null);}
    exportController.current?.abort();setExportJob(null);
    const parameters=balance?{date_to:end,show_zero:zero,...(view==='comparison'?{comparative_to:comparative!.to}:{})}:{date_from:start,date_to:end,show_zero:zero,...(view==='comparison'?{comparative_from:comparative!.from,comparative_to:comparative!.to}:{})};
    const created=await command<Job>('/report-runs',{code:reportCode,version:6,generation_id:source,parameters,view},signal);await finish(created,signal,false,false,automaticFloor);
  },[balance,reportCode,coverageStart,format,command,finish,canPrepare,verifiedAt,prepare]);
  useEffect(()=>{
    setOwner(company+':'+actor);setBlocked(false);setDefinition(null);setRun(null);setCandidate(null);setRows([]);setHistory(null);setExportJob(null);setError('');setStopped(false);setLegacy(false);candidateSource.current=null;retainedSource.current=false;
    if(!canRead){setBlocked(true);setBusy('');return;}
    void work(('Loading '+title),async signal=>{
      const detail=await request<S['DefinitionDetail']>('reports','GET',base+'/report-definitions/'+reportCode,undefined,undefined,signal);
      signal.throwIfAborted();setDefinition(detail);
      if(initialRun){const retained=await request<Job>('reports','GET',base+'/report-runs/'+initialRun,undefined,undefined,signal);await finish(retained,signal,false,true);return;}
      let source=await sourceReady(signal);
      if((!source||financeSourceStale(source.verified_at))&&canPrepare&&detail.run_enabled)source=await prepare(source?.id??'',signal);
      setVerifiedAt(source?.verified_at??null);
      signal.throwIfAborted();const floor=source?coverage(source):'';setGeneration(source?.id??'');setCoverageStart(floor);
      const start=balance?to:floor&&from<floor?floor:from;if(start!==from)setFrom(start);
      if(!balance&&start!==from)setPeriodNotice('From defaults to '+format.date(start)+' because earlier detailed accounting history is unavailable. This is a partial financial-year report.');
      if((balance&&floor&&to<floor)||start>to){setFiltersOpen(true);setFilterFocus('asOf');throw new Error('No accounting history is available through the selected To date. Records begin on '+format.date(floor)+'. Choose To on or after that date.');}
      if(source&&detail.run_enabled&&detail.definition.version===6)await launch(source.id,start,to,'default',false,null,signal,floor);
    });
    return()=>{controller.current?.abort();exportController.current?.abort();};
  },[base,actor,reportCode,canRead,permissions.join('|'),initialRun,reload]);

  function loadHistory(cursor?:string|null){void work('Loading report history',async signal=>{const page=await request<S['JobPage']>('reports','GET',base+'/report-runs?limit=20&code='+reportCode+(cursor?'&cursor='+encodeURIComponent(cursor):''),undefined,undefined,signal);signal.throwIfAborted();setHistory(previous=>({...page,items:cursor?[...(previous?.items??[]),...page.items]:page.items}));});}
  function apply(view:ProfitMode=mode,zero=showZero){setStopped(false);void work(('Preparing '+title),async signal=>{await launch(generation,from,to,view,zero,view==='comparison'?selectedComparison:null,signal);setFiltersOpen(false);filterTrigger.current?.focus();});}
  function changeMode(value:string){if(busy||!definition?.run_enabled||!generation)return;const chosen=value as ProfitMode;setMode(chosen);apply(chosen);}
  function refresh(){void work('Updating accounting data',async signal=>{
    const source=await prepare(generation,signal),floor=coverage(source),start=balance?to:from;
    setGeneration(source.id);setCoverageStart(floor);setFrom(start);setVerifiedAt(source.verified_at??null);
    if((balance&&floor&&to<floor)||start>to)throw new Error('Accounting records begin on '+format.date(floor)+'. Choose a later period.');
    await launch(source.id,start,to,mode,showZero,mode==='comparison'?selectedComparison:null,signal);
  });}
  function stop(){if(!candidate||!pending(candidate))return;void work('Stopping report',async signal=>{
    await command('/report-runs/'+candidate.id+'/cancel',{},signal);setCandidate(null);setStopped(true);
  });}
  function navigatePage(direction:number){if(!run)return;const index=page+direction;if(index<0)return;
    const token=direction>0?next:cursors[index];if(direction>0&&!token)return;
    const updated=direction>0?[...cursors.slice(0,index),token]:cursors;
    void work('Loading report page',async signal=>{await readPage(run,token,index,signal);setCursors(updated);});
  }
  async function drill(row:Row,previous=false){const link=row.drilldowns?.find(item=>item.key===(balance?(previous?'balance_comparison_entries':'balance_account_entries'):(previous?'comparison_account_entries':'account_entries')));if(!run||!link||busy)return;
    await work('Opening account ledger',async signal=>{
      const child=await command<Job>('/report-runs/'+run.id+'/drilldowns',{token:link.token},signal);
      if(child.code!=='ACCOUNT_LEDGER'||!trackingId.test(child.id))throw new Error('The ledger response differs. Retry the report.');
      goTo('/reports/workspace?'+new URLSearchParams({report:'ACCOUNT_LEDGER',run:child.id}));
    });
  }
  function startDownload(job:Job){if(downloaded.current.has(job.id))return;downloaded.current.add(job.id);
    const link=document.createElement('a');link.href=reportDownloadHref(company,job.id);link.download='';document.body.append(link);try{link.click();}catch{downloaded.current.delete(job.id);}finally{link.remove();}
  }
  function exportReport(value:ReportExportFormat){if(!run||!canExport||exportBusy||busy)return;
    exportController.current?.abort();const active=new AbortController();exportController.current=active;setExportFormat(value);setExportSubmitting(true);setError('');
    void (async()=>{try{
      let job=await command<Job>('/report-runs/'+run.id+'/exports',{format:value,view:resultMode},active.signal);
      setExportJob(job);job=await trackReportExport(company,job,active.signal,setExportJob);setExportJob(job);
      if(job.status!=='COMPLETE')throw new Error(reportExportFailure(job));startDownload(job);
    }catch(value){if(!active.signal.aborted)fail(value);}finally{if(exportController.current===active)setExportSubmitting(false);}})();
  }
  if(owner!==company+':'+actor)return <p role="status">Loading this company’s {title}</p>;
  if(legacy&&run)return <div className="janso-page"><p>This completed report uses the earlier layout.</p><ReportWorkspace company={company} permissions={permissions} year={year} years={years} initialReport={reportCode} initialRun={run.id}/></div>;
  return <div className={"janso-page janso-profit-loss"+(balance?" janso-balance-sheet":"")}>
    <PageNavigation back={{href:'/reports',label:'reports'}} breadcrumbs={[{label:'Reports',href:'/reports'},{label:title}]}/>
    <header className="janso-profit-header"><div><h1>{title}</h1><p>{companyName} · {balance?'Assets, liabilities and equity':'Income, expenses, gross and net profit'}</p></div>
      {!blocked&&<div className="janso-profit-actions" role="group" aria-label={title+' actions'}>
        {canPrepare&&<Button variant="ghost" disabled={!!busy} onClick={refresh}>Refresh accounting data</Button>}
        <Button ref={filterTrigger} variant="ghost" aria-expanded={filtersOpen} aria-controls={filtersId} onClick={()=>setFiltersOpen(value=>!value)}><FilterIcon size={18}/> Filters</Button>
        {canExport&&<SplitButton label="Export format" variant="primary" primary={{...primary,label:'Export '+(exportFormat==='XLSX'?'Excel':exportFormat)}} items={exportOptions} loading={exportBusy} loadingLabel="Exporting…" disabledReason={busy?'Wait for the report to finish.':undefined} onSelect={value=>exportReport(value as ReportExportFormat)}/>}
      </div>}
    </header>
    {exportJob&&<section className="janso-profit-export" aria-label={title+' export'} role="status">{exportJob.status==='COMPLETE'?<><strong>{String(exportJob.parameters.format)} ready</strong><a className="janso-btn janso-btn--primary" href={reportDownloadHref(company,exportJob.id)} download>Download {String(exportJob.parameters.format)}</a>{canPreviewReportExport(exportJob)&&<a href={reportDownloadHref(company,exportJob.id,true)} target="_blank" rel="noopener noreferrer">Print preview</a>}</>:pending(exportJob)?<><strong>Preparing {String(exportJob.parameters.format)}…</strong><Button variant="ghost" onClick={()=>{exportController.current?.abort();void work('Cancelling export',async signal=>setExportJob(await command<Job>('/report-exports/'+exportJob.id+'/cancel',{},signal)));}}>Cancel export</Button></>:<><strong>Export {exportJob.status.toLowerCase()}</strong>{exportJob.status==='FAILED'&&<Button variant="ghost" onClick={()=>exportReport(exportJob.parameters.format as ReportExportFormat)}>Retry export</Button>}</>}</section>}
    {!blocked&&stage&&<PreparationProgress label={title+' progress'} title={stageText[0]!} detail={stageText[1]!} active={stage!=='stopped'} steps={stage==='stopped'?[]:[
      {label:'Accounting data',state:stage==='source'||stage==='preparing'?'current':'done'},
      {label:'In queue',state:stage==='QUEUED'?'current':stage==='RUNNING'?'done':'waiting'},
      {label:'Calculate',state:stage==='RUNNING'?'current':'waiting'},
    ]} action={(stage==='QUEUED'||stage==='RUNNING')&&<Button variant="ghost" className="janso-profit-stop" aria-label={"Stop "+title+" report"} onClick={stop}><svg aria-hidden="true" viewBox="0 0 16 16" width="16" height="16" fill="currentColor"><rect x="3" y="3" width="10" height="10" rx="1.5"/></svg>Stop</Button>}/>}
    {error&&<div role="alert" className="janso-profit-error"><p>{error}</p>{!blocked&&<Button variant="ghost" onClick={()=>{if(sourceRetry){refresh();return;}if(!definition||!generation)setReload(value=>value+1);else apply();}}>Retry</Button>}</div>}
    {blocked?<p role="alert">Your report access is unavailable. Reload after checking your permissions.</p>:<>
      <section id={filtersId} className="janso-profit-filters" role="region" aria-label={title+' filters'} hidden={!filtersOpen} onKeyDown={event=>{if(event.key==='Escape'){setFiltersOpen(false);filterTrigger.current?.focus();}}}>{filtersOpen&&<form ref={filterForm} onSubmit={event=>{event.preventDefault();apply();}}>
        {years.length>0&&<Select label="Financial year" value={years.find(item=>balance?item.startDate<=to&&to<=item.endDate:item.startDate===from)?.id??'custom'} options={[...years.map(item=>({value:item.id,label:item.code})),{value:'custom',label:'Custom dates'}]} onChange={value=>{const chosen=years.find(item=>item.id===value);if(chosen){setFrom(chosen.startDate);setTo(chosen.current&&today<=chosen.endDate?today:chosen.endDate);}}}/>}
        {!balance&&<TextField name="from" label="From date" type="date" value={from} onChange={event=>setFrom(event.target.value)} required/>}
        <TextField name="asOf" min={balance?coverageStart||undefined:undefined} label={balance?'As-of date':'To date'} type="date" value={to} onChange={event=>setTo(event.target.value)} required/>
        {mode==='comparison'&&<><Select name="comparisonPreset" label="Compare with" value={preset} options={balance?[{value:'YEAR_END',label:'Previous financial year end'},{value:'MONTH_END',label:'Previous month end'},{value:'LAST_YEAR',label:'Same date last year'},{value:'CUSTOM',label:'Custom date'}]:[{value:'PREVIOUS',label:'Previous period'},{value:'LAST_YEAR',label:'Same period last year'},{value:'CUSTOM',label:'Custom period'}]} onChange={value=>setPreset(value as ComparisonPreset|BalanceComparisonPreset)}/>{preset==='CUSTOM'&&<>{!balance&&<TextField label="Comparison from" type="date" value={comparisonFrom} onChange={event=>setComparisonFrom(event.target.value)} required/>}<TextField min={balance?coverageStart||undefined:undefined} label={balance?'Comparison date':'Comparison to'} type="date" value={comparisonTo} onChange={event=>setComparisonTo(event.target.value)} required/></>}</>}
        <Checkbox checked={showZero} onChange={event=>setShowZero(event.target.checked)}>Include zero accounts</Checkbox>
        <Button type="submit" disabled={!!busy||!definition?.run_enabled||!generation}>Apply filters</Button>
        {balance&&mode==='comparison'&&<p className="janso-balance-filter-note" role="note">{selectedComparison.to?'Comparison as at '+format.date(selectedComparison.to):'Choose a custom comparison date or a financial year with an available previous year end.'}</p>}
      </form>}</section>
      {coverageStart&&year?.startDate&&coverageStart>year.startDate&&<p role="note">Detailed accounting records begin on {format.date(coverageStart)}. {balance?'Earlier dates are unavailable in this accounting source.':'Earlier periods require an eligible imported YTD summary.'}</p>}
      {periodNotice&&run&&String(run.parameters.date_from)===coverageStart&&<p role="note">{periodNotice}</p>}
      {!generation&&!busy&&<p>No prepared accounting snapshot is available.{canPrepare?' Refresh accounting data to prepare one.':' Ask an administrator to prepare accounting data.'}</p>}
      <div className="janso-profit-viewbar"><SegmentedControl label={title+' view'} value={mode} disabled={!!busy||!definition?.run_enabled||!generation} options={[{value:'default',label:standardLabel},{value:'comparison',label:comparisonLabel}]} onChange={changeMode}/>{run&&<p>{balance?'As at ':resultDate(String(run.parameters.date_from))+' to '}{resultDate(String(run.parameters.date_to))}{resultMode==='comparison'&&run.parameters.comparative_to?' \u00b7 versus '+(balance?'':resultDate(String(run.parameters.comparative_from))+' to ')+resultDate(String(run.parameters.comparative_to)):''} · {display.currency}{verifiedAt&&run.generation_id===generation?' / Snapshot verified '+format.dateTime(verifiedAt):''}</p>}</div>
      {run&&(busy||error||stopped||mode!==resultMode)&&<p role="note" className="janso-profit-note">Showing the last completed report ({resultMode==='comparison'?comparisonLabel:standardLabel}). Its dates and amounts remain visible until a new report completes.</p>}
      {summary&&<div className="janso-profit-summary" aria-label={title+' totals'}>{(balance?[['ASSET','Assets'],['LIABILITY','Liabilities'],['EQUITY','Equity including earnings']]:[['TOTAL_INCOME','Income'],['TOTAL_EXPENSE','Expenses'],['GROSS_PROFIT','Gross profit'],['NET_PROFIT','Net profit']]).map(([key,label])=><div key={key} data-wide={money(summary.totals[key].current).length>18||(resultMode==='comparison'&&money(summary.totals[key].previous??'0.0000').length>18)} data-negative={(key==='GROSS_PROFIT'||key==='NET_PROFIT'||key==='EQUITY')&&summary.totals[key].current.startsWith('-')&&!/^-0\.0+$/.test(summary.totals[key].current)}><span>{label}</span><strong>{money(summary.totals[key].current)}</strong>{resultMode==='comparison'&&summary.totals[key].previous!==null&&<small>Previous {money(summary.totals[key].previous!)}</small>}</div>)}</div>}
      {(summary?.imported_ytd?.CURRENT||summary?.imported_ytd?.COMPARATIVE)&&<p role="note" className="janso-profit-note">This report includes imported year-to-date amounts. Account rows and exports identify the included amounts; earlier transaction detail is unavailable.</p>}
      {resultMode==='comparison'&&<p className="janso-profit-note">Change % uses the absolute prior amount. A dash means the prior amount was zero.</p>}
      {resultMode==='comparison'&&<p className="janso-profit-scroll-hint">Swipe horizontally to see Previous, Change and Change %.</p>}
      {balance&&resultMode==='default'&&<p className="janso-profit-scroll-hint">Scroll each statement horizontally to see large balances.</p>}
      {balance&&run&&(next||page>0)&&<p className="janso-profit-note">Detail is split across pages. Totals cover the complete report. Groups expand when you change pages.</p>}
      {balance&&summary&&<p className="janso-balance-check" role="status">Balanced: Assets equal liabilities and equity, including earnings{resultMode==='comparison'?' at both dates':''}.</p>}
      {balance&&<p className="janso-profit-note">Equity includes recorded equity and the disclosed opening, prior untransferred and current year earnings. Losses reduce equity. Section and group totals include their account detail.</p>}
      {balance&&resultMode==='default'?<div className="janso-balance-sides">{(['LIABILITIES_EQUITY','ASSETS'] as const).map(side=><section key={side}><h2>{side==='ASSETS'?'Assets':'Liabilities and equity'}</h2>
        <StatementTable currentDate={run?resultDate(String(run.parameters.date_to)):undefined} title={title+' '+(side==='ASSETS'?'assets':'liabilities and equity')} balance rows={rows.filter(row=>row.data.side===side&&!(row.data.row_kind==='TOTAL'&&(row.data.section==='ASSET'||row.data.section==='LIABILITIES_EQUITY')))} mode="default" currency={display.currency} busy={!!busy} collapsed={collapsed} money={money} onToggle={id=>setCollapsed(current=>current.includes(id)?current.filter(item=>item!==id):[...current,id])} onDrill={(item,previous)=>void drill(item,previous)}/>
        {summary&&<p className="janso-balance-side-total"><span>Total {side==='ASSETS'?'assets':'liabilities and equity'}</span><strong>{money(summary.totals[side==='ASSETS'?'ASSET':'LIABILITIES_EQUITY'].current)}</strong></p>}
      </section>)}</div>:
<StatementTable currentDate={balance&&run?resultDate(String(run.parameters.date_to)):undefined} previousDate={balance&&run?.parameters.comparative_to?resultDate(String(run.parameters.comparative_to)):undefined} title={title} balance={balance} rows={rows} mode={resultMode} currency={display.currency} busy={!!busy} collapsed={collapsed} money={money} onToggle={id=>setCollapsed(current=>current.includes(id)?current.filter(item=>item!==id):[...current,id])} onDrill={(item,previous)=>void drill(item,previous)}/>}
      {run&&<nav className="janso-profit-pages" aria-label={title+' pages'}><Button variant="ghost" disabled={!!busy||page===0} onClick={()=>navigatePage(-1)}>Previous</Button><span>Page {page+1}</span><Button variant="ghost" disabled={!!busy||!next} onClick={()=>navigatePage(1)}>Next</Button></nav>}
      <details className="janso-profit-history"><summary>Report history and source details</summary><p>{verifiedAt?"Snapshot verified "+format.dateTime(verifiedAt):"Snapshot verification time unavailable"}. New calculations refresh data older than five minutes when permitted; retained reports stay frozen.</p>{run&&<p>Report reference: {run.id} · Snapshot: {run.generation_id}</p>}<Button variant="ghost" disabled={!!busy} onClick={()=>loadHistory()}>Load history</Button>{history?.items.filter(item=>item.code===reportCode).map(item=><p key={item.id}><Button variant="ghost" disabled={!!busy||item.status!=='COMPLETE'} onClick={()=>void work('Opening completed report',async signal=>finish(await request<Job>('reports','GET',base+'/report-runs/'+item.id,undefined,undefined,signal),signal,false,true))}>{format.date(item.created_at)} · {item.status}</Button></p>)}{history?.page.next_cursor&&<Button variant="ghost" disabled={!!busy} onClick={()=>loadHistory(history.page.next_cursor)}>Older reports</Button>}</details>
    </>}
  </div>;
}
