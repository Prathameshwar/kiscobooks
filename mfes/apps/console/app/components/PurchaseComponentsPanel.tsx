'use client';

import { Button, Checkbox, Select, TextField, useFormatters } from '@janso/ui';
import { purchaseWorkspacePreview } from '../lib/purchase-workspace';
import { purchaseOrderedComponents, type PurchaseComponent } from '../lib/purchase-workspace-details';
import * as D from '../lib/fixed-decimal';
import type { PurchaseDetailEditorProps } from './PurchaseDetailEditor';
import {PurchaseCalculationPicker} from './PurchaseCalculationPicker';

export function PurchaseComponentsPanel({ draft, policy, setDetails, disabled, error, number }: PurchaseDetailEditorProps) {
  const { money } = useFormatters(), preview = purchaseWorkspacePreview(draft);
  const patch = (id: string, values: Partial<PurchaseComponent>) => setDetails(current => ({ ...current, components: current.components.map(component => component.id === id ? { ...component, ...values } : component) }));
  const add = (kind: PurchaseComponent['kind']) => setDetails(current => {
    let next=current.nextComponent;while(current.components.some(step=>step.id==='pc'+next))next++;
    return { ...current, nextComponent: next+1,
      components: [...current.components, { id: 'pc' + next, kind, purpose:kind==='DISCOUNT'?'DISCOUNT':'OTHER_CHARGE',label: '', basis: 'AMOUNT',basisRecipe:'AFTER_DISCOUNTS',amountBasis:'NET_EXCL_TAX',scope:'INVOICE', value: '0', targets: [], payable: true, taxTreatment: kind === 'DISCOUNT' ? 'INCLUDED' : 'UNRESOLVED' }] };
  });
  return <>
    <PurchaseCalculationPicker policy={policy.calculation} components={draft.details.components} disabled={disabled} onApply={components=>setDetails(current=>({...current,components}))}/>
    <p className="janso-entry-workspace__caption">Each step uses its declared basis and is counted once. Original amounts, prior discounts and selected steps can produce different results.</p>
    {draft.details.components.length === 0 ? <p>No document discounts or charges. Line discounts stay in the bill grid.</p> : null}
    {purchaseOrderedComponents(draft.details.components).map((component, index) => {
      const entry = preview.components.entries.find(item => item.id === component.id);
      return <fieldset key={component.id} className="janso-entry-detail__group" data-purchase-detail-field={`component-${component.id}`}>
        <legend>{component.kind === 'DISCOUNT' ? 'Discount' : 'Charge'} {index + 1}</legend>
        <TextField label={`Component ${index + 1} name`} value={component.label} disabled={disabled} maxLength={80} required
          error={error(`component-${component.id}`)} onChange={event => patch(component.id, { label: event.target.value })} />
        <div className="janso-form-grid janso-entry-detail__pair"><Select label={`Component ${index + 1} basis`} value={component.basis} disabled={disabled}
          options={[{ value: 'AMOUNT', label: 'Fixed amount' }, { value: 'PERCENT', label: 'Percentage of eligible base' }]}
          onChange={basis => patch(component.id, { basis: basis as PurchaseComponent['basis'] })} />
          {number(`component-value-${component.id}`, `Component ${index + 1} value`, component.value, value => patch(component.id, { value }), { quantity: component.basis === 'PERCENT', unit: component.basis === 'PERCENT' ? '%' : undefined })}</div>
        <div className="janso-entry-detail__checks"><Checkbox checked={component.scope!=='SELECTED_LINES'&&component.targets.length === 0} disabled={disabled} onChange={event => patch(component.id, {scope:event.target.checked?'INVOICE':'SELECTED_LINES', targets: event.target.checked ? [] : draft.lines.filter(line => line.subject).map(line => line.key) })}>All entered lines</Checkbox>
          {component.targets.length > 0||component.scope==='SELECTED_LINES' ? draft.lines.filter(line => line.subject).map((line, lineIndex) => <Checkbox key={line.key} checked={component.targets.includes(line.key)} disabled={disabled}
            onChange={event => { const targets = event.target.checked ? [...component.targets, line.key] : component.targets.filter(key => key !== line.key); patch(component.id, {scope:'SELECTED_LINES', targets }); }}>
            Line {lineIndex + 1}: {line.label}</Checkbox>) : null}</div>
        {component.targets.some(key => !draft.lines.some(line => line.key === key && line.subject)) ? <p className="janso-error">A selected line was removed. Select All entered lines or update the targets.</p> : null}
        <details className="janso-entry-detail__group"><summary>Calculation basis for component {index+1}</summary>
          {component.kind==='CHARGE'&&<Select label={`Component ${index+1} charge purpose`} value={component.purpose??'OTHER_CHARGE'} disabled={disabled} options={[{value:'PACKING',label:'Packing'},{value:'FREIGHT',label:'Freight'},{value:'HANDLING',label:'Handling'},{value:'INSURANCE',label:'Insurance'},{value:'OTHER_CHARGE',label:'Other charge'}]} onChange={value=>patch(component.id,{purpose:value as PurchaseComponent['purpose']})}/>}
          <Select label={`Component ${index+1} calculation basis`} value={component.basisRecipe??'AFTER_DISCOUNTS'} disabled={disabled} options={[{value:'ORIGINAL',label:'Original line amount'},{value:'AFTER_DISCOUNTS',label:'After line and preceding discounts'},{value:'AFTER_STEPS',label:'After line discounts and selected steps'}]} onChange={value=>patch(component.id,{basisRecipe:value as PurchaseComponent['basisRecipe'],dependencies:[]})}/>
          <Select label={`Component ${index+1} amount basis`} value={component.amountBasis??'NET_EXCL_TAX'} disabled={disabled} options={[{value:'NET_EXCL_TAX',label:'Amount excluding tax'},{value:'GROSS_INCL_TAX',label:'Amount including supplier-charged tax'}]} onChange={value=>patch(component.id,{amountBasis:value as PurchaseComponent['amountBasis'],...(value==='GROSS_INCL_TAX'?{taxTreatment:'INCLUDED' as const}:{})})}/>
          {component.basisRecipe==='AFTER_STEPS'&&<fieldset><legend>Component {index+1} preceding steps</legend>{purchaseOrderedComponents(draft.details.components).slice(0,index).map(previous=><Checkbox key={previous.id} checked={component.dependencies?.includes(previous.id)??false} disabled={disabled} onChange={event=>patch(component.id,{dependencies:event.target.checked?[...component.dependencies??[],previous.id]:(component.dependencies??[]).filter(key=>key!==previous.id)})}>{previous.label||'Unnamed step'}</Checkbox>)}</fieldset>}
        </details>
        {component.kind==='DISCOUNT'&&<Select label={`Component ${index+1} tax treatment`} value={component.taxTreatment} disabled={disabled||component.amountBasis==='GROSS_INCL_TAX'} options={[{value:'INCLUDED',label:'Changes assessable amount'},{value:'EXCLUDED',label:'Does not change assessable amount'}]} onChange={value=>patch(component.id,{taxTreatment:value as PurchaseComponent['taxTreatment']})}/>}
        {component.kind === 'CHARGE' ? <div className="janso-form-grid janso-entry-detail__pair">
          <Select label={`Component ${index + 1} payable treatment`} value={component.payable ? 'SUPPLIER' : 'LANDED'} disabled={disabled || policy.live}
            options={[{ value: 'SUPPLIER', label: 'Included in supplier bill' }, { value: 'LANDED', label: 'Additional cost only · outside supplier bill' }]}
            onChange={value => patch(component.id, { payable: value === 'SUPPLIER' })} />
          <Select label={`Component ${index + 1} tax treatment`} value={component.taxTreatment} disabled={disabled||component.amountBasis==='GROSS_INCL_TAX'}
            options={[{ value: 'UNRESOLVED', label: 'Unresolved · needs review' }, { value: 'INCLUDED', label: policy.live ? 'Included in assessable base' : 'Included in example tax base' }, { value: 'EXCLUDED', label: policy.live ? 'No change to assessable base' : 'Excluded from example tax base' }]}
            onChange={value => patch(component.id, { taxTreatment: value as PurchaseComponent['taxTreatment'] })} />
        </div> : null}
        <p className="janso-entry-workspace__caption">Eligible base: {entry?.base == null ? '—' : money(D.format(entry.base))} · Component amount: {entry?.amount == null ? '—' : money(D.format(entry.amount))}</p>
        {entry?.requiresOwner&&<p>Save and calculate to verify the supplier-charged tax in this basis.</p>}
        {!disabled ? <div className="janso-entry-detail__pair">{[-1,1].map(direction=><Button key={direction} variant="ghost" type="button" disabled={index+direction<0||index+direction>=draft.details.components.length} onClick={()=>setDetails(current=>{const components=[...purchaseOrderedComponents(current.components)].map(step=>({...step,basisRecipe:step.basisRecipe??'AFTER_DISCOUNTS' as const}));[components[index],components[index+direction]]=[components[index+direction]!,components[index]!];return {...current,components};})}>Move component {index+1} {direction<0?'up':'down'}</Button>)}<Button variant="ghost" type="button" onClick={() => setDetails(current => ({ ...current, components: current.components.filter(item => item.id !== component.id) }))}>Remove component {index + 1}</Button></div> : null}
      </fieldset>;
    })}
    {!disabled ? <div className="janso-entry-detail__pair">{policy.discountsAllowed !== false ? <Button variant="ghost" type="button" onClick={() => add('DISCOUNT')}>Add document discount</Button> : null}{policy.chargesAllowed !== false ? <Button variant="ghost" type="button" onClick={() => add('CHARGE')}>Add charge</Button> : null}</div> : null}
    <p className="janso-entry-workspace__caption">{policy.live ? 'Adjustments remain unsaved until the bill is saved. Accounting calculates and validates the persisted revision.' : 'These treatments belong to the supplied example. Tax rates are read-only in Tax details. Unresolved or unsupported treatment leaves the bill total unavailable.'}</p>
  </>;
}
