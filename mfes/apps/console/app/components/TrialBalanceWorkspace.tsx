'use client';
import {prepareFinanceSource,financeRunFailure,financeSourceStale,FinanceSourceError} from '../lib/finance-source';

import {Fragment,useCallback,useEffect,useId,useRef,useState} from 'react';
import {Button,Checkbox,FilterIcon,PageNavigation,SegmentedControl,Select,SplitButton,TextField,businessToday,formatDate,formatMoney,resolvedDisplay,useDisplayConfig,useFormatters} from '@janso/ui';
import type {components} from '@janso/api-client/reports';
import type {FiscalYearChoice} from '../lib/company-context';
import {productFieldRequest as request,ProductFieldError} from '../lib/product-fields';
import {goTo} from '../lib/navigate';
import {trackingId} from '../lib/stock-tracking-resources';
import {ReportWorkspace} from './ReportWorkspace';
import {canPreviewReportExport,reportDownloadHref,reportExportOptions,reportExportFailure,trackReportExport,type ReportExportFormat} from '../lib/report-exports';
import {initialTrialPresentation,restoreTrial,trialAmounts,trialExpanded,type TrialBranch,type TrialLevel,type TrialMode,type TrialPage,type TrialPresentation,type TrialRow,type TrialSaved} from '../lib/trial-balance';

type S=components['schemas'];
type Job=S['JobDetail'];
type Props={company:string;companyName:string;actor:string;permissions:readonly string[];year?:FiscalYearChoice|null;years?:readonly FiscalYearChoice[];initialRun?:string};
const pending=(job:Job)=>['QUEUED','RUNNING'].includes(job.status);
const sourceCoverage=(source:S['SourceGenerationDetail'])=>{
  const control=source.manifest?.control as {coverage_start?:unknown}|undefined;
  return typeof control?.coverage_start==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(control.coverage_start)?control.coverage_start:'';
};
const levels=[{value:'HEADS',label:'Heads'},{value:'GROUPS',label:'Groups'},{value:'ALL_GROUPS',label:'All groups'},{value:'LEDGERS',label:'Ledgers'}] as const;

function pause(signal:AbortSignal){return new Promise<void>((resolve,reject)=>{
  const abort=()=>{clearTimeout(timer);reject(signal.reason);};
  const timer=setTimeout(()=>{signal.removeEventListener('abort',abort);resolve();},1500);
  signal.addEventListener('abort',abort,{once:true});
});}

/** Only expanded branches in the viewport request children; presets never fetch the whole tree. */
function BranchLoader({load,disabled,paused,columns}:{load:()=>void;disabled:boolean;paused:boolean;columns:number}) {
  const ref=useRef<HTMLTableRowElement>(null);
  useEffect(()=>{
    if(disabled||paused)return;
    if(typeof IntersectionObserver==='undefined'){load();return;}
    const observer=new IntersectionObserver(entries=>{if(entries.some(entry=>entry.isIntersecting)){observer.disconnect();load();}},{rootMargin:'100px'});
    if(ref.current)observer.observe(ref.current);
    return()=>observer.disconnect();
  },[load,disabled,paused]);
  return <tr ref={ref}><td colSpan={columns}><span role="status">{paused?'Updating hierarchy…':disabled?'Collapse a branch to view more accounts.':'Loading hierarchy…'}</span></td></tr>;
}

