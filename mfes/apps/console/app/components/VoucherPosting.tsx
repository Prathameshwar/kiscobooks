'use client';
import {useRef,useState} from 'react';
import {Button,TextField} from '@janso/ui';
import type {components} from '@janso/api-client/vouchers';
import {productFieldRequest as request} from '../lib/product-fields';
import {stockAction,stockKind} from '../lib/voucher-stock';
type Operation=Pick<components['schemas']['OperationDetail'],'id'|'status'|'row_version'|'rejection_code'>;
const rejectionMessages:Record<string,string>={STALE_AUTHORITY:'Posting authorization expired. Refresh the voucher and request posting again.',CLOSED_PERIOD:'The posting period is closed. Review the posting date.',CONFIGURATION_CHANGED:'Configuration changed. Refresh and review the voucher before posting.',SOURCE_CONFLICT:'The source already has another execution. Refresh the voucher before proceeding.',UNSUPPORTED_PROFILE:'This voucher profile is not enabled for posting.',CONTENT_REJECTED:'Accounting rejected the entry. Review its accounts, balances, allocations and configuration before posting again.'};
export function VoucherPosting({company,voucher,permissions}:{company:string;voucher:{id:string;status:string;row_version:number;kind?:string|null;profile?:string|null;invoice?:{accepted_calculation_hash?:string|null}|null};permissions:readonly string[]}){
  const [enabled,setEnabled]=useState(false),[moneyEnabled,setMoneyEnabled]=useState(false),[checked,setChecked]=useState(false),[busy,setBusy]=useState(false),[message,setMessage]=useState('');
  const [operation,setOperation]=useState<Operation|null>(null),[date,setDate]=useState(''),[reason,setReason]=useState('');
  const [stockEnabled,setStockEnabled]=useState(false);
  const retry=useRef<{body:string;key:string}|null>(null),base='/v1/companies/'+company;
  const allowed=(name:string)=>permissions.includes('vouchers.'+name);
  async function act(work:()=>Promise<void>){setBusy(true);setMessage('');try{await work();}catch(error){setMessage(error instanceof Error?error.message:'Unable to complete posting');}finally{setBusy(false);}}
  async function mutate(path:string,body:unknown){const encoded=JSON.stringify({path,body});if(retry.current?.body!==encoded)retry.current={body:encoded,key:crypto.randomUUID()};const result=await request<Operation&{operation_id?:string}>('vouchers','POST',base+path,body,retry.current.key);retry.current=null;setOperation({...result,id:result.operation_id??result.id});}
  if(!allowed('post')&&!allowed('reverse')&&!allowed('operation.read'))return null;
  const pending=operation?.status==='PENDING';
  const ordinary=['JOURNAL','CONTRA','PAYMENT','RECEIPT'].includes(voucher.kind??'');
  const physical=!!stockAction(voucher.kind,voucher.profile);
  return <section aria-label="Voucher posting"><Button disabled={busy} onClick={()=>void act(async()=>{const result=await request<{financial_execution:boolean;invoice_execution?:boolean;stock_execution?:boolean;kinds?:{kind:string;execution_ready:boolean;stock_execution_profiles?:string[]}[]}>('vouchers','GET',base+'/voucher-capabilities');const kind=result.kinds?.find(row=>row.kind===voucher.kind),stockReady=!!result.stock_execution&&!!kind?.stock_execution_profiles?.includes(voucher.profile??'');setMoneyEnabled(result.financial_execution);setStockEnabled(stockReady);setEnabled(physical?stockReady:stockKind(voucher.kind)?false:kind?.execution_ready??(voucher.invoice?!!result.invoice_execution:result.financial_execution));setChecked(true);})}>Check posting availability</Button>
    {checked&&!enabled&&<p>Posting is not enabled for this company service.</p>}
    {enabled&&voucher.invoice&&!voucher.invoice.accepted_calculation_hash&&<p>Accept the invoice calculation before posting.</p>}
    {enabled&&physical&&voucher.status==='APPROVED'&&<p>Issue this stock voucher to assign its number before posting.</p>}
    {enabled&&allowed('post')&&['APPROVED','ISSUED'].includes(voucher.status)&&<Button disabled={busy||pending||operation?.status==='COMMITTED'||(physical&&voucher.status!=='ISSUED')||!!(voucher.invoice&&!voucher.invoice.accepted_calculation_hash)} onClick={()=>void act(()=>mutate('/vouchers/'+voucher.id+'/post',{expected_version:voucher.row_version}))}>Post voucher</Button>}
    {(physical?stockEnabled:moneyEnabled&&(voucher.kind?ordinary:!voucher.invoice))&&allowed('reverse')&&voucher.status==='POSTED'&&<><TextField label="Reversal posting date" type="date" value={date} disabled={busy||pending} onChange={event=>setDate(event.target.value)}/><TextField label="Reversal reason" value={reason} disabled={busy||pending} onChange={event=>setReason(event.target.value)}/><Button disabled={busy||pending||!date||reason.trim().length<3} onClick={()=>void act(()=>mutate('/vouchers/'+voucher.id+'/reverse',{expected_version:voucher.row_version,posting_date:date,reason}))}>Reverse voucher</Button></>}
    {operation&&<><p role="status">Execution: {operation.status}</p>{allowed('operation.read')&&<Button disabled={busy} onClick={()=>void act(async()=>{setOperation(await request<Operation>('vouchers','GET',base+'/voucher-operations/'+operation.id));})}>Refresh execution</Button>}
      {pending&&allowed('operation.recover')&&<Button disabled={busy} onClick={()=>void act(()=>mutate('/voucher-operations/'+operation.id+'/recover',{expected_version:operation.row_version}))}>Retry delivery</Button>}
      {pending&&allowed('cancel')&&<Button disabled={busy} onClick={()=>void act(()=>mutate('/voucher-operations/'+operation.id+'/cancel',{expected_version:operation.row_version}))}>Cancel pending execution</Button>}
      {operation.status==='COMMITTED'&&<p>Execution completed. Refresh the voucher to view its current status.</p>}</>}
    {operation?.status==='REJECTED'&&<p role="alert">{rejectionMessages[operation.rejection_code??'']??'Posting was rejected. Refresh and review the voucher before trying again.'}</p>}
    {message&&<p role="alert">{message}</p>}
  </section>;
}
