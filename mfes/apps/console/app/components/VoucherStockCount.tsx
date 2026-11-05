'use client';
import {useEffect,useRef,useState} from 'react';
import {Button,Checkbox,Notice,ReviewList,TextField} from '@janso/ui';
import type {components as Accounting} from '@janso/api-client/accounting';
import type {components} from '@janso/api-client/vouchers';
import {productFieldRequest as request} from '../lib/product-fields';
import {trackingId} from '../lib/stock-tracking-resources';

type Detail=Accounting['schemas']['CountDetail'];
type Capture=NonNullable<components['schemas']['StockLine-Input']['count']>;
type Entry=components['schemas']['StockLine-Input']['quantity_entry'];
const exact=/^(?:0|[1-9]\d{0,14})(?:\.\d{1,4})?$/;
const normalized=(value:string)=>{const [whole,fraction='']=value.split('.');return whole+'.'+fraction.padEnd(4,'0');};

export function VoucherStockCount({company,item,warehouse,bin,lot,date,reason,quantity,entry,value,index,disabled,canReview,onPending,onApply}:{
  company:string;item:string;warehouse:string;bin?:string|null;lot?:string|null;date:string;reason:string;
  quantity:string;entry?:Entry;value?:Capture|null;index:number;disabled:boolean;canReview:boolean;
  onPending:()=>void;onApply:(value:Capture|null)=>void;
}){
  const base='/v1/companies/'+company+'/stock/counts';
  const [row,setRow]=useState<Detail|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const [confirmed,setConfirmed]=useState(false),[cost,setCost]=useState(''),[costReason,setCostReason]=useState('');
  const active=useRef<AbortController|null>(null),held=useRef<{signature:string;key:string}|null>(null);
  useEffect(()=>()=>active.current?.abort(),[company,item,warehouse,bin,lot,date]);
  useEffect(()=>{setConfirmed(false);},[quantity,entry]);
  useEffect(()=>{if(disabled){active.current?.abort();setBusy(false);}},[disabled]);
  function verify(data:Detail){
    if(!trackingId.test(data.id)||!trackingId.test(data.root_id)||data.item_id!==item||data.warehouse_id!==warehouse||
      (data.bin_id??null)!==(bin??null)||(data.lot_id??null)!==(lot??null)||data.stock_date>date||
      !Number.isSafeInteger(data.revision)||data.revision<1||typeof data.book_quantity!=='string'||!exact.test(data.book_quantity)){
      throw new Error('The native count response could not be verified.');
    }
    return data;
  }
  async function load(){
    if(!value)return;
    active.current?.abort();const abort=new AbortController();active.current=abort;setBusy(true);setError('');
    try{const data=await request<Detail>('accounting','GET',base+'/'+value.observation_id,undefined,undefined,abort.signal);
      if(!abort.signal.aborted)setRow(verify(data));
    }catch(cause){if(!abort.signal.aborted)setError(cause instanceof Error?cause.message:'Unable to load count evidence.');}
    finally{if(!abort.signal.aborted)setBusy(false);}
  }
  async function mutate(observe:boolean){
    if(disabled||busy)return;
    setError('');onPending();
    if(!trackingId.test(warehouse)||reason.trim().length<3){setError('Select the count warehouse and explain the count.');return;}
    if(observe&&(!row||!confirmed||!exact.test(quantity))){setError('Enter the exact counted base quantity on the item line and confirm the observation. Zero is allowed.');return;}
    if(observe&&cost&&(!canReview||!exact.test(cost)||costReason.trim().length<3)){setError('Cost review requires authorized access, an exact cost and a meaningful reason.');return;}
    const path=observe?base+'/'+row!.id+'/observations':base;
    const body=observe?{expected_revision:row!.revision,observed_quantity:quantity,quantity_entry:entry??null,reason:reason.trim(),
      ...(cost?{reviewed_unit_cost:cost,cost_review_reason:costReason.trim()}:{})}:
      {item_id:item,warehouse_id:warehouse,bin_id:bin??null,lot_id:lot??null,stock_date:date,reason:reason.trim()};
    const signature=JSON.stringify({path,body});
    if(held.current?.signature!==signature)held.current={signature,key:crypto.randomUUID()};
    active.current?.abort();const abort=new AbortController();active.current=abort;setBusy(true);
    try{const result=await request<Detail>('accounting','POST',path,body,held.current.key,abort.signal);
      if(abort.signal.aborted)return;
      const data=verify(result);held.current=null;setRow(data);setConfirmed(false);
      if(observe){
        if(typeof data.observed_quantity!=='string'||!exact.test(data.observed_quantity)||normalized(data.observed_quantity)!==normalized(quantity)||data.status!=='OBSERVED')throw new Error('The recorded physical observation could not be verified.');
        if(data.cost_review_required){onApply(null);setError('Record an authorized cost review before applying this surplus count.');}
        else onApply({observation_id:data.id,expected_revision:data.revision});
      }else{onApply(null);setCost('');setCostReason('');}
    }catch(cause){if(!abort.signal.aborted)setError(cause instanceof Error?cause.message:'Unable to record the physical count.');}
    finally{if(!abort.signal.aborted)setBusy(false);}
  }
  return <fieldset className="janso-fieldgroup janso-flow" disabled={disabled||busy}>
    <legend>Physical count {index+1}</legend>
    <Notice>Start a count to record its cutoff. Enter the observed quantity on the item line, including zero. Posting applies the calculated difference and preserves later movements.</Notice>
    <div className="janso-custom-actions">
      <Button type="button" disabled={disabled||busy||!warehouse||reason.trim().length<3} loading={busy} onClick={()=>void mutate(false)}>{row?'Start a new count':'Start count'} {index+1}</Button>
      {value&&<Button type="button" variant="ghost" disabled={disabled||busy} onClick={()=>void load()}>Load count evidence {index+1}</Button>}
    </div>
    {row&&<><ReviewList items={[
      {label:'Cutoff',value:row.cutoff_at},{label:'Book base quantity',value:row.book_quantity},
      {label:'Observed base quantity',value:row.observed_quantity??'Uncounted'},
      {label:'Calculated difference',value:row.difference??'Awaiting observation'},
      {label:'Later movements',value:row.later_quantity},{label:'Current base quantity',value:row.current_quantity},
    ]}/>
      {row.status==='APPLIED'?<Notice>This count has been applied. Start a new count for another observation.</Notice>:<>
        {row.cost_review_required&&<Notice tone="warning">Native cost is missing or FIFO costs differ. An authorized stock administrator must review the surplus cost.</Notice>}
        {canReview&&<div className="janso-form-grid"><TextField label={'Reviewed base-unit cost '+(index+1)} inputMode="decimal" value={cost} onChange={event=>{setCost(event.target.value);onPending();}} hint="Leave blank to use unambiguous verified native cost."/><TextField label={'Cost review reason '+(index+1)} value={costReason} onChange={event=>{setCostReason(event.target.value);onPending();}} maxLength={500}/></div>}
        <Checkbox checked={confirmed} onChange={event=>setConfirmed(event.target.checked)}>I have physically counted this position at the recorded cutoff {index+1}</Checkbox>
        <Button type="button" disabled={disabled||busy||!confirmed||!exact.test(quantity)||(row.cost_review_required&&!cost)} loading={busy} onClick={()=>void mutate(true)}>Record count observation {index+1}</Button>
      </>}
    </>}
    {!row&&value&&<p>Recorded observation revision {value.expected_revision}. Load its native evidence to inspect or recount.</p>}
    {error&&<p role="alert">{error}</p>}
  </fieldset>;
}