export function TrialBalanceWorkspace({company,companyName,actor,permissions,year,years=[],initialRun}:Props) {
  const format=useFormatters(),displayConfig=useDisplayConfig(),base='/v2/companies/'+company;
  const today=businessToday(displayConfig.timezone);
  const [from,setFrom]=useState(year?.startDate??today.slice(0,8)+'01'),[to,setTo]=useState(year?Math.min(Date.parse(today),Date.parse(year.endDate))>=Date.parse(year.startDate)?(today<year.endDate?today:year.endDate):year.endDate:today);
  const retainedSource=useRef(false);
  const [sourceRetry,setSourceRetry]=useState(false);
  const [verifiedAt,setVerifiedAt]=useState<string|null>(null);
  const [definition,setDefinition]=useState<S['DefinitionDetail']|null>(null),[generation,setGeneration]=useState(''),[coverageStart,setCoverageStart]=useState('');
  const [run,setRun]=useState<Job|null>(null),[exportJob,setExportJob]=useState<Job|null>(null);
  const [branches,setBranches]=useState<Record<string,TrialBranch>>({}),[settings,setSettings]=useState<TrialPresentation>(initialTrialPresentation);
  const [mode,setMode]=useState<TrialMode>('default'),[exportScope,setExportScope]=useState<'CURRENT'|'ALL'>('CURRENT');
  const [filtersOpen,setFiltersOpen]=useState(false),[exportFormat,setExportFormat]=useState<ReportExportFormat>('PDF');
  const [exportSubmitting,setExportSubmitting]=useState(false);
  const [runNotice,setRunNotice]=useState<'stopping'|'stopped'|null>(null);
  const filtersId=useId(),filtersTrigger=useRef<HTMLButtonElement>(null);
  const [busy,setBusy]=useState('Loading Trial Balance'),[error,setError]=useState(''),[blocked,setBlocked]=useState(false);
  const [reload,setReload]=useState(0);
  const ownership=company+':'+actor,[owner,setOwner]=useState(ownership);
  const [history,setHistory]=useState<S['JobPage']|null>(null);
  const [legacyRun,setLegacyRun]=useState<string|null>(null);
  const mainController=useRef<AbortController|null>(null),branchController=useRef(new AbortController()),exportController=useRef<AbortController|null>(null);
  const downloadedExports=useRef(new Set<string>());
  const keys=useRef(new Map<string,string>()),loading=useRef(new Set<string>()),failedBranches=useRef(new Set<string>());
  const branchesRef=useRef(branches),restore=useRef<TrialSaved|null>(null),runRef=useRef<Job|null>(null);
  const candidateRun=useRef<Job|null>(null),candidateSource=useRef<S['SourceGenerationDetail']|null>(null);
  const scroll=useRef<HTMLDivElement>(null),scrollRestore=useRef<number|null>(null);
  const canRead=permissions.includes('report.read'),canExport=permissions.includes('report.export'),canPrepare=permissions.includes('report.definition.manage');
  const storageKey='janso:trial-balance:'+company+':'+actor;
  branchesRef.current=branches;runRef.current=run;
  const summary=branches.root?.page.summary;
  const cacheRows=Object.values(branches).reduce((total,branch)=>total+branch.page.items.length,0);
  const display=run?.display?resolvedDisplay(run.display):displayConfig;
  const resultDate=(raw:string)=>formatDate(raw,display);
  const money=(raw:string)=>formatMoney(raw,display,{display:'none'});
  const residual=(values:Record<string,string>|undefined)=>columns.filter(key=>values?.[key]&&values[key]!=='0.0000').map(key=>key.replaceAll('_',' ')+' '+money(values![key])).join('; ');

  const fail=useCallback((value:unknown)=>{
    setSourceRetry(value instanceof FinanceSourceError);
    if(value instanceof ProductFieldError&&(value.status===401||value.status===403)){
      setBlocked(true);setRun(null);setBranches({});setExportJob(null);branchesRef.current={};runRef.current=null;
      branchController.current.abort();mainController.current?.abort();exportController.current?.abort();
      try{sessionStorage.removeItem(storageKey);}catch{/* Storage is optional. */}
    }
    setError(value instanceof Error?value.message:'Trial Balance is unavailable. Please retry.');
  },[storageKey]);

  const command=useCallback(async<T,>(path:string,body:unknown,signal:AbortSignal)=>{
    const payload=JSON.stringify({path,body});
    if(!keys.current.has(payload))keys.current.set(payload,crypto.randomUUID());
    const result=await request<T>('reports','POST',base+path,body,keys.current.get(payload),signal);
    keys.current.delete(payload);signal.throwIfAborted();return result;
  },[base]);

  const prepareSource=useCallback(async(baseId:string,signal:AbortSignal)=>{
    return prepareFinanceSource(base,baseId,signal,command,candidateSource,()=>setBusy('Updating accounting data'));
  },[base,command]);

  const fetchBranch=useCallback(async(job:Job,parent:string,selection:TrialPresentation,signal:AbortSignal,cursors:(string|null)[]=[null],position=0,offset=0):Promise<TrialBranch>=>{
    const query=new URLSearchParams({parent,period:selection.period??'CURRENT',show_zero:String(selection.show_zero??false),limit:'50'});
    if(cursors[position])query.set('cursor',cursors[position]!);
    let page:TrialPage;
    try{page=await request<TrialPage>('reports','GET',base+'/report-runs/'+job.id+'/hierarchy?'+query,undefined,undefined,signal);}
    catch(value){
      if(signal.aborted||!(value instanceof ProductFieldError)||value.status!==422||!query.has('cursor'))throw value;
      query.delete('cursor');cursors=[null];position=0;offset=0;
      page=await request<TrialPage>('reports','GET',base+'/report-runs/'+job.id+'/hierarchy?'+query,undefined,undefined,signal);
    }
    signal.throwIfAborted();
    return {page,cursors,position,offset};
  },[base]);

  const readBranch=useCallback(async(job:Job,parent:string,selection:TrialPresentation,signal:AbortSignal,cursors:(string|null)[]=[null],position=0,offset=0)=>{
    const branch=await fetchBranch(job,parent,selection,signal,cursors,position,offset);
    if(runRef.current?.id!==job.id)return;
    setBranches(current=>({...current,[parent]:branch}));
  },[fetchBranch]);

  const retain=useCallback(async(job:Job,signal:AbortSignal,selection:TrialPresentation=initialTrialPresentation,historical=false)=>{
    if(historical){setVerifiedAt(null);retainedSource.current=true;}
    invalidateExport();
    if(job.code==='TRIAL_BALANCE'&&job.kind==='RUN'&&job.status==='COMPLETE'&&job.version<6){
      branchController.current.abort();setBranches({});branchesRef.current={};setRun(null);runRef.current=null;
      setGeneration(job.generation_id);setFrom(String(job.parameters.date_from));setTo(String(job.parameters.date_to));setLegacyRun(job.id);return;
    }
    if(job.code!=='TRIAL_BALANCE'||job.version!==6||job.kind!=='RUN')throw new Error('Select a Trial Balance prepared with the current hierarchy. Older results remain available in Classic reports.');
    if(job.status!=='COMPLETE')throw new Error(financeRunFailure(job.failure_code,'Trial Balance'));
    const root=restore.current?.cursors.root;
    const branch=await fetchBranch(job,'root',selection,signal,root?.values,root?.position,root?.offset);
    signal.throwIfAborted();
    resetBranchRequests();
    const next={root:branch};setBranches(next);branchesRef.current=next;runRef.current=job;setRun(job);setGeneration(job.generation_id);candidateRun.current=null;setRunNotice(null);setLegacyRun(null);
    setFrom(String(job.parameters.date_from));setTo(String(job.parameters.date_to));setSettings(selection);
  },[fetchBranch]);

  const finishRun=useCallback(async(job:Job,signal:AbortSignal,recovered=false):Promise<void>=>{
    let current=job;
    candidateRun.current=job;
    while(pending(current)){
      setBusy(current.status==='QUEUED'?'Trial Balance queued':'Calculating Trial Balance');
      await pause(signal);
      current=await request<Job>('reports','GET',base+'/report-runs/'+job.id,undefined,undefined,signal);
      signal.throwIfAborted();if(current.id!==job.id)throw new Error('The report response differs. Reload Trial Balance.');
      candidateRun.current=current;
    }
    if(current.status==='BLOCKED'&&current.failure_code==='REPORT_VERIFICATION_FAILED'&&canPrepare&&!recovered){
      const requestedFrom=String(current.parameters.date_from),requestedTo=String(current.parameters.date_to);
      const source=await prepareSource(current.generation_id,signal),floor=sourceCoverage(source),start=requestedFrom;
      setGeneration(source.id);setCoverageStart(floor);setVerifiedAt(source.verified_at??null);
      if(start>requestedTo)throw new Error('Accounting records begin on '+format.date(floor)+'. Choose a period on or after that date.');
      setFrom(start);setTo(requestedTo);
      const retry=await command<Job>('/report-runs',{code:'TRIAL_BALANCE',version:6,generation_id:source.id,parameters:{date_from:start,date_to:requestedTo},view:'default'},signal);
      await finishRun(retry,signal,true);return;
    }
    await retain(current,signal);
  },[base,retain,canPrepare,prepareSource,format,command]);

  const ready=useCallback(async(signal:AbortSignal)=>{
    let cursor:string|null=null;
    for(let i=0;i<20;i++){
      const page:S['ResourcePage']=await request('reports','GET',base+'/report-generations?limit=50'+(cursor?'&cursor='+encodeURIComponent(cursor):''),undefined,undefined,signal);
      const found=page.items.find(item=>item.status==='READY');
      if(found){const source=await request<S['SourceGenerationDetail']>('reports','GET',base+'/report-generations/'+found.id,undefined,undefined,signal);if(source.id!==found.id||source.status!=='READY')throw new Error('The selected accounting snapshot changed. Retry the report.');return source;}
      cursor=page.page.next_cursor;if(!cursor)break;
    }
    return null;
  },[base]);

  const work=useCallback(async(label:string,action:(signal:AbortSignal)=>Promise<void>)=>{
    mainController.current?.abort();const controller=new AbortController();mainController.current=controller;
    setBusy(label);setError('');
    try{await action(controller.signal);}catch(value){if(!controller.signal.aborted)fail(value);}
    finally{if(mainController.current===controller)setBusy('');}
  },[fail]);

  useEffect(()=>{
    retainedSource.current=false;setOwner(ownership);setHistory(null);setExportScope('CURRENT');setExportFormat('PDF');setFiltersOpen(false);setExportSubmitting(false);setLegacyRun(null);
    setRun(null);setBranches({});setDefinition(null);setBlocked(false);keys.current.clear();restore.current=null;runRef.current=null;candidateRun.current=null;candidateSource.current=null;
    setMode('default');setSettings(initialTrialPresentation);setExportJob(null);downloadedExports.current.clear();setRunNotice(null);setGeneration('');setCoverageStart('');
    if(!canRead){setBlocked(true);setBusy('');return;}
    void work('Loading Trial Balance',async signal=>{
      const found=await request<S['DefinitionDetail']>('reports','GET',base+'/report-definitions/TRIAL_BALANCE',undefined,undefined,signal);
      signal.throwIfAborted();setDefinition({...found,run_enabled:found.run_enabled&&found.definition.version===6});
      if(initialRun){
        try{restore.current=restoreTrial(sessionStorage.getItem(storageKey),initialRun);}catch{/* Storage is optional. */}
        const saved=restore.current;
        if(saved){setMode(saved.mode);scrollRestore.current=saved.scroll;}
        const retained=await request<Job>('reports','GET',base+'/report-runs/'+initialRun,undefined,undefined,signal);
        if(retained.status==='COMPLETE')await retain(retained,signal,saved?.settings??initialTrialPresentation,true);
        else await finishRun(retained,signal);
        return;
      }
      let source=await ready(signal);
      if((!source||financeSourceStale(source.verified_at))&&canPrepare&&found.run_enabled&&found.definition.version===6)source=await prepareSource(source?.id??'',signal);
      setVerifiedAt(source?.verified_at??null);
      signal.throwIfAborted();setGeneration(source?.id??'');
      const floor=source?sourceCoverage(source):'',start=floor&&from<floor?floor:from;setCoverageStart(floor);
      if(start>to){setFiltersOpen(true);throw new Error('Accounting records begin on '+format.date(floor)+'. Choose a period on or after that date.');}
      if(start!==from)setFrom(start);
      if(source&&found.run_enabled&&found.definition.version===6){const created=await command<Job>('/report-runs',{code:'TRIAL_BALANCE',version:6,generation_id:source.id,parameters:{date_from:start,date_to:to},view:'default'},signal);await finishRun(created,signal);}
    });
    return()=>{mainController.current?.abort();branchController.current.abort();exportController.current?.abort();};
  },[base,actor,canRead,permissions.join('|'),initialRun,reload]);

  const selectedYear=useRef(year?.id);
  useEffect(()=>{
    if(selectedYear.current===year?.id)return;selectedYear.current=year?.id;
    if(year){setFrom(year.startDate);setTo(year.current&&today>=year.startDate&&today<=year.endDate?today:year.endDate);}
  },[year?.id,year?.startDate,year?.endDate,today]);

  useEffect(()=>{
    if(scrollRestore.current===null||!branches.root)return;
    if(scroll.current)scroll.current.scrollTop=scrollRestore.current;
    scrollRestore.current=null;
  },[branches]);

  function remember(){
    if(!run)return;
    const cursors=Object.fromEntries(Object.entries(branchesRef.current).slice(0,20).map(([key,entry])=>[key,{values:entry.cursors,position:entry.position,offset:entry.offset}]));
    const saved={run:run.id,mode,settings,scroll:scroll.current?.scrollTop??0,cursors};
    let text=JSON.stringify(saved);if(text.length>180_000)text=JSON.stringify({...saved,cursors:{}});
    try{sessionStorage.setItem(storageKey,text);}catch{/* Storage is optional. */}
  }
  function trimCollapsed(next:TrialPresentation){
    resetBranchRequests();
    setBranches(current=>{
      const visible=new Set<string>(['root']),stack=[...(current.root?.page.items??[])];
      for(let i=0;i<stack.length&&i<1000;i++){const row=stack[i];if(trialExpanded(row.data,next)){visible.add(row.data.node_key);stack.push(...(current[row.data.node_key]?.page.items??[]));}}
      const kept=Object.fromEntries(Object.entries(current).filter(([key])=>visible.has(key)));branchesRef.current=kept;return kept;
    });
  }
  function resetBranchRequests(){
    branchController.current.abort();branchController.current=new AbortController();loading.current.clear();failedBranches.current.clear();
  }
  function changeLevel(level:TrialLevel){const next={...settings,level,expanded:[],collapsed:[]};setSettings(next);trimCollapsed(next);}
  function loadHistory(cursor?:string|null){void work('Loading report history',async signal=>setHistory(await request('reports','GET',base+'/report-runs?limit=20&code=TRIAL_BALANCE'+(cursor?'&cursor='+encodeURIComponent(cursor):''),undefined,undefined,signal)));}
  function toggle(row:TrialRow){
    const key=row.data.node_key,isOpen=trialExpanded(row.data,settings);
    if((settings.expanded?.length??0)+(settings.collapsed?.length??0)>=2000){setError('Reset the hierarchy level to change more branches.');return;}
    const next={...settings,expanded:[...(settings.expanded??[]).filter(item=>item!==key),...(!isOpen?[key]:[])],collapsed:[...(settings.collapsed??[]).filter(item=>item!==key),...(isOpen?[key]:[])]};
    setSettings(next);if(isOpen)trimCollapsed(next);
  }
  async function loadChildren(parent:string){
    if(!run||blocked||busy||branchesRef.current[parent]||loading.current.has(parent)||failedBranches.current.has(parent))return;
    if(Object.values(branchesRef.current).reduce((total,branch)=>total+branch.page.items.length,0)+loading.current.size*50+50>1000)return;
    loading.current.add(parent);const signal=branchController.current.signal;
    try{const saved=restore.current?.cursors[parent];await readBranch(run,parent,settings,signal,saved?.values,saved?.position,saved?.offset);}
    catch(value){if(!signal.aborted){failedBranches.current.add(parent);fail(value);}}
    finally{if(branchController.current.signal===signal)loading.current.delete(parent);}
  }
  function invalidateExport(){exportController.current?.abort();setExportJob(null);setExportSubmitting(false);}
  useEffect(()=>{invalidateExport();},[run?.id,mode,settings,exportScope]);
  function apply(){if(!definition?.run_enabled||!generation||from>to)return;
    if(coverageStart&&from<coverageStart){setFiltersOpen(true);setError('Accounting records begin on '+format.date(coverageStart)+'. Choose a From date on or after that date.');return;}
    restore.current=null;setRunNotice(null);invalidateExport();
    void work('Preparing Trial Balance',async signal=>{
      const known=candidateRun.current;
      if(known&&pending(known)&&known.parameters.date_from===from&&known.parameters.date_to===to){await finishRun(known,signal);return;}
      if(known?.status==='FAILED'&&known.parameters.date_from===from&&known.parameters.date_to===to){await finishRun(await command<Job>('/report-runs/'+known.id+'/retry',{},signal),signal);return;}
      let sourceId=generation;
      if(canPrepare&&(retainedSource.current||financeSourceStale(verifiedAt))){const fresh=await prepareSource(generation,signal);retainedSource.current=false;sourceId=fresh.id;setGeneration(sourceId);setCoverageStart(sourceCoverage(fresh));setVerifiedAt(fresh.verified_at??null);}
      const created=await command<Job>('/report-runs',{code:'TRIAL_BALANCE',version:6,generation_id:sourceId,parameters:{date_from:from,date_to:to},view:'default'},signal);await finishRun(created,signal);
    });
  }
  function changePresentation(next:TrialPresentation){
    invalidateExport();
    restore.current=null;resetBranchRequests();
    if(!run){setSettings(next);return;}
    void work('Loading hierarchy',async signal=>{
      const query=new URLSearchParams({parent:'root',period:next.period??'CURRENT',show_zero:String(next.show_zero??false),limit:'50'});
      const page=await request<TrialPage>('reports','GET',base+'/report-runs/'+run.id+'/hierarchy?'+query,undefined,undefined,signal);
      signal.throwIfAborted();resetBranchRequests();const fresh={root:{page,cursors:[null],position:0,offset:0}};setBranches(fresh);branchesRef.current=fresh;setSettings(next);
    });
  }
  function nextPage(parent:string,direction:number){
    if(!run)return;const branch=branches[parent];let cursors=branch.cursors,position=branch.position+direction,offset=branch.offset;
    if(direction>0&&branch.page.page.next_cursor){cursors=[...cursors.slice(0,position),branch.page.page.next_cursor];}
    if(direction===0){cursors=[null];position=0;offset=0;}
    if(cursors.length>100){cursors=cursors.slice(-100);position-=1;offset+=1;}
    if(position<0||position>=cursors.length)return;
    const descendants=new Set<string>(),queue=[...(branch.page.items??[])];
    for(let i=0;i<queue.length;i++){const key=queue[i].data.node_key;descendants.add(key);queue.push(...(branches[key]?.page.items??[]));}
    resetBranchRequests();
    void work('Loading next branch page',async signal=>{await readBranch(run,parent,settings,signal,cursors,position,offset);setBranches(current=>Object.fromEntries(Object.entries(current).filter(([key])=>!descendants.has(key))));});
  }
  async function drill(row:TrialRow){
    const link=row.drilldowns?.find(link=>link.key!=='row_detail');
    if(!run||!link)return;remember();
    await work('Opening account ledger',async signal=>{
      let child:Job;
      try{child=await command<Job>('/report-runs/'+run.id+'/drilldowns',{token:link.token},signal);}
      catch(value){
        if(signal.aborted||!(value instanceof ProductFieldError)||value.status!==422)throw value;
        const parent=row.data.parent_key??'root',branch=branches[parent];
        await readBranch(run,parent,settings,signal,branch?.cursors,branch?.position,branch?.offset);
        throw new Error('Ledger link refreshed. Open the account again.');
      }
      if(child.kind!=='RUN'||child.code!=='ACCOUNT_LEDGER'||!trackingId.test(child.id))throw new Error('The ledger response differs. Refresh Trial Balance and try again.');
      const query=new URLSearchParams({report:'ACCOUNT_LEDGER',run:child.id,trial_balance_run:run.id});
      goTo('/reports/workspace?'+query);
    });
  }
  async function exportReport(value:ReportExportFormat){
    if(!run||!canExport||blocked||exportSubmitting)return;
    exportController.current?.abort();const controller=new AbortController();exportController.current=controller;setError('');setExportSubmitting(true);
    try{
      let job=await command<Job>('/report-runs/'+run.id+'/exports',{format:value,view:mode,trial_balance:{...settings,hierarchy:exportScope}},controller.signal);
      controller.signal.throwIfAborted();setExportJob(job);job=await trackReportExport(company,job,controller.signal,value=>{if(!controller.signal.aborted)setExportJob(value);});
      controller.signal.throwIfAborted();
      if(job.status!=='COMPLETE')throw new Error(reportExportFailure(job));
      startDownload(job);
    }catch(value){if(!controller.signal.aborted)fail(value);}
    finally{if(exportController.current===controller)setExportSubmitting(false);}
  }
  function startDownload(job:Job){
    if(downloadedExports.current.has(job.id))return;
    downloadedExports.current.add(job.id);
    const link=document.createElement('a');
    link.href=reportDownloadHref(company,job.id);
    link.download='';
    document.body.append(link);
    try{link.click();}catch{downloadedExports.current.delete(job.id);}finally{link.remove();}
  }
  function refreshSource(){invalidateExport();void work('Refreshing accounting data',async signal=>{
    setRunNotice(null);
    const source=await prepareSource(generation,signal),floor=sourceCoverage(source),start=from;
    setGeneration(source.id);setCoverageStart(floor);setVerifiedAt(source.verified_at??null);
    if(start>to)throw new Error('Accounting records begin on '+format.date(floor)+'. Choose a period on or after that date.');
    if(start!==from)setFrom(start);
    const created=await command<Job>('/report-runs',{code:'TRIAL_BALANCE',version:6,generation_id:source.id,parameters:{date_from:start,date_to:to},view:'default'},signal);await finishRun(created,signal);
  });}
  function stopReport(){
    const id=candidateRun.current?.id;
    if(!id||runNotice==='stopping')return;
    setRunNotice('stopping');
    void work('Stopping Trial Balance',async signal=>{
      try{await command('/report-runs/'+id+'/cancel',{},signal);candidateRun.current=null;setRunNotice('stopped');}
      catch(value){setRunNotice(null);throw value;}
    });
  }
  const columns=mode==='default'?trialAmounts.slice(4):trialAmounts;
  const exportOptions=reportExportOptions({run,limits:definition?.export_limits,view:mode,formats:['PDF','XLSX','CSV','HTML']});
  const primaryExport=exportOptions.find(option=>option.id===exportFormat)!;
  const exportBusy=exportSubmitting||!!exportJob&&pending(exportJob);
  const reportStage=runNotice??(candidateRun.current&&pending(candidateRun.current)&&busy?candidateRun.current.status:busy==='Updating accounting data'||busy==='Refreshing accounting data'?'source':busy==='Loading Trial Balance'||busy==='Preparing Trial Balance'?'preparing':null);
  const reportProgress=reportStage==='stopping'?{title:'Stopping report',detail:'Sending the stop request.'}:reportStage==='stopped'?{title:'Report stopped',detail:'Apply the period to run it again.'}:reportStage==='QUEUED'?{title:'Report queued',detail:'Waiting for a report worker.'}:reportStage==='RUNNING'?{title:'Calculating report',detail:'Building the Trial Balance.'}:reportStage==='source'?{title:'Preparing accounting data',detail:'Verifying the accounting snapshot.'}:{title:'Preparing Trial Balance',detail:'Checking report settings.'};
  const completedFormat=exportJob?.parameters?.format??exportFormat;
  const exportName=completedFormat==='XLSX'?'Excel':completedFormat==='PDF'||completedFormat==='CSV'||completedFormat==='HTML'?completedFormat:'export';
  const visible:({type:'row';row:TrialRow}|{type:'branch';parent:string})[]=[];
  const stack:({type:'row';row:TrialRow}|{type:'branch';parent:string})[]=[{type:'branch',parent:'root'}];
  while(stack.length&&visible.length<1200){
    const item=stack.pop()!;
    if(item.type==='branch'){
      const branch=branches[item.parent];
      if(branch){visible.push(item);for(let i=branch.page.items.length-1;i>=0;i--)stack.push({type:'row',row:branch.page.items[i]});}
      else visible.push(item);
    }else{visible.push(item);if(trialExpanded(item.row.data,settings))stack.push({type:'branch',parent:item.row.data.node_key});}
  }
  if(owner!==ownership)return <p role="status">Loading this company’s Trial Balance</p>;
  if(legacyRun&&!blocked&&canRead)return <div className="janso-page"><p>This completed report uses the earlier layout.</p>{error&&<p role="alert">{error}</p>}{busy&&<p role="status">{busy}</p>}<Button disabled={!!busy||!definition?.run_enabled} onClick={apply}>Prepare current Trial Balance</Button><ReportWorkspace company={company} permissions={permissions} year={year} years={years} initialReport="TRIAL_BALANCE" initialRun={legacyRun}/></div>;
  return <div className="janso-page janso-trial-balance">
    <PageNavigation back={{href:'/reports',label:'reports'}} breadcrumbs={[{label:'Reports',href:'/reports'},{label:'Trial Balance'}]}/>
    <header className="janso-report-header"><div className="janso-trial-heading"><h1>Trial Balance</h1><p>{companyName} · Opening, posted movement and closing balances</p></div>
      {!blocked&&canRead&&<div className="janso-trial-actions" role="group" aria-label="Trial Balance actions">
        {canPrepare&&<Button variant="ghost" disabled={!!busy||!definition?.run_enabled} onClick={refreshSource}>Refresh accounting data</Button>}
        <Button ref={filtersTrigger} type="button" variant="ghost" className="janso-trial-filter-toggle" aria-expanded={filtersOpen} aria-controls={filtersId} onClick={()=>setFiltersOpen(value=>!value)}><FilterIcon size={18}/>Filter</Button>
        {canExport&&<>
          <Select label="Export hierarchy" hideLabel value={exportScope} disabled={exportBusy} options={[{value:'CURRENT',label:'Current hierarchy'},{value:'ALL',label:'All ledgers'}]} onChange={value=>setExportScope(value as 'CURRENT'|'ALL')}/>
          <SplitButton label="Export format" variant="primary" primary={{...primaryExport,label:'Export '+(exportFormat==='XLSX'?'Excel':exportFormat)}} items={exportOptions} disabledReason={busy?'Wait for the report update to finish.':undefined} loading={exportBusy} loadingLabel="Exporting…" onSelect={value=>{setExportFormat(value as ReportExportFormat);void exportReport(value as ReportExportFormat);}}/>
          {exportJob&&<section className="janso-trial-export-status" aria-label="Trial Balance exports">
            <p role="status">{exportJob.status==='COMPLETE'?<>{exportName} ready. <a className="janso-btn janso-btn--primary" href={reportDownloadHref(company,exportJob.id)} download>Download {exportName}</a>{canPreviewReportExport(exportJob)&&<a href={reportDownloadHref(company,exportJob.id,true)} target="_blank" rel="noopener noreferrer">Print preview</a>}</>:pending(exportJob)?<>Preparing {exportName}… <Button variant="ghost" onClick={()=>void work('Refreshing export status',async signal=>{exportController.current=mainController.current;const updated=await request<Job>('reports','GET',base+'/report-exports/'+exportJob.id,undefined,undefined,signal);signal.throwIfAborted();setExportJob(updated);if(updated.status==='COMPLETE')startDownload(updated);})}>Refresh export status</Button><Button variant="ghost" onClick={()=>{exportController.current?.abort();void work('Cancelling export',async signal=>setExportJob(await command<Job>('/report-exports/'+exportJob.id+'/cancel',{},signal)));}}>Cancel export</Button></>:<>Export {exportJob.status.toLowerCase()}. {exportJob.status==='FAILED'&&<Button variant="ghost" onClick={()=>void work('Retrying export',async signal=>{exportController.current=mainController.current;const retried=await command<Job>('/report-exports/'+exportJob.id+'/retry',{},signal);setExportJob(retried);const completed=await trackReportExport(company,retried,signal,value=>{if(!signal.aborted)setExportJob(value);});signal.throwIfAborted();setExportJob(completed);if(completed.status==='COMPLETE')startDownload(completed);})}>Retry export</Button>}</>}</p>
          </section>}
        </>}
      </div>}
    </header>
    {!blocked&&canRead&&reportStage&&<section className="janso-trial-progress" data-stage={reportStage} role="region" aria-label="Trial Balance progress">
      <div className="janso-trial-progress__message" role="status"><strong>{reportProgress.title}</strong><span>{reportProgress.detail}</span></div>
      {reportStage!=='stopped'&&<div className="janso-trial-progress__meter"><div className="janso-trial-progress__track" role="progressbar" aria-label="Trial Balance preparation"><span/></div><ol className="janso-trial-progress__steps" aria-label="Report stages"><li data-state={reportStage==='source'||reportStage==='preparing'?'current':'done'}>Accounting data</li><li data-state={reportStage==='QUEUED'?'current':reportStage==='RUNNING'?'done':'waiting'}>In queue</li><li data-state={reportStage==='RUNNING'?'current':'waiting'}>Calculate</li></ol></div>}
      {(reportStage==='QUEUED'||reportStage==='RUNNING'||reportStage==='stopping')&&<Button type="button" variant="ghost" className="janso-trial-progress__stop" disabled={reportStage==='stopping'} aria-label="Stop Trial Balance report" onClick={stopReport}><svg aria-hidden="true" viewBox="0 0 16 16" width="16" height="16" fill="currentColor"><rect x="3" y="3" width="10" height="10" rx="1.5"/></svg>{reportStage==='stopping'?'Stopping…':'Stop'}</Button>}
    </section>}
    {coverageStart&&year?.startDate&&coverageStart>year.startDate&&<p role="note">Accounting records begin on {format.date(coverageStart)}. This Trial Balance starts there; earlier dates in the financial year are unavailable.</p>}
    {error&&<div role="alert"><p>{error}</p>{!blocked&&<Button variant="ghost" onClick={()=>{if(sourceRetry){refreshSource();return;}failedBranches.current.clear();setBranches(current=>({...current}));if(!run){if(!definition||!generation)setReload(value=>value+1);else apply();}else setError('');}}>Retry</Button>}</div>}
    {blocked||!canRead?<p role="alert">Your report access is unavailable. Reload after checking your permissions.</p>:<>
      <section id={filtersId} className="janso-trial-filters" role="region" aria-label="Trial Balance filters" hidden={!filtersOpen} onKeyDown={event=>{if(event.key==='Escape'&&!event.defaultPrevented){event.preventDefault();setFiltersOpen(false);filtersTrigger.current?.focus();}}}>{filtersOpen&&<>
        <form className="janso-trial-controls janso-trial-period" onSubmit={event=>{event.preventDefault();apply();}}>
          {years.length>0&&<Select label="Financial year" disabled={!!busy} value={years.find(item=>item.startDate===from)?.id??'custom'} options={[...years.map(item=>({value:item.id,label:item.code})),{value:'custom',label:'Custom dates'}]} onChange={value=>{const chosen=years.find(item=>item.id===value);if(chosen){setFrom(chosen.startDate);setTo(chosen.current&&today>=chosen.startDate&&today<=chosen.endDate?today:chosen.endDate);}}}/>}
          <TextField label="From date" type="date" disabled={!!busy} value={from} onChange={event=>setFrom(event.target.value)} required/>
          <TextField label="To date" type="date" disabled={!!busy} value={to} onChange={event=>setTo(event.target.value)} required/>
          <Button type="submit" disabled={!!busy||!definition?.run_enabled||!generation||!from||!to||from>to}>Apply period</Button>
        </form>
        {from>to&&<p role="alert">From date must be on or before To date.</p>}
        <div className="janso-trial-controls janso-trial-presentation">
          <Select label="Expand hierarchy" inline disabled={!!busy} value={settings.level??'GROUPS'} options={levels} onChange={value=>changeLevel(value as TrialLevel)}/>
          {(branches.root?.page.periods.length??0)>1&&<Select label="Statement period" inline disabled={!!busy} value={settings.period??'CURRENT'} options={[{value:'CURRENT',label:'Current period'},{value:'COMPARATIVE',label:'Comparative period'}]} onChange={value=>changePresentation({...settings,period:value as 'CURRENT'|'COMPARATIVE'})}/>}
          <Checkbox disabled={!!busy} checked={settings.show_zero??false} onChange={event=>changePresentation({...settings,show_zero:event.target.checked})}>Show zero rows</Checkbox>
        </div>
      </>}</section>
      {busy&&!reportStage&&<p role="status">{busy}</p>}
      {definition&&!definition.run_enabled&&<p>New report preparation is unavailable. Open a completed report from history.</p>}
      {definition&&!generation&&!busy&&<p>No prepared accounting snapshot is available.{canPrepare?' Refresh accounting data to prepare one.':' Ask an administrator to prepare accounting data.'}</p>}
      <div className="janso-trial-viewbar">
        <SegmentedControl label="Trial Balance layout" value={mode} options={[{value:'default',label:'Closing balances'},{value:'detailed',label:'Opening and movement'}]} onChange={setMode}/>
        {run&&<div className="janso-trial-meta"><p>{resultDate(String(run.parameters.date_from))} to {resultDate(String(run.parameters.date_to))} · {display.currency} · {summary?.account_count??'…'} accounts{verifiedAt&&run.generation_id===generation?' / Snapshot verified '+format.dateTime(verifiedAt):''}</p>
          {summary&&<p className="janso-trial-balance-check" role="status">Balanced · Difference {money(summary.closing_difference)} {display.currency}</p>}
        </div>}
      </div>
      {summary&&residual(summary.display_residual)&&<p role="note">Display rounding: grand totals minus rounded ledger sums — {residual(summary.display_residual)} {display.currency}. Exact balances remain reconciled.</p>}
      <p className="janso-trial-scroll-hint" data-layout={mode}>Scroll horizontally to view all balance columns.</p>
      <div ref={scroll} className="janso-trial-scroll" role="region" aria-label="Trial Balance accounts" aria-busy={!!busy} tabIndex={0} onScroll={remember}>
        <table className="janso-trial-table" data-layout={mode}><caption className="janso-visually-hidden">Trial Balance, {mode==='default'?'closing balances':'opening and movement'}, {display.currency}. Parent rows summarize descendant accounts. Grand totals count each account once.</caption>
          <thead>{mode==='detailed'?<><tr><th rowSpan={2} scope="col">Account / group</th><th colSpan={2} scope="colgroup">Opening balance</th><th colSpan={2} scope="colgroup">Period movement</th><th colSpan={2} scope="colgroup">Closing balance</th></tr><tr>{columns.map(key=><th scope="col" key={key}>{key.endsWith('debit')?'Debit':'Credit'}</th>)}</tr></>:<tr><th scope="col">Account / group</th><th scope="col">Debit</th><th scope="col">Credit</th></tr>}</thead>
          <tbody>{visible.map(item=>item.type==='row'?<tr key={item.row.data.node_key} data-kind={item.row.data.row_kind}>
            <th scope="row"><span className="janso-trial-label"><span aria-hidden="true" className="janso-trial-indent">{'│ '.repeat(Math.min(item.row.data.depth,30))}</span>
              {item.row.data.child_count>0?<button type="button" className="janso-trial-disclosure" disabled={!!busy} aria-expanded={trialExpanded(item.row.data,settings)} aria-label={(trialExpanded(item.row.data,settings)?'Collapse ':'Expand ')+item.row.data.name} onClick={()=>toggle(item.row)}>{trialExpanded(item.row.data,settings)?'▾':'▸'}</button>:<span aria-hidden="true">· </span>}
              {item.row.data.row_kind==='ACCOUNT'&&item.row.drilldowns?.some(link=>link.key!=='row_detail')?<button type="button" className="janso-trial-account" disabled={!!busy} onClick={()=>void drill(item.row)}>{item.row.data.name}</button>:<span>{item.row.data.name}</span>}
              <small>{item.row.data.code}</small>{residual(item.row.data.display_residual)&&<small>Display rounding: total minus rounded ledger sum — {residual(item.row.data.display_residual)}</small>}</span></th>{columns.map(key=><td key={key} className="janso-figure" title={'Exact amount: '+item.row.data[key]}>{money(item.row.data[key])}</td>)}
          </tr>:branches[item.parent]?<Fragment key={'page:'+item.parent}>{(branches[item.parent].offset>0||branches[item.parent].position>0||branches[item.parent].page.page.has_more)&&<tr><td colSpan={columns.length+1}><div className="janso-report-actions" aria-label={'Pages for '+item.parent}><Button variant="ghost" disabled={!!busy||branches[item.parent].position===0} onClick={()=>nextPage(item.parent,-1)}>Previous accounts</Button>{branches[item.parent].offset>0&&<Button variant="ghost" disabled={!!busy} onClick={()=>nextPage(item.parent,0)}>First accounts</Button>}<span>Page {branches[item.parent].position+branches[item.parent].offset+1}</span><Button variant="ghost" disabled={!!busy||!branches[item.parent].page.page.has_more} onClick={()=>nextPage(item.parent,1)}>Next accounts</Button></div></td></tr>}</Fragment>:run&&item.parent!=='root'?<BranchLoader key={'load:'+item.parent} columns={columns.length+1} paused={!!busy} disabled={cacheRows+loading.current.size*50+50>1000||failedBranches.current.has(item.parent)} load={()=>void loadChildren(item.parent)}/>:null)}</tbody>
          {summary&&<tfoot><tr><th scope="row">Grand total</th>{columns.map(key=><td className="janso-figure" key={key} title={'Exact amount: '+summary[key]}>{money(summary[key])}</td>)}</tr></tfoot>}
        </table>
        {summary&&summary.account_count===0&&<p>No accounts are present in this prepared snapshot.</p>}
      </div>
      <details className="janso-trial-history"><summary>Report history and source details</summary><p>{verifiedAt?"Snapshot verified "+format.dateTime(verifiedAt):"Snapshot verification time unavailable"}. New calculations refresh data older than five minutes when permitted; retained reports stay frozen.</p><p>{run?'Prepared from a verified accounting snapshot.':'Prepare a report to review its accounting source.'}</p>{run&&<p>Report reference: {run.id} · Snapshot: {run.generation_id}</p>}<Button variant="ghost" disabled={!!busy} onClick={()=>loadHistory()}>Load history</Button>{history?.items.filter(item=>item.code==='TRIAL_BALANCE').map(item=><p key={item.id}><Button variant="ghost" onClick={()=>void work('Opening completed report',async signal=>retain(await request('reports','GET',base+'/report-runs/'+item.id,undefined,undefined,signal),signal,undefined,true))} disabled={item.status!=='COMPLETE'}>{format.date(item.created_at)} · {item.status}</Button></p>)}{history?.page.next_cursor&&<Button variant="ghost" disabled={!!busy} onClick={()=>loadHistory(history.page.next_cursor)}>Older reports</Button>}</details>
    </>}
  </div>;
}
