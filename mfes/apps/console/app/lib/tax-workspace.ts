import type {BookDefinition} from './book-workspace';
export const taxReportCodes=['INVOICE_TAX_REGISTER','INVOICE_CREDIT_REGISTER','TAX_GL_BRIDGE'] as const;
export type TaxReportCode=typeof taxReportCodes[number];
export const isTaxReport=(code:string|undefined):code is TaxReportCode=>taxReportCodes.some(value=>value===code);
const taxAcronyms=new Set(['CGST','SGST','IGST','UTGST','GST','VAT','RCM','ITC','TDS','TCS']);
export function taxValueLabel(value:string):string{
 return value.split('_').map((word,index)=>taxAcronyms.has(word.toUpperCase())?word.toUpperCase():index===0?word.charAt(0).toUpperCase()+word.slice(1).toLowerCase():word.toLowerCase()).join(' ');
}
type TaxDefinition=BookDefinition&{columns:readonly string[]};
export const taxWorkspaces:Record<TaxReportCode,TaxDefinition>={
 INVOICE_TAX_REGISTER:{code:'INVOICE_TAX_REGISTER',title:'Invoice Tax Register',overline:'Recorded invoice tax',resultNoun:'tax components',lede:'Review invoice tax, recorded taxable values and the date basis used for this period.',focus:'Taxable value counts each supply once across its tax components. Totals show recorded tax; statutory return preparation is separate.',empty:'No recorded invoice tax matches this period and selection.',primaryFilters:['date_from','date_to','date_basis','search'],columns:['period','posting_date','bill_reference','account_name','invoice_kind','tax_code','component_taxable_basis','tax_amount','currency']},
 INVOICE_CREDIT_REGISTER:{code:'INVOICE_CREDIT_REGISTER',title:'Input Tax Credit Register',overline:'Recorded credit positions',resultNoun:'credit rows',lede:'Review closing tax credit positions and the committed events recorded during the selected period.',focus:'Closing positions are separate from period events. Purchase tax alone does not establish a lawful claim.',empty:'No recorded purchase tax credits match this selection.',primaryFilters:['date_from','date_to','party_id','search'],columns:['period','row_kind','bill_reference','account_name','tax_code','recorded_tax','pending','eligible_unclaimed','claimed','suspended','blocked','currency']},
 TAX_GL_BRIDGE:{code:'TAX_GL_BRIDGE',title:'Tax to Ledger Reconciliation',overline:'Verified tax posting evidence',resultNoun:'tax ledger entries',lede:'Trace recorded invoice and credit-event tax effects to their posted ledger entries.',focus:'Debit less credit shows movement in the selected tax accounts. Source lineage is verified before publication.',empty:'No verified invoice tax ledger entries match this period and selection.',primaryFilters:['date_from','date_to','date_basis','tax_ledger_id','tax_purpose','search'],columns:['period','posting_date','bill_reference','account_name','tax_code','tax_purpose','side','amount','currency']},
};
export const taxParameterLabels:Record<string,string>={date_from:'From date',date_to:'To date',date_basis:'Date basis',search:'Search invoices and tax',tax_ledger_id:'Tax ledger',tax_purpose:'Tax posting purpose',tax_code:'Tax component code',company_registration_id:'Company registration reference',party_id:'Customer or supplier',account_id:'Party ledger',invoice_id:'Invoice reference',currency:'Currency code'};
export type TaxSummary={code:string;comparison_present?:boolean;row_count:number;invoice_count:number;component_count:number;position_count?:number;event_count?:number;ledger_count?:number;amounts:Record<string,Record<string,string>>;event_amounts?:Record<string,Record<string,string>>;mode?:'POSITIONS'|'EVENTS'|'BOTH';verification:string};
export const taxAmountColumns:Record<TaxReportCode,readonly [string,string][]>= {
 INVOICE_TAX_REGISTER:[['taxable_value','Net taxable value'],['outward_tax','Outward tax'],['inward_tax','Inward tax'],['tax_amount','Net recorded tax']],
 INVOICE_CREDIT_REGISTER:[['recorded_tax','Recorded tax'],['pending','Pending evidence'],['eligible_unclaimed','Eligible, unclaimed'],['claimed','Claimed'],['suspended','Suspended'],['blocked','Blocked'],['rcm_discharged','RCM discharged']],
 TAX_GL_BRIDGE:[['debit','Debit'],['credit','Credit'],['net','Net debit movement']],
};
