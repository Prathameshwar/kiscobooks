import type {components} from '@janso/api-client/vouchers';
import type {CustomDefinition,CustomField,SearchSelectLoader} from '@janso/ui';
import {productFieldRequest as request} from './product-fields';
import {serviceCall,type ServiceRequest} from './service-call';
export const voucherCommandRequest=<T>(command:ServiceRequest)=>serviceCall<T>('/api/product-fields',{...command,service:'vouchers'},'voucher');
export type Native={readOnly?:boolean;properties?:Record<string,Native>;items?:Native;anyOf?:Native[];enum?:string[]};
export type FieldSet={native:Native;custom:{entity_type:string;definition:CustomDefinition;presentation?:{label?:string;help_text?:string|null};readOnly:boolean}[];configuration:{kind?:string;profile?:string;type_revision_id:string;policy:components['schemas']['Policy']};
  /** A saved voucher's field-set when its type can no longer give an edit view (retired type, unreadable configuration): why. */
  configuration_unavailable?:string};
export type Choice={id:string;name?:string;code?:string;sku?:string;row_version?:number;base_unit_id?:string;kind?:string;party_role?:string};
export function customFields(metadata:FieldSet,entity:string):CustomField[]{return metadata.custom.filter(row=>row.entity_type===entity).map(row=>({key:row.definition.key,label:row.presentation?.label||row.definition.key,help_text:row.presentation?.help_text,source:'custom',visible:row.definition.is_active,required:row.definition.validation.required,writable:!row.readOnly,custom:row.definition}));}
export function lookup(company:string,source:string,remember?:(rows:Choice[])=>void):SearchSelectLoader {
  return async({q,cursor,signal})=>{
    const service=['parties','accounts','account-groups'].includes(source)?'accounting':source==='voucher_types'?'vouchers':'catalog';
    if(!['items','units','parties','accounts','account-groups','voucher_types'].includes(source))throw new Error('Lookup is unavailable');
    const params=new URLSearchParams({limit:'50',...(source==='units'?{is_active:'true'}:{status:'ACTIVE'})});
    // Voucher types currently use indexed code-prefix search.
    if(q)params.set('q',q);if(cursor)params.set('cursor',cursor);
    const result=await request<{items:Choice[];next_cursor?:string|null;page?:{next_cursor:string|null}}>(service,'GET','/v1/companies/'+company+'/'+source.replace('_','-')+'?'+params,undefined,undefined,signal);
    remember?.(result.items);
    return {items:result.items.filter(row=>row.name||row.code||row.sku).map(row=>({id:row.id,label:row.name??row.code??row.sku??'',meta:row.code??row.sku})),nextCursor:result.page?.next_cursor??result.next_cursor??null};
  };
}
