'use client';
import {useEffect,useMemo,useRef,useState} from 'react';
import {SearchSelect,useFormatters,type SearchSelectOption} from '@janso/ui';
import {productFieldRequest as request} from '../lib/product-fields';
import {trackingId} from '../lib/stock-tracking-resources';

type Invoice={id:string;company_id?:string;bill_reference?:string;kind?:string;currency?:string;posting_date?:string};
type Page={items:Invoice[];page:{next_cursor:string|null}};
export function FinanceInvoiceReference({company,value,from,to,disabled,onChange,onReady}:{company:string;value:string;from?:string;to?:string;disabled:boolean;onChange:(value:string)=>void;onReady:(ready:boolean)=>void}){
 const format=useFormatters(),[selected,setSelected]=useState<SearchSelectOption|null>(null),[error,setError]=useState('');
 const ready=useRef(onReady);ready.current=onReady;
 const base='/v1/companies/'+company+'/invoice-records';
 const option=(row:Invoice)=>{
  if(!trackingId.test(row.id)||(row.company_id!==undefined&&row.company_id!==company))throw new Error('Invoice ownership could not be verified.');
  return {id:row.id,label:row.bill_reference??'Protected invoice reference',meta:[row.kind?.replaceAll('_',' '),row.posting_date?format.date(row.posting_date):'',row.currency].filter(Boolean).join(' / ')};
 };
 useEffect(()=>{const controller=new AbortController();setSelected(null);setError('');ready.current(!value);
  if(value)void request<Invoice>('accounting','GET',base+'/'+value,undefined,undefined,controller.signal).then(row=>{controller.signal.throwIfAborted();if(row.id!==value||row.company_id!==company)throw new Error('Invoice ownership could not be verified.');setSelected(option(row));ready.current(true);}).catch(error=>{if(!controller.signal.aborted)setError(error instanceof Error?error.message:'Invoice unavailable.');});
  return()=>controller.abort();
 },[base,value]);
 const load=useMemo(()=>async({q,cursor,signal}:{q:string;cursor:string|null;signal:AbortSignal})=>{
  const params=new URLSearchParams({limit:'50'});if(cursor)params.set('cursor',cursor);if(from)params.set('date_from',from);if(to)params.set('date_to',to);
  const page=await request<Page>('accounting','GET',base+'?'+params,undefined,undefined,signal);
  if(!Array.isArray(page.items)||page.items.length>50||!page.page)throw new Error('Invoices could not be read.');
  return {items:page.items.map(option).filter(item=>(item.label+' '+item.meta).toLowerCase().includes(q.trim().toLowerCase())),nextCursor:page.page.next_cursor};
 },[base,from,to,format]);
 return <SearchSelect label="Invoice" hint="Posted invoices in this period. Search the loaded page or use Load more." emptyLabel="No matching invoices on this page" value={value||null} selected={selected} error={error} loadOptions={load} scopeKey={[base,from,to].join(':')} minQueryLength={0} disabled={disabled} onChange={value=>onChange(value??'')}/>;
}
