'use client';
import {useEffect,useState} from 'react';
import type {components} from '@janso/api-client/accounting';
import {decimal,sum,request} from './financial-opening';
import {requestFailure,type RequestFailure} from './service-call';

type Schema=components['schemas'];
export type OpeningCapture=Schema['MasterOpeningCapture'];
export type OpeningInput=Schema['MasterOpeningInput'];
export type MasterHeld=Schema['MasterOpeningItem'];
export type MasterHeldPage=Schema['Page_MasterOpeningItem_'];
export type OpeningBillDraft={id:string;reference:string;kind:string;original:string;pending:string;date:string;due:string;base:string};
export type OpeningDraft={mode:'simple'|'bills';amount:string;side:string;date:string;rate:string;base:string;cashReason:string;bills:OpeningBillDraft[];editor:OpeningBillDraft|null};
export type OpeningAccount={party:boolean;role?:string;currencyMode?:string;currency?:string;kind?:string;inventory?:boolean};
export const blankOpening=():OpeningDraft=>({mode:'simple',amount:'',side:'',date:'',rate:'',base:'',cashReason:'',bills:[],editor:null});
export const masterHeldPath=(company:string)=>`/v1/companies/${company}/opening-batches/master-balances`;
const writable=(fields:Record<string,boolean>|undefined)=>!!fields&&Object.keys(fields).length>0&&Object.values(fields).every(value=>value===true);
export const canOpen=(metadata:OpeningCapture|null,account:OpeningAccount)=>!!metadata?.can_capture&&writable(metadata.capture_permissions.journal_lines)&&(!account.party||writable(metadata.capture_permissions.open_items));
export const hasBillDraft=(bill:OpeningBillDraft|null)=>!!bill&&[bill.reference,bill.original,bill.pending,bill.date,bill.due,bill.base].some(Boolean);
export const openingDirty=(draft:OpeningDraft)=>draft.mode==='bills'||!!draft.amount||!!draft.side||!!draft.date||!!draft.rate||!!draft.base||!!draft.cashReason||draft.bills.length>0||hasBillDraft(draft.editor);
export const billKinds=(account:OpeningAccount,side:string)=>{
  const debt=account.role==='CUSTOMER'?side!=='CREDIT':side!=='DEBIT';
  return debt?[{value:account.role==='CUSTOMER'?'INVOICE':'BILL',label:account.role==='CUSTOMER'?'Sales':'Purchase'}]:[{value:'ADVANCE',label:'Advance'},{value:'CREDIT_NOTE',label:'Credit note'}];
};
export const newBill=(account:OpeningAccount,side:string):OpeningBillDraft=>({id:crypto.randomUUID(),reference:'',kind:billKinds(account,side)[0]!.value,original:'',pending:'',date:'',due:'',base:''});
export function pendingTotal(bills:OpeningBillDraft[]){return sum(bills.map(bill=>bill.pending));}
const dateValid=(value:string)=>/^\d{4}-\d{2}-\d{2}$/.test(value)&&Number.isFinite(Date.parse(value))&&new Date(value).toISOString().slice(0,10)===value;
const exactUnits=(value:string)=>BigInt(sum([value]).replace('.',''));
export function billErrors(bill:OpeningBillDraft,account:OpeningAccount,side:string,date:string,foreign:boolean):Record<string,string>{
  const errors:Record<string,string>={};
  if(!bill.reference.trim()||bill.reference.length>120||/[\x00-\x1f\x7f]/.test(bill.reference))errors.reference='Enter a printable bill number, up to 120 characters.';
  if(!decimal(bill.original,true))errors.original='Enter the original bill amount, up to four decimals.';
  if(!decimal(bill.pending,true))errors.pending='Enter a positive pending amount, up to four decimals.';
  else if(decimal(bill.original,true)&&exactUnits(bill.pending)>exactUnits(bill.original))errors.pending='Pending amount cannot exceed bill amount.';
  if(!billKinds(account,side).some(kind=>kind.value===bill.kind))errors.kind='Choose a type matching this role and Dr/Cr.';
  if(!dateValid(bill.date)||bill.date>=date)errors.date='Bill date must be before the opening date.';
  if(!dateValid(bill.due)||bill.due<bill.date)errors.due='Enter the real due date, on or after bill date.';
  if(foreign&&!decimal(bill.base,true))errors.base='Enter the pending historical value in company currency.';
  return errors;
}
export function openingPayload(draft:OpeningDraft,metadata:OpeningCapture|null,account:OpeningAccount):{opening?:OpeningInput;errors:Record<string,string>}{
  const errors:Record<string,string>={};
  if(draft.mode==='simple'&&(!draft.amount||(decimal(draft.amount)&&!/[1-9]/.test(draft.amount))))return {errors};
  if(!metadata||!canOpen(metadata,account)){errors['opening.amount']='Opening capture is unavailable. Retry or leave the opening balance blank.';return {errors};}
  if(account.inventory||account.kind==='INVENTORY_CONTROL'){errors['opening.amount']='Use the stock opening worksheet for inventory accounts.';return {errors};}
  const date=draft.date||metadata.opening_date;
  const foreign=account.currencyMode==='FIXED'&&!!account.currency&&account.currency!==metadata.currency;
  if(!['DEBIT','CREDIT'].includes(draft.side))errors['opening.side']='Choose Dr or Cr explicitly.';
  if(!dateValid(date)||date!==metadata.opening_date)errors['opening.opening_date']='Opening date must match the company’s books-begin date.';
  let amount=draft.amount;
  if(draft.mode==='bills'){
    if(!account.party||!['CUSTOMER','SUPPLIER'].includes(account.role??''))errors['opening.documents']='Bill-wise opening requires a customer or supplier ledger.';
    if(!draft.bills.length||draft.bills.length>200)errors['opening.documents']='Add between 1 and 200 pending bills.';
    if(hasBillDraft(draft.editor))errors['opening.documents']='Add or update the current bill before creating, or cancel that bill.';
    const refs=new Set<string>();
    draft.bills.forEach((bill,index)=>{
      for(const [key,value] of Object.entries(billErrors(bill,account,draft.side,date,foreign)))errors[`opening.documents.${index}.${key}`]=value;
      const reference=bill.reference.trim().toLowerCase();
      if(refs.has(reference))errors[`opening.documents.${index}.reference`]='Bill numbers must be unique.';
      refs.add(reference);
    });
    if(draft.bills.every(bill=>decimal(bill.pending,true)))amount=pendingTotal(draft.bills);
    else amount='';
  }
  if(!decimal(amount,true))errors['opening.amount']='Enter a positive opening balance, up to four decimals.';
  if(foreign){
    if(!/^(?:0|[1-9]\d{0,10})(?:\.\d{1,8})?$/.test(draft.rate)||!/[1-9]/.test(draft.rate))errors['opening.exchange_rate']='Enter a positive exchange rate, up to eight decimals.';
    if(!decimal(draft.base,true))errors['opening.base_amount']='Enter the historical balance in company currency.';
    else if(draft.mode==='bills'&&draft.bills.every(bill=>decimal(bill.base,true))&&sum(draft.bills.map(bill=>bill.base))!==sum([draft.base]))errors['opening.base_amount']='Bill carrying values must equal the account carrying value.';
  }
  if(account.kind==='CASH'&&draft.side==='CREDIT'&&(draft.cashReason.trim().length<3||draft.cashReason.length>500||/[\x00-\x1f\x7f]/.test(draft.cashReason)))errors['opening.credit_cash_reason']='Explain the credit cash opening for review.';
  if(Object.keys(errors).length)return {errors};
  const documents:NonNullable<OpeningInput['documents']>=draft.mode==='bills'?draft.bills.map(bill=>({line_sequence:1,reference:bill.reference.trim(),document_kind:bill.kind as 'INVOICE'|'BILL'|'ADVANCE'|'CREDIT_NOTE',original_amount:bill.original,amount:bill.pending,document_date:bill.date,due_date:bill.due,...(foreign?{base_amount:bill.base}:{})})):[];
  return {errors,opening:{amount,side:draft.side as 'DEBIT'|'CREDIT',opening_date:date,documents,...(foreign?{exchange_rate:draft.rate,base_amount:draft.base}:{}),...(account.kind==='CASH'&&draft.side==='CREDIT'?{credit_cash_reason:draft.cashReason.trim()}:{})}};
}

