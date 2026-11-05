'use client';
import {useRef,useState} from 'react';
import {Button,SearchSelect,Select,TextField,useFormatters} from '@janso/ui';
import type {components} from '@janso/api-client/reports';
import {productFieldRequest as request} from '../lib/product-fields';
import {sessionFetch} from '../lib/session-fetch';
import {lookup,type Native} from '../lib/voucher-fields';
import {BankingHistory} from './BankingHistory';
import {BankReconciliation} from './BankReconciliation';
import type {FiscalYearChoice} from '../lib/company-context';
import {ReportYearRange,useReportYearDates} from './ReportYearRange';
import {reportRowLabel} from '../lib/report-labels';
type Run=components['schemas']['RunDetail'];
type Definition=components['schemas']['Definition'];
export function FinancialReports({company,permissions,year,years=[]}:{company:string;permissions:readonly string[];year?:FiscalYearChoice|null;years?:readonly FiscalYearChoice[]}){
  const range=useReportYearDates(company,year,years),start=range.from,end=range.to;
  const format=useFormatters(),base='/v1/companies/'+company;
  const [definitions,setDefinitions]=useState<Definition[]>([]),[code,setCode]=useState(''),[schema,setSchema]=useState<Native|null>(null);
  const [generations,setGenerations]=useState<{id:string;status:string}[]>([]),[generation,setGeneration]=useState('');
  const [account,setAccount]=useState(''),[statement,setStatement]=useState('');
  const [bankSession,setBankSession]=useState('');
  const [group,setGroup]=useState(''),[party,setParty]=useState(''),[role,setRole]=useState('');
  const [basis,setBasis]=useState('BASE'),[currency,setCurrency]=useState(''),[grain,setGrain]=useState('DAY');
  const [comparativeFrom,setComparativeFrom]=useState(''),[comparativeTo,setComparativeTo]=useState('');
  const [dateBasis,setDateBasis]=useState('POSTING');
  const [run,setRun]=useState<Run|null>(null),[rows,setRows]=useState<components['schemas']['RowItem'][]>([]),[cursor,setCursor]=useState<string|null>(null);
  const [busy,setBusy]=useState(false),[message,setMessage]=useState('');
  const retry=useRef<{payload:string;key:string}|null>(null);
  const allowed=(name:string)=>permissions.includes(name);
  async function act(work:()=>Promise<void>){setBusy(true);setMessage('');try{await work();}catch(error){setMessage(error instanceof Error?error.message:'Unable to load report');}finally{setBusy(false);}}
  async function create<T>(path:string,body:unknown){const payload=JSON.stringify({path,body});if(retry.current?.payload!==payload)retry.current={payload,key:crypto.randomUUID()};const value=await request<T>('reports','POST',base+path,body,retry.current.key);retry.current=null;return value;}
  async function loadRows(identity:string,next:string|null){const page=await request<components['schemas']['RowPage']>('reports','GET',base+'/report-runs/'+identity+'/rows?limit=50'+(next?'&cursor='+encodeURIComponent(next):''));setRows(previous=>next?[...previous,...page.items]:page.items);setCursor(page.page.next_cursor);}
  async function download(){if(!run?.download_token)return;const response=await sessionFetch('/api/product-fields',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({service:'reports',method:'GET',path:base+'/report-runs/'+run.id+'/download?token='+encodeURIComponent(run.download_token)})});if(!response.ok)throw new Error('Report download unavailable. Refresh the report and retry.');const url=URL.createObjectURL(await response.blob());try{const link=document.createElement('a');link.href=url;link.download='financial-report.csv';link.click();}finally{URL.revokeObjectURL(url);}}
  const selected=definitions.find(row=>row.code===code),fields=schema?.properties??{};
  const columns=[...new Set(rows.flatMap(row=>Object.keys(row.data)))];
  function cell(key:string,value:unknown,row:Record<string,unknown>){if(value==null)return '';if(key==='row_kind'&&typeof value==='string')return reportRowLabel(value);if(typeof value==='string'&&/^-?\d+\.\d{4}$/.test(value))return format.money(value,{display:'none'})+(typeof row.currency==='string'?' '+row.currency:'');if(typeof value==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(value))return format.date(value);return typeof value==='object'?JSON.stringify(value):String(value);}
  return <section aria-label="Financial reports"><h1>Financial reports</h1>
    <Button disabled={busy} onClick={()=>void act(async()=>{const data=await request<Definition[]>('reports','GET',base+'/report-definitions');setDefinitions(data);const page=await request<{items:{id:string;status:string}[]}>('reports','GET',base+'/report-generations?limit=50');setGenerations(page.items);})}>Load reports</Button>
    {allowed('report.definition.manage')&&<Button disabled={busy} onClick={()=>void act(async()=>{const value=await create<components['schemas']['GenerationDetail']>('/report-generations',{});setMessage('Report source refresh requested: '+value.id);})}>Refresh report sources</Button>}
    <Select label="Report" value={code} options={definitions.filter(row=>!['BANK_RECONCILIATION_EVIDENCE','BANK_RECONCILIATION_WORKLIST'].includes(row.code)||allowed('accounting.statement.read')).map(row=>({value:row.code,label:row.code==='BANK_RECONCILIATION'?'Bank balance agreement (manual)':row.code.replaceAll('_',' ')}))} disabled={busy} onChange={value=>{setCode(value);setSchema(null);setRun(null);setRows([]);setAccount('');setGroup('');setParty('');setRole('');setBasis(['BANK_RECONCILIATION_EVIDENCE','BANK_RECONCILIATION_WORKLIST'].includes(value)?'TRANSACTION':'BASE');setCurrency(['BANK_RECONCILIATION_EVIDENCE','BANK_RECONCILIATION_WORKLIST'].includes(value)?'INR':'');setBankSession('');setGrain('DAY');setComparativeFrom('');setComparativeTo('');setDateBasis('POSTING');}}/>
    <Select label="Source snapshot" value={generation} options={generations.filter(row=>row.status==='READY').map(row=>({value:row.id,label:row.id}))} disabled={busy} onChange={setGeneration}/>
    <Button disabled={busy||!code} onClick={()=>void act(async()=>{const result=await request<{native:Native}>('reports','GET',base+'/report-definitions/'+code+'/field-set');setSchema(result.native);})}>Load report fields</Button>
    {schema&&<form onSubmit={event=>{event.preventDefault();void act(async()=>{const body={code,generation_id:generation,...(code!=='SOURCE_RECONCILIATION'?{
        date_from:start,date_to:end,
        ...(fields.date_basis?.enum?{date_basis:dateBasis}:{}),
        ...(!selected?.financial_statement?{basis,...(basis==='TRANSACTION'?{currency}:{}),
          ...(account?{account_id:account}:{}),...(group?{group_id:group}:{}),
          ...(party?{party_id:party}:{}),...(role?{role}:{})}:{}),
        ...(code==='ACCOUNT_SUMMARY'?{grain}:{}),
        ...(code==='BANK_RECONCILIATION'?{statement_balance:statement}:code==='BANK_RECONCILIATION_EVIDENCE'?{session_id:bankSession}:comparativeFrom||comparativeTo?{comparative_from:comparativeFrom,comparative_to:comparativeTo}:{})
      }:{})};setRun(await create<Run>('/report-runs',body));setRows([]);setCursor(null);});}}>
      {code!=='SOURCE_RECONCILIATION'&&(fields.date_from||fields.date_to)&&<ReportYearRange range={range} disabled={busy}/>}
      {code==='BALANCE_SHEET'&&<p>Previous-year accumulated earnings and current-year profit are derived separately from retained posted history.</p>}
      {code!=='SOURCE_RECONCILIATION'&&fields.date_from&&<TextField label="From date" type="date" value={start} required disabled={busy} onChange={event=>range.custom('from',event.target.value)}/>}
      {code!=='SOURCE_RECONCILIATION'&&fields.date_to&&<TextField label="To date" type="date" value={end} required disabled={busy} onChange={event=>range.custom('to',event.target.value)}/>}
      {fields.date_basis?.enum&&<Select label="Date basis" value={dateBasis} options={fields.date_basis.enum.map(value=>({value,label:value==='TAX_POINT'?'Tax event date':value==='DOCUMENT'?'Document date':'Posting date'}))} disabled={busy} onChange={setDateBasis}/>}
      {!selected?.financial_statement&&code!=='SOURCE_RECONCILIATION'&&fields.account_id&&<SearchSelect label="Ledger account" value={account||null} loadOptions={lookup(company,'accounts')} minQueryLength={0} disabled={busy} onChange={id=>setAccount(id??'')}/>}
      {!selected?.financial_statement&&code!=='SOURCE_RECONCILIATION'&&<>
        {!['BANK_RECONCILIATION','BANK_RECONCILIATION_WORKLIST'].includes(code)&&fields.group_id&&<SearchSelect label="Account group" value={group||null} loadOptions={lookup(company,'account-groups')} minQueryLength={0} disabled={busy} onChange={id=>setGroup(id??'')}/>}
        {!['BANK_RECONCILIATION','BANK_RECONCILIATION_WORKLIST'].includes(code)&&fields.party_id&&<SearchSelect label="Party" value={party||null} loadOptions={lookup(company,'parties')} minQueryLength={0} disabled={busy} onChange={id=>setParty(id??'')}/>}
        {!['BANK_RECONCILIATION','BANK_RECONCILIATION_WORKLIST'].includes(code)&&fields.role&&<Select label="Party role" value={role} options={[{value:'',label:'All roles'},{value:'CUSTOMER',label:'Customer'},{value:'SUPPLIER',label:'Supplier'}]} disabled={busy} onChange={setRole}/>}
        {fields.basis&&<Select label="Amount basis" value={basis} options={[{value:'BASE',label:'Company currency'},{value:'TRANSACTION',label:'Transaction currency'}]} disabled={busy||['BANK_RECONCILIATION_EVIDENCE','BANK_RECONCILIATION_WORKLIST'].includes(code)} onChange={setBasis}/>}
        {basis==='TRANSACTION'&&fields.currency&&<TextField label="Transaction currency" value={currency} required pattern="[A-Z]{3}" disabled={busy} onChange={event=>setCurrency(event.target.value)}/>}
      </>}
      {code==='ACCOUNT_SUMMARY'&&fields.grain&&<Select label="Summary period" value={grain} options={[{value:'DAY',label:'Day'},{value:'MONTH',label:'Month'}]} disabled={busy} onChange={setGrain}/>}
      {!['SOURCE_RECONCILIATION','BANK_RECONCILIATION','BANK_RECONCILIATION_EVIDENCE','BANK_RECONCILIATION_WORKLIST'].includes(code)&&fields.comparative_from&&fields.comparative_to&&<>
        <TextField label="Comparative from date" type="date" value={comparativeFrom} required={!!comparativeTo} disabled={busy} onChange={event=>setComparativeFrom(event.target.value)}/>
        <TextField label="Comparative to date" type="date" value={comparativeTo} required={!!comparativeFrom} disabled={busy} onChange={event=>setComparativeTo(event.target.value)}/>
      </>}
      {code==='BANK_RECONCILIATION'&&fields.statement_balance&&<TextField label="Statement closing balance" value={statement} inputMode="decimal" required disabled={busy} onChange={event=>setStatement(event.target.value)}/>}
      {code==='BANK_RECONCILIATION_EVIDENCE'&&fields.session_id&&<TextField label="Finalized bank session ID" value={bankSession} required disabled={busy} onChange={event=>setBankSession(event.target.value)}/>}
      <Button type="submit" disabled={busy||!generation||(['BANK_RECONCILIATION','BANK_RECONCILIATION_EVIDENCE','BANK_RECONCILIATION_WORKLIST'].includes(code)&&!account)||(code==='BANK_RECONCILIATION_EVIDENCE'&&!bankSession)}>Create report</Button>
    </form>}
    {run&&<><p role="status">Report: {run.status}</p><Button disabled={busy} onClick={()=>void act(async()=>{const next=await request<Run>('reports','GET',base+'/report-runs/'+run.id);setRun(next);if(next.status==='COMPLETE')await loadRows(next.id,null);})}>Refresh report</Button>{['BLOCKED','FAILED'].includes(run.status)&&<p role="alert">Report could not be completed. Check the report parameters and source snapshot before retrying.</p>}{run.download_token&&allowed('report.export')&&<Button disabled={busy} onClick={()=>void act(download)}>Download CSV</Button>}</>}
    {rows.length>0&&<table><caption>{code.replaceAll('_',' ')}</caption><thead><tr>{columns.map(key=><th scope="col" key={key}>{key.replaceAll('_',' ')}</th>)}</tr></thead><tbody>{rows.map(row=><tr key={row.id}>{columns.map(key=><td key={key}>{cell(key,row.data[key],row.data)}</td>)}</tr>)}</tbody></table>}
    {cursor&&run&&<Button disabled={busy} onClick={()=>void act(()=>loadRows(run.id,cursor))}>More report rows</Button>}
    {message&&<p role="alert">{message}</p>}
    <BankingHistory company={company} permissions={permissions}/>
    <BankReconciliation company={company} permissions={permissions}/>
  </section>;
}
