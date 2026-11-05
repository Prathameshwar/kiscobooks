'use client';
import {Checkbox,Select,TextField} from '@janso/ui';
import type {PurchaseCalculationStep} from '../lib/purchase-calculation';

export function PurchaseCalculationStepFields({step,prefix,previous,disabled,onChange}:{
 step:PurchaseCalculationStep;prefix:string;previous:readonly {key:string;name:string}[];disabled?:boolean;
 onChange:(patch:Partial<PurchaseCalculationStep>)=>void;
}){
 return <div className="janso-flow">
  <div className="janso-form-grid janso-entry-detail__pair">
   <TextField label={prefix+' name'} value={step.name} required maxLength={80} disabled={disabled} onChange={event=>onChange({name:event.target.value})}/>
   <Select label={prefix+' purpose'} value={step.purpose} disabled={disabled} options={[{value:'DISCOUNT',label:'Discount'},{value:'PACKING',label:'Packing'},{value:'FREIGHT',label:'Freight'},{value:'INSURANCE',label:'Insurance'},{value:'HANDLING',label:'Handling'},{value:'OTHER_CHARGE',label:'Other charge'}]} onChange={value=>onChange({purpose:value as PurchaseCalculationStep['purpose']})}/>
   <Select label={prefix+' input'} value={step.input_kind} disabled={disabled} options={[{value:'PERCENT',label:'Percentage'},{value:'FIXED',label:'Fixed amount'}]} onChange={value=>onChange({input_kind:value as PurchaseCalculationStep['input_kind']})}/>
   <TextField label={prefix+' value'+(step.input_kind==='PERCENT'?' (%)':'')} value={step.value} inputMode="decimal" maxLength={24} disabled={disabled} onChange={event=>onChange({value:event.target.value})}/>
   <Select label={prefix+' calculation basis'} value={step.basis_recipe} disabled={disabled} options={[{value:'ORIGINAL',label:'Original line amount'},{value:'AFTER_DISCOUNTS',label:'After line and preceding discounts'},{value:'AFTER_STEPS',label:'After line discounts and selected steps'}]} onChange={value=>onChange({basis_recipe:value as PurchaseCalculationStep['basis_recipe'],dependencies:[]})}/>
   <Select label={prefix+' amount basis'} value={step.amount_basis} disabled={disabled} options={[{value:'NET_EXCL_TAX',label:'Amount excluding tax'},{value:'GROSS_INCL_TAX',label:'Amount including supplier-charged tax'}]} onChange={value=>onChange({amount_basis:value as PurchaseCalculationStep['amount_basis'],...(value==='GROSS_INCL_TAX'?{tax_treatment:'ASSESSABLE' as const}:{})})}/>
   <Select label={prefix+' applies to'} value={step.scope} disabled={disabled} options={[{value:'INVOICE',label:'All bill lines'},{value:'SELECTED_LINES',label:'Selected bill lines'}]} onChange={value=>onChange({scope:value as PurchaseCalculationStep['scope']})}/>
   <Select label={prefix+' tax treatment'} value={step.tax_treatment} disabled={disabled||step.amount_basis==='GROSS_INCL_TAX'} options={[{value:'ASSESSABLE',label:'Changes assessable amount'},{value:'NO_CHANGE',label:'Does not change assessable amount'}]} onChange={value=>onChange({tax_treatment:value as PurchaseCalculationStep['tax_treatment']})}/>
  </div>
  {step.basis_recipe==='AFTER_STEPS'&&<fieldset className="janso-entry-detail__group"><legend>{prefix+' preceding steps'}</legend>{previous.length?previous.map(row=><Checkbox key={row.key} checked={step.dependencies.includes(row.key)} disabled={disabled} onChange={event=>onChange({dependencies:event.target.checked?[...step.dependencies,row.key]:step.dependencies.filter(key=>key!==row.key)})}>{row.name||'Unnamed step'}</Checkbox>):<p>Add a preceding step before choosing this basis.</p>}</fieldset>}
 </div>;
}
