'use client';
import {useState} from 'react';
import {Button,Modal,Notice,Select} from '@janso/ui';
import {componentsFromPreset,type PurchaseCalculationPolicy} from '../lib/purchase-calculation';
import type {PurchaseComponent} from '../lib/purchase-workspace-details';

export function PurchaseCalculationPicker({policy,components,disabled,onApply}:{policy?:PurchaseCalculationPolicy;components:readonly PurchaseComponent[];disabled?:boolean;onApply:(components:PurchaseComponent[])=>void}){
 const [choice,setChoice]=useState<string>(),[confirm,setConfirm]=useState(false);
 const saved=components.length&&components.every(step=>step.presetKey===components[0]!.presetKey)?components[0]!.presetKey:undefined;
 const selected=choice??saved??policy?.default_preset??'';
 const preset=policy?.presets.find(row=>row.key===selected);
 if(!policy?.presets.length)return null;
 const apply=()=>{if(preset){onApply(componentsFromPreset(preset));setConfirm(false);}};
 return <div className="janso-flow"><div className="janso-form-grid janso-entry-detail__pair">
  <Select label="Calculation formula" value={selected} disabled={disabled} options={[{value:'',label:'Custom supplier bill'},...policy.presets.map(row=>({value:row.key,label:row.name})),...(saved&&!policy.presets.some(row=>row.key===saved)?[{value:saved,label:'Saved bill formula'}]:[])]} onChange={setChoice}/>
  <Button type="button" variant="ghost" disabled={disabled||!preset} onClick={()=>components.length?setConfirm(true):apply()}>Apply calculation formula</Button>
 </div>{preset&&<p>{preset.steps.length?`${preset.steps.length} calculation steps. Choose Apply calculation formula, then review values and selected lines against the supplier invoice.`:'Choose Apply calculation formula for standard line amounts and applicable tax, with no additional formula steps.'}</p>}
 {saved&&<Notice>The saved bill retains its own values and calculation bases. Applying a formula replaces its current discount and charge steps.</Notice>}
 <Modal open={confirm} title="Replace discount and charge steps?" onClose={()=>setConfirm(false)} footer={<><Button type="button" variant="ghost" onClick={()=>setConfirm(false)}>Keep current steps</Button><Button type="button" onClick={apply}>Apply formula</Button></>}><p>Replace the current discount and charge steps with {preset?.name}. Item quantities, rates and supplier evidence remain as entered.</p></Modal>
 </div>;
}
