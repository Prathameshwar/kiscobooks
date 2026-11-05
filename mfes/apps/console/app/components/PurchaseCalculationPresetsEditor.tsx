'use client';
import {useState} from 'react';
import {Button,Notice,Select,TextField} from '@janso/ui';
import {calculationStep,purchaseCalculationStarters,validateCalculationPolicy,type PurchaseCalculationPolicy,type PurchaseCalculationPreset} from '../lib/purchase-calculation';
import {PurchaseCalculationStepFields} from './PurchaseCalculationStepFields';
import {PurchaseCalculationExample} from './PurchaseCalculationExample';

export function PurchaseCalculationPresetsEditor({value,invoice,disabled,onChange}:{value:PurchaseCalculationPolicy;invoice?:Record<string,unknown>|null;disabled?:boolean;onChange:(value:PurchaseCalculationPolicy)=>void}){
 const [starter,setStarter]=useState('standard');
 const update=(key:string,patch:Partial<PurchaseCalculationPreset>)=>onChange({...value,presets:value.presets.map(preset=>preset.key===key?{...preset,...patch}:preset)});
 function add(){
  const recipe=purchaseCalculationStarters.find(row=>row.key===starter)!;
  let index=1;while(value.presets.some(row=>row.key===recipe.key+'-'+index))index++;
  let name=recipe.name,suffix=2;
  while(value.presets.some(row=>row.name===name)){name=recipe.name+' ('+suffix+')';suffix++;}
  onChange({...value,presets:[...value.presets,{...recipe,key:recipe.key+'-'+index,name,steps:recipe.steps.map(step=>({...step,dependencies:[...step.dependencies]}))}]});
 }
 const problems=validateCalculationPolicy(value,invoice);
 return <fieldset className="janso-flow"><legend>Purchase calculation formulas</legend>
  <p>Create named starting recipes for supplier bills. Values remain editable on the bill within its effective entry rules. Each step declares the amount it uses.</p>
  <Select label="Default calculation formula" value={value.default_preset??''} disabled={disabled} options={[{value:'',label:'Choose on each bill'},...value.presets.map(row=>({value:row.key,label:row.name||'Unnamed preset'}))]} onChange={key=>onChange({...value,default_preset:key||null})}/>
  {value.presets.map((preset,presetIndex)=><section key={preset.key} className="janso-entry-workspace__panel janso-flow" aria-label={preset.name||'Calculation preset'}>
   <TextField label={'Formula '+(presetIndex+1)+' name'} value={preset.name} required maxLength={80} disabled={disabled} onChange={event=>update(preset.key,{name:event.target.value})}/>
   {!preset.steps.length&&<p>Standard calculation: line amounts, applicable tax, then configured rounding.</p>}
   <PurchaseCalculationExample preset={preset}/>
   {preset.steps.map((step,index)=><details key={step.key} open={!step.name.trim()||undefined} className="janso-entry-detail__group"><summary>Step {index+1}: {step.name||'New step'} · {step.input_kind==='PERCENT'?step.value+'%':step.value}</summary>
    <PurchaseCalculationStepFields step={step} prefix={preset.name+' step '+(index+1)} previous={preset.steps.slice(0,index)} disabled={disabled} onChange={patch=>update(preset.key,{steps:preset.steps.map(row=>row.key===step.key?{...row,...patch}:row)})}/>
    <div className="janso-entry-detail__pair">{[-1,1].map(direction=><Button key={direction} type="button" variant="ghost" disabled={disabled||index+direction<0||index+direction>=preset.steps.length} onClick={()=>{const steps=[...preset.steps];[steps[index],steps[index+direction]]=[steps[index+direction]!,steps[index]!];update(preset.key,{steps});}}>Move step {index+1} {direction<0?'up':'down'}</Button>)}</div>
    <Button type="button" variant="ghost" disabled={disabled} onClick={()=>update(preset.key,{steps:preset.steps.filter(row=>row.key!==step.key).map(row=>({...row,dependencies:row.dependencies.filter(key=>key!==step.key)}))})}>Remove step {index+1}</Button>
   </details>)}
   <div className="janso-entry-detail__pair"><Button type="button" variant="ghost" disabled={disabled||preset.steps.length>=32} onClick={()=>{
    let index=1;while(preset.steps.some(row=>row.key==='step-'+index))index++;
    update(preset.key,{steps:[...preset.steps,{...calculationStep('step-'+index),name:''}]});
   }}>Add calculation step</Button><Button type="button" variant="ghost" disabled={disabled} onClick={()=>onChange({...value,default_preset:value.default_preset===preset.key?null:value.default_preset,presets:value.presets.filter(row=>row.key!==preset.key)})}>Remove formula {preset.name}</Button></div>
  </section>)}
  <div className="janso-form-grid janso-entry-detail__pair"><Select label="Starting recipe" value={starter} disabled={disabled} options={purchaseCalculationStarters.map(row=>({value:row.key,label:row.name}))} onChange={setStarter}/><Button type="button" variant="ghost" disabled={disabled||value.presets.length>=20} onClick={add}>Add calculation formula</Button></div>
  {!!problems.length&&<Notice tone="danger" title="Check calculation formulas"><ul>{problems.map(problem=><li key={problem}>{problem}</li>)}</ul></Notice>}
  <Notice>Tax rates follow the company and supplier tax facts. Formula steps do not define statutory rates or override entry permissions.</Notice>
 </fieldset>;
}