export function useMasterOpening(company:string,visible:boolean){
  const [draft,setDraft]=useState<OpeningDraft>(blankOpening),[metadata,setMetadata]=useState<OpeningCapture|null>(null),[failure,setFailure]=useState<RequestFailure|null>(null),[loading,setLoading]=useState(false),[revision,setRevision]=useState(0),[owner,setOwner]=useState(company);
  useEffect(()=>{setOwner(company);setDraft(blankOpening());setMetadata(null);setFailure(null);},[company]);
  useEffect(()=>{
    if(!visible)return;
    const controller=new AbortController();setLoading(true);setFailure(null);
    void request<OpeningCapture>({path:masterHeldPath(company)+'/capture',signal:controller.signal}).then(value=>{
      if(controller.signal.aborted)return;
      if(value.company_id!==company||!dateValid(value.opening_date)||!value.capture?.properties||!value.capture_permissions?.journal_lines||!value.capture_permissions?.open_items||!Object.keys(value.capture_permissions.journal_lines).length||!Object.keys(value.capture_permissions.open_items).length||Object.values(value.capture_permissions).some(fields=>Object.values(fields).some(flag=>typeof flag!=='boolean'))||!/^[A-Z]{3}$/.test(value.currency)||typeof value.can_capture!=='boolean'||!Array.isArray(value.blockers)||value.blockers.some(code=>typeof code!=='string'))throw {status:502,message:'Opening capture metadata could not be verified.'};
      setMetadata(value);
    }).catch(error=>{if(!controller.signal.aborted){setMetadata(null);setFailure(requestFailure(error,'Opening balance'));}}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});
    return()=>controller.abort();
  },[company,visible,revision]);
  return {draft:owner===company?draft:blankOpening(),setDraft,metadata:owner===company?metadata:null,failure,loading,retry:()=>setRevision(value=>value+1)};
}
