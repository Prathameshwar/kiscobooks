import * as D from './fixed-decimal';
import type {PurchaseComponent} from './purchase-workspace-details';

export type PurchaseCalculationStep = {
 key:string;name:string;purpose:'DISCOUNT'|'FREIGHT'|'PACKING'|'INSURANCE'|'HANDLING'|'OTHER_CHARGE';
 input_kind:'FIXED'|'PERCENT';value:string;scope:'INVOICE'|'SELECTED_LINES';
 amount_basis:'NET_EXCL_TAX'|'GROSS_INCL_TAX';basis_recipe:'ORIGINAL'|'AFTER_DISCOUNTS'|'AFTER_STEPS';
 dependencies:string[];tax_treatment:'ASSESSABLE'|'NO_CHANGE';
};
export type PurchaseCalculationPreset={key:string;name:string;steps:PurchaseCalculationStep[]};
export type PurchaseCalculationPolicy={presets:PurchaseCalculationPreset[];default_preset:string|null};
export const emptyCalculationPolicy=():PurchaseCalculationPolicy=>({presets:[],default_preset:null});
export function readCalculationPolicy(value:Partial<PurchaseCalculationPolicy>|null|undefined):PurchaseCalculationPolicy{
 return {default_preset:value?.default_preset??null,presets:(value?.presets??[]).map(preset=>({...preset,steps:(preset.steps??[]).map(step=>({...calculationStep(step.key),...step,value:step.value??'0',dependencies:[...step.dependencies??[]]}))}))};
}
export function calculationStep(key:string,purpose:PurchaseCalculationStep['purpose']='DISCOUNT'):PurchaseCalculationStep{
 return {key,name:purpose==='DISCOUNT'?'Trade discount':purpose==='FREIGHT'?'Freight':'Packing',purpose,input_kind:purpose==='FREIGHT'?'FIXED':'PERCENT',value:purpose==='DISCOUNT'?'10':purpose==='FREIGHT'?'100':'2',scope:'INVOICE',amount_basis:'NET_EXCL_TAX',basis_recipe:'AFTER_DISCOUNTS',dependencies:[],tax_treatment:'ASSESSABLE'};
}
export const purchaseCalculationStarters:PurchaseCalculationPreset[]=[
 {key:'standard',name:'Standard purchase',steps:[]},
 {key:'sequential',name:'Two-stage trade discount',steps:[calculationStep('trade'),{...calculationStep('additional'),name:'Additional discount',value:'5'}]},
 {key:'original',name:'Discounts on original amount',steps:[{...calculationStep('trade'),basis_recipe:'ORIGINAL'},{...calculationStep('additional'),name:'Additional discount',value:'5',basis_recipe:'ORIGINAL'}]},
 {key:'freight',name:'Discount, packing and freight',steps:[calculationStep('trade'),calculationStep('packing','PACKING'),calculationStep('freight','FREIGHT')]},
 {key:'inclusive',name:'Discount on tax-inclusive amount',steps:[{...calculationStep('trade'),amount_basis:'GROSS_INCL_TAX'}]},
];
export function validateCalculationPolicy(value:PurchaseCalculationPolicy,invoice?:Record<string,unknown>|null):string[]{
 const errors:string[]=[],presets=new Set<string>(),names=new Set<string>();
 if(value.presets.length>20)errors.push('Use at most 20 calculation presets.');
 for(const preset of value.presets){
  if(!/^[a-z][a-z0-9_-]{0,39}$/.test(preset.key)||presets.has(preset.key))errors.push('Preset identities must be valid and distinct.');
  presets.add(preset.key);
  if(!preset.name.trim()||preset.name.length>80)errors.push('Enter a preset name up to 80 characters.');
  const name=preset.name.trim().split(/\s+/).join(' ').toLowerCase();
  if(name&&names.has(name))errors.push('Give every preset a different name.');
  names.add(name);
  if(preset.steps.length>32)errors.push('Use at most 32 steps per preset.');
  const preceding=new Set<string>();
  // Accounting caps the total discount, so a preset's discounts are summed against the limit.
  let percent=0n,fixed=0n;
  for(const step of preset.steps){
   if(invoice){
    const choiceAllowed=(field:string,choice:string)=>!Array.isArray(invoice[field])||(invoice[field] as unknown[]).includes(choice);
    if(!choiceAllowed('allowed_scopes',step.scope)||!choiceAllowed('allowed_component_inputs',step.input_kind)||!choiceAllowed('allowed_price_bases',step.amount_basis))errors.push('A formula uses a basis, input or scope excluded by these invoice rules.');
    if(step.purpose==='DISCOUNT'){
     if(!invoice.manual_discounts_allowed)errors.push('Allow Purchase discounts before adding discount steps.');
     if(!choiceAllowed('discount_input_kinds',step.input_kind)||!choiceAllowed('discount_amount_bases',step.amount_basis))errors.push('A discount uses a choice excluded by these invoice rules.');
     const maximum=D.parse(String(step.input_kind==='PERCENT'?invoice.max_discount_pct??100:invoice.max_discount_amount??'999999999999999.9999'));
     const entered=D.parse(step.value);
     if(entered!==null){if(step.input_kind==='PERCENT')percent+=entered;else fixed+=entered;}
     if(maximum!==null&&entered!==null&&(step.input_kind==='PERCENT'?percent:fixed)>maximum)errors.push('The discounts in a formula together exceed the configured discount limit.');
     if(invoice.discount_compounding_allowed===false&&step.basis_recipe!=='ORIGINAL')errors.push('These invoice rules allow discounts on the original amount only.');
    }else if(!invoice.charges_allowed)errors.push('Allow Purchase charges before adding charge steps.');
   }
   if(!step.name.trim()||step.name.length>80)errors.push('Enter a name for every calculation step.');
   if(!/^[a-z][a-z0-9_-]{0,39}$/.test(step.key)||preceding.has(step.key))errors.push('Step identities must be valid and distinct.');
   const amount=D.parse(step.value);
   if(amount===null||amount<0n||amount>9999999999999999999n||step.input_kind==='PERCENT'&&amount>1000000n)errors.push('Enter a non-negative value; percentages cannot exceed 100.');
   if(step.basis_recipe==='AFTER_STEPS'&&(!step.dependencies.length||step.dependencies.some(key=>!preceding.has(key))||new Set(step.dependencies).size!==step.dependencies.length))errors.push('Choose distinct preceding steps for the calculation basis.');
   if(step.basis_recipe!=='AFTER_STEPS'&&step.dependencies.length)errors.push('Named steps require the after-selected-steps basis.');
   if(step.amount_basis==='GROSS_INCL_TAX'&&step.tax_treatment!=='ASSESSABLE')errors.push('Tax-inclusive adjustments must change the assessable base.');
   preceding.add(step.key);
  }
  if(invoice&&(preset.steps.length>Number(invoice.max_components??200)||preset.steps.filter(step=>step.purpose==='DISCOUNT').length>Number(invoice.max_discount_components??200)))errors.push('A formula exceeds the configured adjustment count.');
 }
 if(invoice===null&&value.presets.length)errors.push('Enable purchase invoice entry to use calculation formulas.');
 if(value.default_preset!==null&&!presets.has(value.default_preset))errors.push('Choose an existing default preset.');
 return [...new Set(errors)];
}
export function componentsFromPreset(preset:PurchaseCalculationPreset):PurchaseComponent[]{
 return preset.steps.map(step=>({id:step.key,label:step.name,kind:step.purpose==='DISCOUNT'?'DISCOUNT':'CHARGE',purpose:step.purpose,basis:step.input_kind==='FIXED'?'AMOUNT':'PERCENT',value:step.value,targets:[],payable:true,taxTreatment:step.tax_treatment==='ASSESSABLE'?'INCLUDED':'EXCLUDED',amountBasis:step.amount_basis,basisRecipe:step.basis_recipe,dependencies:[...step.dependencies],scope:step.scope,presetKey:preset.key}));
}
/** Every contributing adjustment is named: depending only on the last step loses earlier discounts. */
export function componentDependencies(component:PurchaseComponent,preceding:readonly PurchaseComponent[],lineDiscountKeys:readonly string[]=[]):string[]{
 if(component.basisRecipe==='ORIGINAL')return [];
 const rows=lineDiscountKeys.filter(id=>!component.targets.length||component.targets.includes(id.slice(9)));
 if(component.basisRecipe==='AFTER_STEPS')return [...rows,...component.dependencies??[]];
 return [...rows,...preceding.filter(step=>step.kind==='DISCOUNT'&&(!component.targets.length||!step.targets.length||step.targets.some(key=>component.targets.includes(key)))).map(step=>step.id)];
}
export function componentRecipeProblem(component:PurchaseComponent,preceding:readonly PurchaseComponent[],lineDiscountKeys:readonly string[]=[]):string|null{
 const dependencies=componentDependencies(component,preceding,lineDiscountKeys);
 const available=new Set([...preceding.map(step=>step.id),...lineDiscountKeys]);
 if(component.basisRecipe==='AFTER_STEPS'&&!component.dependencies?.length)return 'Choose at least one preceding calculation step.';
 if(dependencies.length>32)return 'A calculation basis can reference at most 32 preceding adjustments.';
 if(new Set(dependencies).size!==dependencies.length||dependencies.some(key=>!available.has(key)))return 'Choose distinct preceding calculation steps; a referenced step was removed or moved.';
 if(new Set(component.targets).size!==component.targets.length)return 'Choose distinct lines for this adjustment.';
 if((component.scope==='SELECTED_LINES'||component.scope==='LINE')&&!component.targets.length)return 'Choose the lines for this adjustment.';
 if(component.amountBasis==='GROSS_INCL_TAX'&&component.taxTreatment!=='INCLUDED')return 'A tax-inclusive adjustment must change the assessable base.';
 if(component.purpose&&((component.kind==='DISCOUNT')!==(component.purpose==='DISCOUNT')))return 'The adjustment purpose does not match its discount or charge treatment.';
 const value=D.parse(component.value);
 if(value===null||value<0n||value>9999999999999999999n||component.basis==='PERCENT'&&value>1000000n)return 'Enter a non-negative value; percentages cannot exceed 100.';
 return null;
}
export function componentEvidence(component:PurchaseComponent):string{
 return JSON.stringify({v:1,label:component.label.trim(),preset:component.presetKey??null,recipe:component.basisRecipe??'AFTER_DISCOUNTS'});
}
export function readComponentEvidence(value:string):{label:string;preset?:string;recipe?:PurchaseComponent['basisRecipe']}{
 try{const data:unknown=JSON.parse(value);if(data&&typeof data==='object'&&'v'in data&&data.v===1&&'label'in data&&typeof data.label==='string'){
  const row=data as Record<string,unknown>;return {label:row.label as string,...(typeof row.preset==='string'?{preset:row.preset}:{}),...(['ORIGINAL','AFTER_DISCOUNTS','AFTER_STEPS'].includes(String(row.recipe))?{recipe:row.recipe as PurchaseComponent['basisRecipe']}:{})};
 }}catch{/* Older revisions retain their plain supplier evidence. */}return {label:value};
}
