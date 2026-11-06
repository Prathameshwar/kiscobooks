import {describe,expect,it} from 'vitest';
import {componentsFromPreset,purchaseCalculationStarters,componentDependencies,validateCalculationPolicy} from '../app/lib/purchase-calculation';
import {blankPurchaseLine,newPurchaseWorkspace,purchaseWorkspacePreview,type PurchaseMode} from '../app/lib/purchase-workspace';
import {purchaseComponentPreview} from '../app/lib/purchase-workspace-details';
import {purchaseInput,purchaseFromVoucher,type PurchaseBinding} from '../app/lib/purchase-api';
import {company,draft as native,metadata as baseMetadata} from './purchase-entry-fixtures';

function sample(mode:PurchaseMode='ACCOUNTS'){
 const draft=newPurchaseWorkspace('2026-10-30');draft.mode=mode;
 draft.lines=[{...blankPurchaseLine('p1',mode==='ACCOUNTS'?'ACCOUNT':'ITEM'),subject:'verified',billed:'10',received:'10',rate:'100',amount:'1000'}];
 return draft;
}
describe('declared Purchase calculation recipes',()=>{
 it.each(['ACCOUNTS','ITEMS','MIXED'] as const)('calculates sequential discounts once for %s',mode=>{
  const draft=sample(mode);draft.details.components=componentsFromPreset(purchaseCalculationStarters[1]!);
  const result=purchaseWorkspacePreview(draft);expect(result.components.afterDiscounts).toBe(8550000n);
  expect(result.components.entries.map(row=>row.amount)).toEqual([1000000n,450000n]);
 });
 it('distinguishes original amounts, row discounts and selected preceding adjustments',()=>{
  const draft=sample();draft.lines[0]!.discount='100';draft.details.components=componentsFromPreset(purchaseCalculationStarters[2]!);
  expect(purchaseWorkspacePreview(draft).components.afterDiscounts).toBe(7500000n);
  draft.details.components=componentsFromPreset(purchaseCalculationStarters[1]!);
  expect(purchaseWorkspacePreview(draft).components.afterDiscounts).toBe(7695000n);
 });
 it('uses every earlier discount but does not automatically compound packing and freight',()=>{
  const draft=sample();draft.details.components=componentsFromPreset(purchaseCalculationStarters[3]!);
  const result=purchaseWorkspacePreview(draft).components;
  expect(result.entries.map(row=>row.base)).toEqual([10000000n,9000000n,9000000n]);
  expect(result.afterDiscounts!+result.supplierCharges!).toBe(10180000n);
  expect(componentDependencies(draft.details.components[2]!,draft.details.components.slice(0,2))).toEqual(['trade']);
 });
 it('extracts a tax-inclusive discount from verified illustrative tax without inventing a rate',()=>{
  const draft=sample();draft.details.components=componentsFromPreset(purchaseCalculationStarters[4]!);
  const known=purchaseComponentPreview(draft,[{key:'p1',net:10000000n}],180000n);
  expect(known.entries[0]!.base).toBe(11800000n);expect(known.entries[0]!.amount).toBe(1180000n);
  expect(known.afterDiscounts).toBe(9000000n);
  const missing=purchaseComponentPreview(draft,[{key:'p1',net:10000000n}]);
  expect(missing.entries[0]!.amount).toBeNull();expect(missing.entries[0]!.requiresOwner).toBe(true);
 });
 it('rejects missing dependencies, excessive total reductions and mismatched selected lines',()=>{
  const draft=sample();draft.details.components=componentsFromPreset(purchaseCalculationStarters[1]!);
  draft.details.components[1]!.basisRecipe='AFTER_STEPS';draft.details.components[1]!.dependencies=['missing'];
  expect(purchaseWorkspacePreview(draft).components.entries[1]!.amount).toBeNull();
  draft.details.components=componentsFromPreset(purchaseCalculationStarters[2]!);for(const step of draft.details.components)step.value='80';
  expect(purchaseWorkspacePreview(draft).components.afterDiscounts).toBeNull();
 });
 it('checks the discounts in one formula together against the configured limit',()=>{
  const preset=structuredClone(purchaseCalculationStarters[2]!);
  const invoice={manual_discounts_allowed:true,max_discount_pct:'12'};
  expect(validateCalculationPolicy({presets:[preset],default_preset:null},invoice)).toContain('The discounts in a formula together exceed the configured discount limit.');
  expect(validateCalculationPolicy({presets:[preset],default_preset:null},{...invoice,max_discount_pct:'15'})).toEqual([]);
  const fixed=structuredClone(preset);for(const step of fixed.steps){step.input_kind='FIXED';step.value='60';}
  expect(validateCalculationPolicy({presets:[fixed],default_preset:null},{manual_discounts_allowed:true,max_discount_amount:'100'})).toHaveLength(1);
 });
 it('requires distinct formula names, ignoring case and spacing',()=>{
  const first=structuredClone(purchaseCalculationStarters[0]!),second={...structuredClone(first),key:'other',name:'  standard   PURCHASE '};
  expect(validateCalculationPolicy({presets:[first,second],default_preset:null})).toEqual(['Give every preset a different name.']);
 });
 it('blocks formula expressions, missing preceding steps and invalid defaults',()=>{
  const preset=structuredClone(purchaseCalculationStarters[1]!);preset.steps[1]!.basis_recipe='AFTER_STEPS';preset.steps[1]!.dependencies=['future'];
  expect(validateCalculationPolicy({presets:[preset],default_preset:'missing'})).toHaveLength(2);
 });
});

