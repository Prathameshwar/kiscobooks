'use client';
import {useEffect,useMemo,useRef,useState} from 'react';
import {SearchSelect,useFormatters,type SearchSelectOption} from '@janso/ui';
import {productFieldRequest as request} from '../lib/product-fields';
import {trackingId} from '../lib/stock-tracking-resources';
export type FinanceSession={id:string;company_id:string;account_id:string;currency:string;period_from:string;period_to:string;status:string};
type Session=FinanceSession;
export function FinanceSessionReference({company,account,value,disabled,onChange,onReady,onScope}:{company:string;account:string;value:string;disabled:boolean;onChange:(value:string)=>void;onReady:(ready:boolean)=>void;onScope?:(session:Session)=>void}){
 const format=useFormatters(),[selected,setSelected]=useState<SearchSelectOption|null>(null),[error,setError]=useState('');
 const ready=useRef(onReady);ready.current=onReady;
 const scope=useRef(onScope);scope.current=onScope;
 const base='/v1/companies/'+company+'/bank-reconciliation/sessions';
 const option=(row:Session)=>{
  if(!trackingId.test(row.id)||row.company_id!==company||row.account_id!==account)throw new Error('The reconciliation session belongs to a different account.');
  return {id:row.id,label:format.date(row.period_from)+' to '+format.date(row.period_to),meta:row.currency+' / '+row.status.toLowerCase()};
 };
 useEffect(()=>{const controller=new AbortController();setSelected(null);setError('');ready.current(!value);
  if(value&&account)void request<Session>('accounting','GET',base+'/'+value,undefined,undefined,controller.signal).then(row=>{controller.signal.throwIfAborted();if(row.id!==value||!['FINALIZED','AMENDED'].includes(row.status)||!/^\d{4}-\d{2}-\d{2}$/.test(row.period_from)||!/^\d{4}-\d{2}-\d{2}$/.test(row.period_to)||row.period_from>row.period_to||!(/^[A-Z]{3}$/).test(row.currency))throw new Error('Choose a finalised reconciliation session.');setSelected(option(row));scope.current?.(row);ready.current(true);}).catch(error=>{if(!controller.signal.aborted)setError(error instanceof Error?error.message:'Unable to load session.');});
  return()=>controller.abort();
 },[base,account,value]);
 const load=useMemo(()=>async({q,cursor,signal}:{q:string;cursor:string|null;signal:AbortSignal})=>{
  const params=new URLSearchParams({account_id:account,limit:'50'});if(cursor)params.set('after',cursor);
  const rows=await request<Session[]>('accounting','GET',base+'?'+params,undefined,undefined,signal);
  if(!Array.isArray(rows)||rows.length>50)throw new Error('Unable to read reconciliation sessions.');
  rows.forEach(option);
  return {items:rows.filter(row=>row.status==='FINALIZED').map(option).filter(item=>(item.label+' '+item.meta).toLowerCase().includes(q.trim().toLowerCase())),nextCursor:rows.length===50?rows[49].id:null};
 },[base,account,format]);
 return <SearchSelect label="Finalised reconciliation session" value={value||null} selected={selected} error={error} loadOptions={load} scopeKey={base+':'+account} minQueryLength={0} disabled={disabled||!account} required onChange={value=>onChange(value??'')}/>;
}
