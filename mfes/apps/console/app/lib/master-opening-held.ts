'use client';
import {decimal,sum,type Entry} from './financial-opening';
import {trackingId} from './stock-tracking-resources';
import type {MasterHeld,MasterHeldPage} from './master-opening';

const positive=(value:unknown):value is string=>typeof value==='string'&&decimal(value,true);
const units=(value:string)=>BigInt(sum([value]).replace('.',''));
const date=(value:unknown):value is string=>typeof value==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(value)&&Number.isFinite(Date.parse(value))&&new Date(value).toISOString().slice(0,10)===value;
const bad=()=>({status:502,message:'Saved opening balances could not be verified. Reload the current company.'});
export function verifyMasterItem(company:string,item:MasterHeld){
  const line=item?.entry;
  if(!item||item.company_id!==company||!trackingId.test(item.id)||!trackingId.test(item.account_id)||!Number.isSafeInteger(item.row_version)||item.row_version<1||!['PENDING','WITHDRAWN','POSTING','POSTED','REVERSED'].includes(item.status)||typeof item.included!=='boolean'||!date(item.opening_date)||!line||line.account_id!==item.account_id||line.source_key!==item.source_key||item.source_key!=='mob-'+item.account_id.replaceAll('-','').toLowerCase()||!['DEBIT','CREDIT'].includes(line.side)||!/^[A-Z]{3}$/.test(line.currency)||!positive(line.amount)||!positive(line.base_amount)||typeof line.exchange_rate!=='string'||!/^(?:0|[1-9]\d{0,10})(?:\.\d{1,8})?$/.test(line.exchange_rate)||!/[1-9]/.test(line.exchange_rate)||!Array.isArray(line.documents)||line.documents.length>200)throw bad();
  const refs=new Set<string>();
  for(const doc of line.documents){
    if(doc.line_sequence!==1||typeof doc.reference!=='string'||!doc.reference.trim()||doc.reference.length>120||/[\x00-\x1f\x7f]/.test(doc.reference)||!positive(doc.amount)||!positive(doc.base_amount)||!['ON_ACCOUNT','INVOICE','BILL','ADVANCE','CREDIT_NOTE'].includes(doc.document_kind??'')||doc.original_amount!=null&&(!positive(doc.original_amount)||units(doc.original_amount)<units(doc.amount)))throw bad();
    if(doc.document_kind==='ON_ACCOUNT'?(doc.document_date!=null||doc.due_date!=null):(!date(doc.document_date)||!date(doc.due_date)||doc.document_date>=item.opening_date||doc.due_date<doc.document_date))throw bad();
    const key=doc.reference.trim().toLowerCase();if(refs.has(key))throw bad();refs.add(key);
  }
  if(line.documents.length&&(sum(line.documents.map(doc=>doc.amount))!==sum([line.amount])||sum(line.documents.map(doc=>doc.base_amount!))!==sum([line.base_amount!])))throw bad();
}
export function verifyMasterPage(company:string,value:MasterHeldPage){
  if(!value||!Array.isArray(value.items)||value.items.length>50||!value.page||!Number.isSafeInteger(value.page.limit)||value.page.limit<1||value.page.limit>50||typeof value.page.has_more!=='boolean'||value.page.has_more&&(typeof value.page.next_cursor!=='string'||!value.page.next_cursor||value.page.next_cursor.length>4096)||!value.page.has_more&&value.page.next_cursor!==null)throw bad();
  const ids=new Set<string>();for(const item of value.items){verifyMasterItem(company,item);if(ids.has(item.id))throw bad();ids.add(item.id);}
}
export const masterEntry=(item:MasterHeld):Entry=>({...item.entry,documents:item.entry.documents.map(doc=>doc.document_kind==='ON_ACCOUNT'?{...doc,document_kind:'ON_ACCOUNT',document_date:null,due_date:null}:{...doc,document_kind:doc.document_kind,document_date:doc.document_date!,due_date:doc.due_date!})});
export function addableMaster(items:MasterHeld[],rows:Entry[],date:string){
  const present=new Set(rows.map(row=>row.source_key.toLowerCase()));
  return items.filter(item=>item.status==='PENDING'&&!item.included&&item.opening_date===date&&!present.has(item.source_key.toLowerCase()));
}