it('persists cumulative native dependencies and preserves them when reloading a bill',()=>{
 const metadata=structuredClone(baseMetadata);
 Object.assign(metadata.native.properties!,Object.fromEntries(['document_date','credit_terms_date','currency','narration','mode','lines','attachments','links','custom_fields'].map(key=>[key,{}])));
 metadata.native.properties!.invoice!.anyOf![0]!.properties!.components={};
 metadata.configuration.policy.invoice!.manual_discounts_allowed=true;
 const draft=sample();Object.assign(draft,{supplier:native.party!.id,payable:native.payable!.id,invoice:'INV-1'});Object.assign(draft.lines[0]!,{subject:native.supplies[0]!.account!.id,description:'Consulting services'});
 draft.details.components=componentsFromPreset(purchaseCalculationStarters[1]!);
 draft.details.components.push({...draft.details.components[1]!,id:'third',value:'2'});
 const binding:PurchaseBinding={company,currency:'INR',metadata,keys:new Map(),partyKey:native.partyLineKey,sources:new Map([native.party!,native.payable!,native.supplies[0]!.account!].map(source=>[source.id,source]))};
 const wire=purchaseInput(draft,binding),steps=wire.invoice!.components!;
 expect(steps[2]!.dependencies).toEqual([steps[0]!.component_key,steps[1]!.component_key]);
 expect(purchaseInput(draft,binding).invoice!.components).toEqual(steps);
 const voucher={...wire,id:'10000000-0000-7000-8000-000000000090',company_id:company,kind:'PURCHASE',profile:'STANDARD',status:'DRAFT',revision_id:'10000000-0000-7000-8000-000000000091',row_version:1,revision_number:1,lines:[],attachments:[],links:[],custom_fields:{}} as Parameters<typeof purchaseFromVoucher>[0];
 const loaded=purchaseFromVoucher(voucher,company,metadata);
 const rebound=loaded.binding;
 expect(purchaseInput(loaded.draft,rebound).invoice!.components!.map(step=>({purpose:step.purpose,value:Number(step.value),dependencies:step.dependencies,scope:step.scope,amount_basis:step.amount_basis}))).toEqual(steps.map(step=>({purpose:step.purpose,value:Number(step.value),dependencies:step.dependencies,scope:step.scope,amount_basis:step.amount_basis})));
});

it('includes prior charges in an explicitly selected discount basis and protects both balances',()=>{
 const draft=sample();draft.details.components=[
  {...componentsFromPreset(purchaseCalculationStarters[3]!)[2]!,id:'freight',value:'100',basisRecipe:'ORIGINAL'},
  {...componentsFromPreset(purchaseCalculationStarters[1]!)[0]!,id:'trade',value:'75',basisRecipe:'AFTER_STEPS',dependencies:['freight']},
 ];
 const preview=purchaseComponentPreview(draft,[{key:'p1',net:1000000n}],180000n);
 expect(preview.entries.map(row=>row.amount)).toEqual([1000000n,1500000n]);
 expect(preview.afterDiscounts!+preview.supplierCharges!).toBe(500000n);
 draft.details.components[0]!.taxTreatment='EXCLUDED';
 expect(purchaseComponentPreview(draft,[{key:'p1',net:1000000n}]).entries[1]!.amount).toBeNull();
});
