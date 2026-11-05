'use client';
import {useEffect,useRef,useState} from 'react';
import {Button,Notice,SearchSelect,TextField,type SearchSelectLoader} from '@janso/ui';
import type {components} from '@janso/api-client/vouchers';
import {productFieldRequest as request} from '../lib/product-fields';
import {trackingId} from '../lib/stock-tracking-resources';

type Capture=NonNullable<components['schemas']['StockLine-Input']['quantity_entry']>;
type Binding={id:string;unit_id:string;code:string};
type Revision={id:string;conversion_mode:'FIXED'|'MEASURED';valid_from:string;valid_to:string|null};
type Page<T>={items:T[];page:{has_more:boolean;next_cursor:string|null}};
const positive=/^(?:0|[1-9]\d{0,14})(?:\.\d{1,4})?$/;
const valid=(value:string)=>positive.test(value)&&!/^0(?:\.0+)?$/.test(value);

/** The browser requests a native preview; approval/posting verifies the owner facts again. */
export function VoucherStockQuantity({company,item,baseUnit,date,index,value,onPending,onApply,disabled}:{
  company:string;item:string;baseUnit:string;date:string;index:number;value?:Capture|null;
  onPending:()=>void;onApply:(capture:Capture|null,quantity?:string)=>void;disabled:boolean;
}){
  const [enabled,setEnabled]=useState(!!value),[revision,setRevision]=useState<Revision|null>(null);
  const [unit,setUnit]=useState(value?.entered_unit_id??''),[binding,setBinding]=useState<Binding|null>(null);
  const [quantity,setQuantity]=useState(value?.entered_quantity??''),[measured,setMeasured]=useState(value?.measured_base_quantity??'');
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[result,setResult]=useState('');
  const base='/v1/companies/'+company;
  const active=useRef<AbortController|null>(null);
  useEffect(()=>()=>active.current?.abort(),[company,item,baseUnit,date]);
  useEffect(()=>{if(disabled){active.current?.abort();setBusy(false);}},[disabled]);
  const load:SearchSelectLoader=async({cursor,signal})=>{
    const query=new URLSearchParams({limit:'50',...(cursor?{cursor}:{})});
    const page=await request<Page<Binding>>('catalog','GET',base+'/items/'+item+'/unit-bindings?'+query,undefined,undefined,signal);
    if(!Array.isArray(page.items)||!page.page)throw new Error('Product unit choices are unavailable.');
    choices.current=new Map([...choices.current,...page.items.map(row=>[row.id,row] as const)]);
    return {items:page.items.filter(row=>trackingId.test(row.id)&&trackingId.test(row.unit_id)).map(row=>({id:row.id,label:row.code})),nextCursor:page.page.has_more?page.page.next_cursor:null};
  };
  const choices=useRef(new Map<string,Binding>());
  async function select(id:string|null){
    const chosen=choices.current.get(id??'');setBinding(chosen??null);setRevision(null);setUnit(chosen?.unit_id??'');setMeasured('');setResult('');setError('');onPending();
    if(!chosen)return;
    active.current?.abort();const abort=new AbortController();active.current=abort;
    setBusy(true);
    try{
      const page=await request<Page<Revision>>('catalog','GET',base+'/item-unit-bindings/'+chosen.id+'/revisions?limit=200&as_of='+date,undefined,undefined,abort.signal);
      if(abort.signal.aborted)return;
      const effective=page.items.filter(row=>row.valid_from<=date&&(!row.valid_to||row.valid_to>=date));
      if(page.page.has_more||effective.length!==1||!trackingId.test(effective[0]!.id))throw new Error('Choose a product unit with one effective revision on the stock date.');
      setRevision(effective[0]!);
    }catch(cause){if(!abort.signal.aborted)setError(cause instanceof Error?cause.message:'Unable to load the product unit.');}
    finally{if(!abort.signal.aborted)setBusy(false);}
  }
  async function calculate(){
    setError('');setResult('');
    if(!revision||!valid(quantity)||(revision.conversion_mode==='MEASURED'&&!valid(measured))){setError('Select a dated product unit and enter positive exact quantities with at most four decimal places.');return;}
    active.current?.abort();const abort=new AbortController();active.current=abort;
    setBusy(true);
    try{
      const capture:Capture={entered_unit_id:unit,unit_revision_id:revision.id,entered_quantity:quantity,...(revision.conversion_mode==='MEASURED'?{measured_base_quantity:measured}:{})};
      const preview=await request<{item_id:string;base_unit_id:string;base_quantity:string}>('catalog','POST',base+'/items/'+item+'/quantity-preview',{as_of:date,components:[{unit_revision_id:revision.id,quantity,...(revision.conversion_mode==='MEASURED'?{measured_base_quantity:measured}:{})}]},undefined,abort.signal);
      if(abort.signal.aborted)return;
      if(preview.item_id!==item||preview.base_unit_id!==baseUnit||typeof preview.base_quantity!=='string'||!valid(preview.base_quantity))throw new Error('The native quantity preview could not be verified.');
      onApply(capture,preview.base_quantity);setResult('Applied '+preview.base_quantity+' in the product base unit. Posting verifies the conversion again.');
    }catch(cause){if(!abort.signal.aborted)setError(cause instanceof Error?cause.message:'Unable to validate the quantity.');}
    finally{if(!abort.signal.aborted)setBusy(false);}
  }
  const locked=disabled||busy;
  return <fieldset className="janso-fieldgroup janso-flow" disabled={locked}><legend>Product unit entry {index+1}</legend>
    {!enabled?<Button type="button" onClick={()=>{setEnabled(true);onPending();}}>Enter in another product unit {index+1}</Button>:<>
      <SearchSelect label={'Entered product unit '+(index+1)} value={binding?.id??null} selected={binding?{id:binding.id,label:binding.code}:null} loadOptions={load} minQueryLength={0} disabled={locked} onChange={id=>void select(id)}/>
      <TextField label={'Entered quantity '+(index+1)} inputMode="decimal" value={quantity} disabled={locked} onChange={event=>{setQuantity(event.target.value);setResult('');onPending();}}/>
      {revision?.conversion_mode==='MEASURED'&&<><Notice tone="info">Record the actual base quantity. Nominal measurements do not determine physical stock.</Notice><TextField label={'Actual measured base quantity '+(index+1)} inputMode="decimal" value={measured} disabled={locked} onChange={event=>{setMeasured(event.target.value);setResult('');onPending();}}/></>}
      <Button type="button" disabled={locked||!revision} loading={busy} onClick={()=>void calculate()}>Validate and apply quantity {index+1}</Button>
      <Button type="button" disabled={locked} onClick={()=>{setEnabled(false);setRevision(null);setBinding(null);setResult('');setError('');onApply(null);}}>Use base quantity {index+1}</Button>
      {value&&!result&&<p>Recorded entered quantity: {value.entered_quantity}. Base quantity remains on the item line.</p>}
    </>}
    {error&&<p role="alert">{error}</p>}{result&&<p role="status">{result}</p>}
  </fieldset>;
}
