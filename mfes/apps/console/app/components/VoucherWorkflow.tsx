"use client";
import {useEffect,useRef,useState} from 'react';
import {Button,Select,TextField,useFormatters} from '@janso/ui';
import {VoucherSummary} from './VoucherSummary';
import type {components} from '@janso/api-client/vouchers';
import {VoucherPosting} from './VoucherPosting';
import {VoucherStockSummary} from './VoucherStockSummary';
import {productFieldRequest as request} from '../lib/product-fields';
type Voucher=components['schemas']['VoucherDetail'];
type Transition={id:string;action:string;from_status:string;to_status:string};
type InvoicePreview={calculation_hash:string;payable:string;commercial_total:string;tax_total:string};
export function VoucherWorkflow({company,voucherId,permissions}:{company:string;voucherId:string;permissions:readonly string[]}){
  const [voucher,setVoucher]=useState<Voucher|null>(null),[history,setHistory]=useState<Transition[]>([]),[cursor,setCursor]=useState<string|null>(null);
  const [preview,setPreview]=useState<(InvoicePreview&{revision_id:string})|null>(null);
  const [series,setSeries]=useState<{id:string;code?:string}[]>([]),[selectedSeries,setSelectedSeries]=useState('');
  const [reason,setReason]=useState(''),[message,setMessage]=useState(''),[busy,setBusy]=useState(false);
  const format=useFormatters();
  function verified(value:Voucher):Voucher {
    if(value.id!==voucherId||value.company_id!==company||!Number.isSafeInteger(value.row_version)||value.row_version<1)throw new Error('The voucher could not be verified for this company.');
    return value;
  }
  const retry=useRef<{request:string;key:string}|null>(null),base='/v1/companies/'+company;
  async function action(work:()=>Promise<void>){setBusy(true);setMessage('');try{await work();}catch(error){setMessage(error instanceof Error?error.message:'Unable to update voucher');}finally{setBusy(false);}}
  const allowed=(name:string)=>permissions.includes('vouchers.'+name);
  const canRead=allowed('read');
  useEffect(()=>{
    const controller=new AbortController();
    setVoucher(null);setPreview(null);setHistory([]);setCursor(null);setMessage('');retry.current=null;
    if(canRead){
      setBusy(true);
      void request<Voucher>('vouchers','GET',base+'/vouchers/'+voucherId,undefined,undefined,controller.signal).then(value=>{
        if(!controller.signal.aborted)setVoucher(verified(value));
      }).catch(error=>{if(!controller.signal.aborted)setMessage(error instanceof Error?error.message:'Unable to read voucher');}).finally(()=>{if(!controller.signal.aborted)setBusy(false);});
    }
    return()=>controller.abort();
  },[base,voucherId,canRead]);
  const nonpostingOrder=voucher?.kind==='SALES_ORDER'||voucher?.kind==='PURCHASE_ORDER'||(voucher?.kind==='STOCK_JOURNAL'&&voucher?.profile==='REQUISITION');
  const actions=voucher?.status==='DRAFT'?['submit','cancel']:voucher?.status==='SUBMITTED'?['approve','reject','cancel']:voucher?.status==='APPROVED'?voucher.invoice?['cancel']:['issue','cancel']:voucher?.status==='ISSUED'&&nonpostingOrder?['accept','decline','expire','cancel']:[];
  async function loadHistory(next:string|null){const page=await request<{items:Transition[];page:{next_cursor:string|null}}>('vouchers','GET',base+'/vouchers/'+voucherId+'/history?limit=50'+(next?'&cursor='+encodeURIComponent(next):''));setHistory(previous=>next?[...previous,...page.items]:page.items);setCursor(page.page.next_cursor);}
  return <section className="janso-flow" aria-label="Voucher workflow"><h2>Saved voucher</h2><div className="janso-custom-actions"><Button disabled={busy} onClick={()=>void action(async()=>{setVoucher(verified(await request<Voucher>('vouchers','GET',base+'/vouchers/'+voucherId)));setPreview(null);})}>Refresh voucher</Button></div>
    {voucher&&<><p>Status: {voucher.status}{voucher.issue_number?' · '+voucher.issue_number:''}</p><VoucherSummary company={company} voucher={voucher}/><TextField label="Reason" value={reason} onChange={event=>setReason(event.target.value)} disabled={busy}/>
      <div className="janso-custom-actions">{voucher.status==='DRAFT'&&voucher.invoice&&allowed('read')&&<Button disabled={busy||!voucher.posting_date} onClick={()=>void action(async()=>{const result=await request<InvoicePreview>('vouchers','POST',base+'/vouchers/'+voucherId+'/invoice-preview',{expected_version:voucher.row_version});setPreview({...result,revision_id:voucher.revision_id});})}>Preview invoice</Button>}
      {preview&&voucher.status==='DRAFT'&&voucher.revision_id===preview.revision_id&&<><p>Invoice total: {format.money(preview.payable,{display:'none'})} {voucher.currency}; commercial amount: {format.money(preview.commercial_total,{display:'none'})} {voucher.currency}; tax: {format.money(preview.tax_total,{display:'none'})} {voucher.currency}</p>{allowed('edit')&&<Button disabled={busy} onClick={()=>void action(async()=>{
        const latest=verified(await request<Voucher>('vouchers','GET',base+'/vouchers/'+voucherId));
        if(latest.row_version!==voucher.row_version||latest.revision_id!==preview.revision_id)throw new Error('Voucher changed. Refresh and preview again.');
        if(!latest.invoice)throw new Error('Invoice fields are not readable.');
        const body={expected_version:latest.row_version,calculation_hash:preview.calculation_hash};
        const encoded=JSON.stringify({name:'accept-calculation',body});
        if(retry.current?.request!==encoded)retry.current={request:encoded,key:crypto.randomUUID()};
        setVoucher(verified(await request<Voucher>('vouchers','POST',base+'/vouchers/'+voucherId+'/invoice-acceptance',body,retry.current.key)));retry.current=null;setPreview(null);setMessage('Invoice calculation accepted in a new revision');
      })}>Accept calculation</Button>}</>}
      {actions.includes('issue')&&allowed('issue')&&<><Button disabled={busy} onClick={()=>void action(async()=>{const page=await request<{items:{id:string;code?:string}[]}>('vouchers','GET',base+'/voucher-series?status=ACTIVE&limit=200');setSeries(page.items);})}>Load issue series</Button><Select label="Issue series" value={selectedSeries} options={[{value:'',label:'Configured default'},...series.map(row=>({value:row.id,label:row.code??row.id}))]} onChange={setSelectedSeries}/></>}
      {actions.filter(allowed).map(name=><Button key={name} disabled={busy||(['reject','cancel','decline'].includes(name)&&!reason.trim())} onClick={()=>void action(async()=>{const body={expected_version:voucher.row_version,reason,...(name==='issue'&&selectedSeries?{series_id:selectedSeries}:{})};const encoded=JSON.stringify({name,body});if(retry.current?.request!==encoded)retry.current={request:encoded,key:crypto.randomUUID()};setVoucher(verified(await request<Voucher>('vouchers','POST',base+'/vouchers/'+voucherId+'/'+name,body,retry.current.key)));retry.current=null;setMessage('Voucher '+name+' completed');})}>{name[0].toUpperCase()+name.slice(1)}</Button>)}</div></>}
    {voucher?.stock&&<VoucherStockSummary stock={voucher.stock}/>}
    {voucher&&<VoucherPosting company={company} voucher={voucher} permissions={permissions}/>}
    {allowed('history.read')&&<Button disabled={busy} onClick={()=>void action(()=>loadHistory(null))}>Load voucher history</Button>}
    {history.length>0&&<ol>{history.map(row=><li key={row.id}>{row.action}: {row.from_status} → {row.to_status}</li>)}</ol>}
    {cursor&&<Button disabled={busy} onClick={()=>void action(()=>loadHistory(cursor))}>More history</Button>}{message&&<p role="status">{message}</p>}
  </section>;
}
