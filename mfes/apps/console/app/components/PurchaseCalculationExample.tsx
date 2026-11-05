'use client';
import {useFormatters} from '@janso/ui';
import {componentsFromPreset,type PurchaseCalculationPreset} from '../lib/purchase-calculation';
import {purchaseComponentPreview} from '../lib/purchase-workspace-details';
import {newPurchaseWorkspace} from '../lib/purchase-workspace';
import * as D from '../lib/fixed-decimal';

export function PurchaseCalculationExample({preset}:{preset:PurchaseCalculationPreset}){
 const {money}=useFormatters(),draft=newPurchaseWorkspace('2026-01-01');
 draft.details.components=componentsFromPreset(preset).map(step=>({...step,...(step.scope==='SELECTED_LINES'?{targets:['example']}:{})}));
 const result=purchaseComponentPreview(draft,[{key:'example',net:10000000n}],180000n);
 const show=(value:bigint|null)=>value===null?'Check steps':money(D.format(value),{display:'none'});
 const net=result.afterDiscounts!==null&&result.supplierCharges!==null?result.afterDiscounts+result.supplierCharges:null;
 const taxBase=result.taxAfterDiscounts!==null&&result.taxCharges!==null?result.taxAfterDiscounts+result.taxCharges:null;
 const tax=taxBase!==null?D.round(D.percent(taxBase,180000n),2):null;
 return <details className="janso-entry-detail__group"><summary>Formula example</summary>
  <p>Illustration: {show(10000000n)} before tax, with 18% supplier-charged tax. Actual bills use their verified tax facts and Accounting calculation.</p>
  <table className="janso-purchase-tax-table"><caption>Example calculation steps</caption><thead><tr><th>Step</th><th>Basis</th><th>Amount</th></tr></thead><tbody>{result.entries.map((entry,index)=><tr key={entry.id}><td>{preset.steps[index]?.name}</td><td>{show(entry.base)}</td><td>{show(entry.amount)}</td></tr>)}</tbody></table>
  <dl className="janso-purchase-figures"><div><dt>Commercial amount</dt><dd>{show(net)}</dd></div><div><dt>Tax</dt><dd>{show(tax)}</dd></div><div><dt>Supplier payable</dt><dd>{show(net!==null&&tax!==null?net+tax:null)}</dd></div></dl>
 </details>;
}
