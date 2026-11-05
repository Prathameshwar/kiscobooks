'use client';
import {useMemo,useRef} from 'react';
import {Button,SearchSelect,Select,TextField,type SearchSelectLoader} from '@janso/ui';
import type {components} from '@janso/api-client/vouchers';
import {lookup,type Choice,type FieldSet} from '../lib/voucher-fields';
import {productFieldRequest as request} from '../lib/product-fields';
export type MoneyInput=components['schemas']['MoneyInput-Input'];
type Entry=components['schemas']['AccountEntry-Input'];
type Tender=components['schemas']['Tender-Input'];
type Allocation=components['schemas']['BillAllocation-Input'];
const options=(values:readonly string[])=>values.map(value=>({value,label:value.replaceAll('_',' ')}));
export function VoucherMoney({company,currency,metadata,value,onChange,disabled,knownAccounts=[]}:{company:string;currency:string;metadata:FieldSet;value:MoneyInput|null;onChange:(value:MoneyInput|null)=>void;disabled:boolean;knownAccounts?:Choice[]}){
  const choices=useRef(new Map<string,Choice>());
  for(const row of knownAccounts)choices.current.set(row.id,row);
  const accounts=useMemo(()=>lookup(company,'accounts',rows=>rows.forEach(row=>choices.current.set(row.id,row))),[company]);
  const kind=metadata.configuration.kind,policy=metadata.configuration.policy.financial,moneyPolicy=metadata.configuration.policy.money;
  const field=metadata.native.properties?.financial;
  if(!field||field.readOnly||!['JOURNAL','CONTRA','PAYMENT','RECEIPT'].includes(kind??''))return null;
  const purposeChoices=(kind==='CONTRA'?['TRANSFER']:metadata.configuration.profile==='ADVANCE'?['ADVANCE']:kind==='JOURNAL'?['GENERAL','SETTLEMENT','BILL_ADJUSTMENT']:['GENERAL','SETTLEMENT','ADVANCE','REFUND']).filter(purpose=>!moneyPolicy?.allowed_purposes||moneyPolicy.allowed_purposes.includes(purpose as NonNullable<MoneyInput['purpose']>));
  const modes=(policy?.allowed_payment_modes??['CASH','CHEQUE','NEFT','RTGS','IMPS','UPI','CARD','BANK_TRANSFER']).filter(mode=>!moneyPolicy?.allowed_tender_modes||moneyPolicy.allowed_tender_modes.includes(mode));
  const data:MoneyInput=value??{purpose:purposeChoices[0] as MoneyInput['purpose'],accounts:[],tenders:[],allocations:[]};
  const entries=data.accounts??[],tenders=data.tenders??[],allocations=data.allocations??[];
  const blocked=metadata.configuration.policy.forbidden_sections??[];
  function tenderModes(lineKey:string){const entry=entries.find(row=>row.line_key===lineKey),accountKind=choices.current.get(entry?.account_id??'')?.kind;return modes.filter(mode=>accountKind==='CASH'?mode==='CASH':accountKind==='BANK'?mode!=='CASH':true);}
  function update(index:number,next:Entry){onChange({...data,accounts:entries.map((row,i)=>i===index?next:row)});}
  function tender(index:number,next:Tender){onChange({...data,tenders:tenders.map((row,i)=>i===index?next:row)});}
  function allocation(index:number,next:Allocation){onChange({...data,allocations:allocations.map((row,i)=>i===index?next:row)});}
  const loadAccounts:SearchSelectLoader=async args=>{const result=await accounts(args);return {...result,items:result.items.map(row=>({...row,disabled:
    (policy?.allowed_account_ids!=null&&!policy.allowed_account_ids.includes(row.id))||
    (!!policy?.allowed_account_kinds&&!policy.allowed_account_kinds.includes(choices.current.get(row.id)?.kind as NonNullable<typeof policy.allowed_account_kinds>[number]))}))};};
  function bills(direction:'DEBT'|'CREDIT',billCurrency:string):SearchSelectLoader{return async({q,cursor,signal})=>{
    const params=new URLSearchParams({limit:'50',direction,...(q?{q}:{}),...(cursor?{cursor}:{})});
    const page=await request<{items:{id:string;reference?:string;currency?:string;reversal_date?:string|null}[];page:{next_cursor:string|null}}>('accounting','GET','/v1/companies/'+company+'/open-items?'+params,undefined,undefined,signal);
    return {items:page.items.filter(row=>row.reference&&row.currency===billCurrency&&!row.reversal_date).map(row=>({id:row.id,label:row.reference!})),nextCursor:page.page.next_cursor};
  };}
  return <fieldset className="janso-fieldgroup janso-flow" disabled={disabled}><legend className="janso-fieldgroup__legend">Accounts and settlement</legend>
    <Select label="Transaction purpose" value={data.purpose??''} disabled={disabled||!purposeChoices.length} options={options(purposeChoices)} onChange={purpose=>onChange({...data,purpose:purpose as MoneyInput['purpose'],...(purpose==='BILL_ADJUSTMENT'?{accounts:[],tenders:[]}:{})})}/>
    {entries.map((entry,index)=><fieldset className="janso-fieldgroup janso-flow" key={entry.line_key}><legend className="janso-fieldgroup__legend">Account entry {index+1}</legend><div className="janso-form-grid">
      <SearchSelect label={'Account '+(index+1)} selected={knownAccounts.find(row=>row.id===entry.account_id)?{id:entry.account_id,label:knownAccounts.find(row=>row.id===entry.account_id)!.name??knownAccounts.find(row=>row.id===entry.account_id)!.code??entry.account_id}:undefined} value={entry.account_id||null} loadOptions={loadAccounts} minQueryLength={0} disabled={disabled} onChange={id=>update(index,{...entry,account_id:id??'',source_version:choices.current.get(id??'')?.row_version??0})}/>
      <Select label={'Side '+(index+1)} value={entry.side} options={options(['DEBIT','CREDIT'])} onChange={side=>update(index,{...entry,side:side as Entry['side']})}/>
      <TextField label={'Amount '+(index+1)} value={entry.amount} required inputMode="decimal" pattern="[0-9]+([.][0-9]{1,4})?" onChange={event=>update(index,{...entry,amount:event.target.value})}/>
      {policy?.foreign_currency_allowed&&<><TextField label={'Currency '+(index+1)} value={entry.currency} required pattern="[A-Z]{3}" onChange={event=>update(index,{...entry,currency:event.target.value})}/><TextField label={'Exchange rate '+(index+1)} value={entry.exchange_rate??'1'} required inputMode="decimal" onChange={event=>update(index,{...entry,exchange_rate:event.target.value})}/></>}
      <TextField label={'Entry description '+(index+1)} value={entry.description??''} maxLength={500} onChange={event=>update(index,{...entry,description:event.target.value})}/>
      {policy?.settlement_adjustments_allowed&&<Select label={'Amount purpose '+(index+1)} value={entry.purpose??'PRINCIPAL'} options={options(['PRINCIPAL','DISCOUNT','FEE','ROUNDING'])} onChange={purpose=>update(index,{...entry,purpose:purpose as Entry['purpose']})}/>}
      {kind!=='CONTRA'&&<Select label={'Bill tracking '+(index+1)} value={entry.tracking??'NONE'} options={options(policy?.allowed_tracking??['NONE','NEW_REF','ON_ACCOUNT','ADVANCE'])} onChange={tracking=>update(index,{...entry,tracking:tracking as Entry['tracking'],bill_reference:null,due_date:null})}/>}
      {entry.tracking&&entry.tracking!=='NONE'&&<><TextField label={'Bill reference '+(index+1)} value={entry.bill_reference??''} required={entry.tracking==='NEW_REF'} onChange={event=>update(index,{...entry,bill_reference:event.target.value||null})}/><TextField label={'Due date '+(index+1)} type="date" value={entry.due_date??''} hint="Optional. Without one the bill is due on the voucher date." onChange={event=>update(index,{...entry,due_date:event.target.value||null})}/></>}
      </div><div className="janso-custom-actions">{!blocked.includes('TENDERS')&&['CASH','BANK'].includes(choices.current.get(entry.account_id)?.kind??'')&&<Button type="button" disabled={disabled||!tenderModes(entry.line_key).length||tenders.length>=(moneyPolicy?.max_tenders??200)||(policy?.split_tenders_allowed===false&&(kind==='CONTRA'?tenders.some(row=>row.line_key===entry.line_key):tenders.length>0))} onClick={()=>{const allowed=tenderModes(entry.line_key),preferred=choices.current.get(entry.account_id)?.kind==='CASH'?'CASH':'BANK_TRANSFER';onChange({...data,tenders:[...tenders,{tender_key:crypto.randomUUID(),line_key:entry.line_key,mode:allowed.includes(preferred)?preferred:allowed[0],amount:entry.amount,currency:entry.currency,recognition:'BOOK_DATE'}]});}}>Add payment detail {index+1}</Button>}
      <Button type="button" variant="ghost" onClick={()=>onChange({...data,accounts:entries.filter((_,i)=>i!==index),tenders:tenders.filter(row=>row.line_key!==entry.line_key),allocations:allocations.filter(row=>row.debt.line_key!==entry.line_key&&row.credit.line_key!==entry.line_key)})}>Remove account {index+1}</Button>
    </div></fieldset>)}
    {data.purpose!=='BILL_ADJUSTMENT'&&!blocked.includes('ACCOUNTS')&&<Button type="button" disabled={disabled||entries.length>=(policy?.max_account_entries??200)} onClick={()=>onChange({...data,accounts:[...entries,{line_key:crypto.randomUUID(),account_id:'',source_version:0,side:entries.length?'CREDIT':'DEBIT',currency,amount:'',exchange_rate:'1',tracking:'NONE'}]})}>Add account entry</Button>}
    {tenders.map((row,index)=><fieldset className="janso-fieldgroup janso-flow" key={row.tender_key}><legend className="janso-fieldgroup__legend">Payment detail {index+1}</legend><div className="janso-form-grid">
      <Select label={'Payment mode '+(index+1)} value={row.mode} options={options(tenderModes(row.line_key))} onChange={mode=>tender(index,{...row,mode:mode as Tender['mode'],reference:null,instrument_date:null,recognition:'BOOK_DATE'})}/>
      <TextField label={'Tender amount '+(index+1)} inputMode="decimal" value={row.amount} required onChange={event=>tender(index,{...row,amount:event.target.value})}/>
      {row.mode!=='CASH'&&<TextField label={'Payment reference '+(index+1)} value={row.reference??''} hint="Optional: cheque, UTR or slip number." onChange={event=>tender(index,{...row,reference:event.target.value||null})}/>}
      {row.mode==='CHEQUE'&&<><TextField label={'Instrument date '+(index+1)} type="date" value={row.instrument_date??''} required onChange={event=>tender(index,{...row,instrument_date:event.target.value})}/><Select label={'Recognition '+(index+1)} value={row.recognition??'BOOK_DATE'} options={options(policy?.allowed_recognition??['BOOK_DATE','MATURITY_DATE'])} onChange={recognition=>tender(index,{...row,recognition:recognition as Tender['recognition']})}/></>}
      </div><div className="janso-custom-actions"><Button type="button" variant="ghost" onClick={()=>onChange({...data,tenders:tenders.filter((_,i)=>i!==index)})}>Remove payment detail {index+1}</Button>
    </div></fieldset>)}
    {allocations.map((row,index)=><fieldset className="janso-fieldgroup janso-flow" key={row.allocation_key}><legend className="janso-fieldgroup__legend">Bill adjustment {index+1}</legend><div className="janso-form-grid">
      {(['debt','credit'] as const).map(side=><div key={side}><Select label={side+' target '+(index+1)} value={row[side].line_key??'existing'} options={[{value:'existing',label:'Existing bill or advance'},...entries.filter(entry=>entry.tracking&&entry.tracking!=='NONE').map((entry,i)=>({value:entry.line_key,label:'New tracked account entry '+(i+1)}))]} onChange={id=>allocation(index,{...row,[side]:id==='existing'?{item_id:''}:{line_key:id}})}/>{!row[side].line_key&&<SearchSelect label={side+' bill '+(index+1)} value={row[side].item_id??null} loadOptions={bills(side==='debt'?'DEBT':'CREDIT',row.currency)} minQueryLength={0} onChange={id=>allocation(index,{...row,[side]:{item_id:id??''}})}/>}</div>)}
      {policy?.foreign_currency_allowed&&<TextField label={'Allocation currency '+(index+1)} value={row.currency} required pattern="[A-Z]{3}" onChange={event=>allocation(index,{...row,currency:event.target.value,debt:{item_id:''},credit:{item_id:''}})}/>}
      <TextField label={'Allocation amount '+(index+1)} value={row.amount} required inputMode="decimal" onChange={event=>allocation(index,{...row,amount:event.target.value})}/>
      {policy?.foreign_currency_allowed&&<SearchSelect label={'Exchange difference account '+(index+1)} value={row.fx_account_id??null} loadOptions={accounts} minQueryLength={0} onChange={id=>allocation(index,{...row,fx_account_id:id})}/>}
      </div><div className="janso-custom-actions"><Button type="button" variant="ghost" onClick={()=>onChange({...data,allocations:allocations.filter((_,i)=>i!==index)})}>Remove bill adjustment {index+1}</Button>
    </div></fieldset>)}
    {kind!=='CONTRA'&&policy?.allocations_allowed!==false&&!blocked.includes('BILL_ALLOCATIONS')&&<Button type="button" disabled={disabled||allocations.length>=200} onClick={()=>onChange({...data,allocations:[...allocations,{allocation_key:crypto.randomUUID(),debt:{item_id:''},credit:{item_id:''},amount:'',currency}]})}>Add bill adjustment</Button>}
  </fieldset>;
}
