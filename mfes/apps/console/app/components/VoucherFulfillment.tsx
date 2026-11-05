"use client";
import {Select,TextField} from '@janso/ui';
import type {components} from '@janso/api-client/vouchers';
import type {FieldSet} from '../lib/voucher-fields';

type Terms=components['schemas']['FulfillmentTermsInput'];

function purposes(metadata:FieldSet):Terms['purpose'][] {
  const {kind,profile,policy}=metadata.configuration;
  const native:Terms['purpose'][]=kind==='SALES_ORDER'?[profile==='QUOTATION'?'QUOTE':'SALE']
    :kind==='PURCHASE_ORDER'?['PURCHASE']
    :kind==='STOCK_JOURNAL'&&profile==='REQUISITION'?['PROCURE','INTERNAL_ISSUE']:[];
  return native.filter(purpose=>!policy.order?.allowed_purposes||policy.order.allowed_purposes.includes(purpose));
}

export function initialFulfillmentTerms(metadata:FieldSet):Terms|null{
  const allowed=purposes(metadata);
  return allowed.length?{purpose:allowed[0]}:null;
}

export function VoucherFulfillment({metadata,value,onChange,disabled}:{metadata:FieldSet;value:Terms|null;onChange:(value:Terms)=>void;disabled:boolean}){
  const native=metadata.native.properties?.fulfillment_terms;
  if(!value||!native)return null;
  const locked=disabled||!!native.readOnly;
  return <fieldset disabled={locked}><legend>Fulfillment terms</legend>
    {value.purpose==='PROCURE'||value.purpose==='INTERNAL_ISSUE'?<Select label="Requisition purpose" value={value.purpose} disabled={locked||purposes(metadata).length<2} options={purposes(metadata).map(purpose=>({value:purpose,label:purpose==='PROCURE'?'Procure':'Internal issue'}))} onChange={purpose=>onChange({...value,purpose:purpose as Terms['purpose']})}/>:null}
    {value.purpose==='QUOTE'&&<TextField label="Quote valid until" type="date" value={value.valid_until??''} disabled={locked} required onChange={event=>onChange({...value,valid_until:event.target.value||null})}/>}
    <TextField label="Required by" type="date" value={value.required_by??''} disabled={locked} required={value.purpose==='PROCURE'||value.purpose==='INTERNAL_ISSUE'} onChange={event=>onChange({...value,required_by:event.target.value||null})}/>
    <TextField label="Destination reference" value={value.destination_reference??''} disabled={locked} onChange={event=>onChange({...value,destination_reference:event.target.value||null})}/>
    <TextField label="Delivery terms" value={value.delivery_terms??''} disabled={locked} onChange={event=>onChange({...value,delivery_terms:event.target.value})}/>
    <TextField label="Payment terms" value={value.payment_terms??''} disabled={locked} onChange={event=>onChange({...value,payment_terms:event.target.value})}/>
  </fieldset>;
}
