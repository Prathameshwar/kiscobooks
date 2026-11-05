'use client';
import {useRef,useState} from 'react';
import {Badge,Button,DataTable,Notice,Select,type Column,type Tone} from '@janso/ui';
import type {components} from '@janso/api-client/vouchers';
import {productFieldRequest as request} from '../lib/product-fields';
import {sessionFetch} from '../lib/session-fetch';
import {IMPORT_KINDS} from '../lib/operate-navigation';
import {trackingId} from '../lib/stock-tracking-resources';
type Job=components['schemas']['ImportJobDetail'];
type Row=components['schemas']['ImportVoucherListItem'];
type Detail=components['schemas']['ImportVoucherDetail'];
type Format='CSV'|'XLSX'|'JSON';
type VoucherType={id:string;name?:string|null;code?:string|null;kind?:string|null};
/** Kinds the import supports; other types are not offered. */
export const importKinds=IMPORT_KINDS;
type DuplicateRule=Job['duplicate_rule'];
const duplicateRules:{value:DuplicateRule;label:string}[]=[{value:'DATE_NUMBER_PARTY',label:'Same bill number, date and supplier'},{value:'DATE_NUMBER_ACCOUNT',label:'Same bill number, date and supplier ledger'},{value:'DATE_NUMBER',label:'Same bill number and date, any supplier'}];
const tones:Record<string,Tone>={VALID:'success',CREATED:'success',SUCCEEDED:'success',WARNING:'warn',PARTIAL:'warn',INVALID:'danger',FAILED:'danger',BLOCKED:'danger'};
const working=new Set(['VALIDATING','COMMITTING']);
/** File bytes as base64, read by the browser rather than re-encoded in script. */
export function fileBase64(file:Blob):Promise<string>{
  return new Promise((resolve,reject)=>{
    const reader=new FileReader();
    reader.onerror=()=>reject(new Error('Unable to read the selected file'));
    reader.onload=()=>resolve(String(reader.result).replace(/^data:[^,]*,/,''));
    reader.readAsDataURL(file);
  });
}
/** Downloads go through the same-origin proxy so the access token never reaches the page. */
export async function download(path:string,name:string):Promise<void>{
  const response=await sessionFetch('/api/product-fields',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({service:'vouchers',method:'GET',path})});
  if(!response.ok){const value=await response.json().catch(()=>({}));throw new Error(value.error?.message??'Unable to download the file');}
  const blob=await response.blob(),url=URL.createObjectURL(blob),link=document.createElement('a');
  link.href=url;link.download=name;link.click();
  // Revoking at once can cancel the download in some browsers.
  setTimeout(()=>URL.revokeObjectURL(url),60000);
}
export function VoucherImport({company,permissions,initialKind,initialTypeId}:{company:string;permissions:readonly string[];initialKind?:string;initialTypeId?:string}){
  const can=(key:string)=>permissions.includes('vouchers.'+key);
  const manage=can('import.manage')&&can('create'),commitAllowed=can('import.commit')&&can('create');
  const [types,setTypes]=useState<VoucherType[]>([]),[type,setType]=useState(initialTypeId??''),[format,setFormat]=useState<Format>('XLSX'),[moreTypes,setMoreTypes]=useState(false);
  const [rule,setRule]=useState<DuplicateRule>('DATE_NUMBER_PARTY'),[file,setFile]=useState<File|null>(null),[job,setJob]=useState<Job|null>(null),[rows,setRows]=useState<Row[]>([]),[detail,setDetail]=useState<Detail|null>(null);
  const [onError,setOnError]=useState<'STOP'|'CONTINUE_INDEPENDENT'>('STOP'),[reviewed,setReviewed]=useState(false),[busy,setBusy]=useState(false),[message,setMessage]=useState('');
  const retry=useRef<{intent:string;key:string}|null>(null),base='/v1/companies/'+company;
  if(!can('import.read'))return null;
  function key(intent:string){if(retry.current?.intent!==intent)retry.current={intent,key:crypto.randomUUID()};return retry.current.key;}
  async function act(work:()=>Promise<void>){setBusy(true);setMessage('');try{await work();}catch(error){setMessage(error instanceof Error?error.message:'Unable to complete the import action');}finally{setBusy(false);}}
  async function refresh(next:Job){
    let current=next;
    // Validation and commit advance in bounded steps; keep stepping while the job works.
    setJob(current);setDetail(null);setReviewed(false);
    for(let step=0;step<50&&working.has(current.state);step++){current=await request<Job>('vouchers','POST',base+'/voucher-imports/'+current.id+'/run',{});setJob(current);}
    // Review needs every voucher: a job holds at most 500, so this is at most three pages.
    const all:Row[]=[];let cursor:string|null|undefined;
    do{const page=await request<{items:Row[];next_cursor?:string|null}>('vouchers','GET',base+'/voucher-imports/'+current.id+'/vouchers?limit=200'+(cursor?'&cursor='+encodeURIComponent(cursor):''));all.push(...page.items);cursor=page.next_cursor;}while(cursor);
    setRows(all);
  }
  async function mutate(path:string,body:unknown){const intent=JSON.stringify({path,body});const result=await request<Job>('vouchers','POST',base+path,body,key(intent));retry.current=null;await refresh(result);}
  const columns:Column<Row>[]=[
    {key:'import_key',header:'Import key',type:'code'},
    {key:'state',header:'Result',type:'custom',render:row=><Badge tone={tones[row.state]??'neutral'}>{row.state}</Badge>},
    {key:'declared_total',header:'Declared total',type:'money',currencyKey:'currency'},
    {key:'computed_payable',header:'Calculated amount',type:'money',currencyKey:'currency'},
    {key:'supplier_difference',header:'Difference',type:'money',currencyKey:'currency'},
    {key:'error_count',header:'Errors',type:'custom',render:row=>String(row.error_count)},
    {key:'details',header:'Details',type:'custom',render:row=><Button disabled={busy} onClick={()=>void act(async()=>setDetail(await request<Detail>('vouchers','GET',base+'/voucher-imports/'+job?.id+'/vouchers/'+encodeURIComponent(row.import_key))))}>{'Details for '+row.import_key}</Button>},
  ];
  const selected=(job?.valid_count??0)+(job?.warning_count??0);
  const chosen=types.find(row=>row.id===type),purchase=chosen?.kind==='PURCHASE';
  return <section aria-label="Voucher import"><h2>Import vouchers</h2>
    <Button disabled={busy} onClick={()=>void act(async()=>{
      const page=initialTypeId?{items:[await request<VoucherType&{company_id?:string;status?:string}>('vouchers','GET',base+'/voucher-types/'+initialTypeId)]}:await request<{items:(VoucherType&{company_id?:string;status?:string})[];page?:{has_more:boolean}}>('vouchers','GET',base+'/voucher-types?status=ACTIVE&limit=200'+(initialKind?'&kind='+initialKind:''));
      if(initialKind&&(!Array.isArray(page.items)||page.items.some(row=>!trackingId.test(row.id)||row.company_id!==company||row.kind!==initialKind||row.status!=='ACTIVE'||initialTypeId&&row.id!==initialTypeId)))throw new Error('Voucher type ownership and kind could not be verified.');
      setTypes(page.items.filter(row=>!!row.kind&&row.kind in importKinds));setMoreTypes('page' in page&&!!page.page?.has_more);
    })}>Load voucher types</Button>
    {moreTypes&&<Notice>More types are available. Open Import voucher from a specific type's list to select a type beyond this page.</Notice>}
    <Select label="Voucher type" value={type} disabled={busy} options={types.map(row=>({value:row.id,label:(row.name??row.code??row.id)+' ('+importKinds[row.kind??'']+')'}))} onChange={value=>{setType(value);setRule('DATE_NUMBER_PARTY');setJob(null);setRows([]);}}/>
    <Select label="File format" value={format} disabled={busy} options={(['XLSX','CSV','JSON'] as const).map(value=>({value,label:value}))} onChange={value=>setFormat(value as Format)}/>
    {manage&&<Button disabled={busy||!type||!chosen} onClick={()=>void act(()=>download(base+'/voucher-import-templates?voucher_type_id='+encodeURIComponent(type)+'&format='+format,'voucher-import.'+format.toLowerCase()))}>Download template</Button>}
    {manage&&purchase&&<Select label="Treat as duplicate" value={rule} disabled={busy} options={duplicateRules} onChange={value=>setRule(value as DuplicateRule)}/>}
    {manage&&<label>Import file<input type="file" accept=".csv,.xlsx,.json" disabled={busy} onChange={event=>setFile(event.target.files?.[0]??null)}/></label>}
    {manage&&<Button disabled={busy||!type||!chosen||!file} loading={busy} onClick={()=>void act(async()=>{
      if(!file)return;
      const body=format==='JSON'?{voucher_type_id:type,format,duplicate_rule:rule,document:JSON.parse(await new Response(file).text())}:{voucher_type_id:type,format,duplicate_rule:rule,content_base64:await fileBase64(file)};
      const result=await request<Job>('vouchers','POST',base+'/voucher-imports',body,key('stage:'+type+':'+format+':'+rule+':'+file.name+':'+file.size+':'+file.lastModified));
      retry.current=null;await refresh(result);
    })}>Upload file</Button>}
    {job&&<div aria-label="Import job">
      <p role="status">Job {job.state}: {job.voucher_count} vouchers, {job.valid_count} valid, {job.warning_count} with warnings, {job.invalid_count} invalid, {job.created_count} drafts created, {job.failed_count} failed.</p>
      {job.kind==='PURCHASE'&&<p>Duplicate check: {duplicateRules.find(row=>row.value===job.duplicate_rule)?.label??job.duplicate_rule}</p>}
      {['STAGED','READY'].includes(job.state)&&manage&&<Button disabled={busy} onClick={()=>void act(()=>mutate('/voucher-imports/'+job.id+'/validate',{expected_version:job.row_version}))}>{job.state==='READY'?'Validate again':'Validate'}</Button>}
      {working.has(job.state)&&<Button disabled={busy} onClick={()=>void act(()=>refresh(job))}>Continue</Button>}
      {job.state==='READY'&&commitAllowed&&(selected>0?<>
        <Select label="If a draft fails" value={onError} disabled={busy} options={[{value:'STOP',label:'Stop the import'},{value:'CONTINUE_INDEPENDENT',label:'Continue with the others'}]} onChange={value=>setOnError(value as typeof onError)}/>
        <label><input type="checkbox" checked={reviewed} disabled={busy} onChange={event=>setReviewed(event.target.checked)}/>I reviewed the results; create {selected} draft vouchers</label>
        <Button disabled={busy||!reviewed} onClick={()=>void act(()=>mutate('/voucher-imports/'+job.id+'/commit',{expected_version:job.row_version,selection_digest:job.selection_digest,on_error:onError}))}>Create drafts</Button>
      </>:<Notice tone="warning">No voucher passed validation. Correct the file and upload it again.</Notice>)}
      {['STAGED','READY','VALIDATING','COMMITTING'].includes(job.state)&&manage&&<Button disabled={busy} onClick={()=>void act(()=>mutate('/voucher-imports/'+job.id+'/cancel',{expected_version:job.row_version}))}>Cancel import</Button>}
      {!['STAGED','VALIDATING'].includes(job.state)&&<Button disabled={busy} onClick={()=>void act(async()=>{const ticket=await request<{download_path:string}>('vouchers','GET',base+'/voucher-imports/'+job.id+'/report-ticket?format=CSV');await download(ticket.download_path,'voucher-import-results.csv');})}>Download result report</Button>}
      {rows.length>0&&<DataTable caption="Import results" columns={columns} rows={rows} rowId={row=>row.id} rowLabel={row=>'Import '+row.import_key}/>}
      {detail&&<div aria-label={'Details for '+detail.import_key}><h3>{detail.import_key}</h3>
        {detail.errors.length?<ul>{detail.errors.map((error,index)=><li key={index}>{error.sheet} row {error.row}{error.column?' · '+error.column:''}: {error.message} ({error.code})</li>)}</ul>:<p>No problems found.</p>}
        {detail.voucher_id&&<p>Draft voucher: {detail.voucher_id}</p>}
      </div>}
    </div>}
    {message&&<p role="alert">{message}</p>}
  </section>;
}
