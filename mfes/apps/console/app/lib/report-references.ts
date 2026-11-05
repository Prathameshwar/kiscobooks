import type {SearchSelectLoader,SearchSelectOption} from '@janso/ui';
import {productFieldRequest as request} from './product-fields';
import {trackingId} from './stock-tracking-resources';

export type ReportReferenceSource='accounts'|'account-groups'|'parties'|'items'|'item-groups'|'warehouses'|'batches'|'voucher-types';
type Reference={id:string;company_id?:string;name?:string;code?:string;sku?:string;kind?:string};
const owner=(source:ReportReferenceSource)=>source==='voucher-types'?'vouchers' as const:['accounts','account-groups','parties','batches'].includes(source)?'accounting' as const:'catalog' as const;
const path=(company:string,source:ReportReferenceSource)=>'/v1/companies/'+company+'/'+(source==='batches'?'stock-tracking/batches':source);
function option(row:Reference,company:string):SearchSelectOption {
  if(!trackingId.test(row.id)||(row.company_id!==undefined&&row.company_id!==company))throw new Error('Report reference ownership could not be verified.');
  return {id:row.id,label:row.name??row.code??row.sku??'Protected record',meta:row.name?row.code??row.sku:undefined};
}
/** Report filters include historical/inactive masters; execution validates the frozen source. */
export function reportLookup(company:string,source:ReportReferenceSource,item?:string,generation?:string,accountKind?:'BANK'|'CASH'):SearchSelectLoader {
  return async({q,cursor,signal})=>{
    if(generation && ['items','item-groups','warehouses','batches'].includes(source)) {
      const page=await frozenReferences(company,source,generation,{q,cursor,item},signal);
      return {items:page.items.map(row=>option(row,company)),nextCursor:page.next_cursor};
    }
    const query=q.trim();if(query.length>200)throw new Error('Shorten the reference search to 200 characters.');
    const params=new URLSearchParams({limit:'50'});
    if(source==='accounts'&&accountKind)params.set('kind',accountKind);
    if(query.length>=2)params.set('q',query);if(cursor)params.set('cursor',cursor);
    if(source==='batches'&&item){if(!trackingId.test(item))throw new Error('Choose a valid product before filtering its batches.');params.set('item_id',item);}
    const page=await request<{items:Reference[];page:{next_cursor:string|null}}> (owner(source),'GET',path(company,source)+'?'+params,undefined,undefined,signal);
    if(!Array.isArray(page.items)||page.items.length>50||!page.page||page.page.next_cursor!==null&&typeof page.page.next_cursor!=='string')throw new Error('Report references could not be loaded.');
    return {items:page.items.map(row=>option(row,company)),nextCursor:page.page.next_cursor};
  };
}
export async function reportReference(company:string,source:ReportReferenceSource,id:string,signal:AbortSignal,generation?:string,item?:string,accountKind?:'BANK'|'CASH'):Promise<SearchSelectOption>{
  if(!trackingId.test(id))throw new Error('The retained report reference is invalid.');
  if(generation && ['items','item-groups','warehouses','batches'].includes(source)) {
    const page=await frozenReferences(company,source,generation,{id,item},signal);
    if(page.items.length!==1||page.items[0].id!==id)throw new Error('This reference is outside the frozen inventory snapshot.');
    return option(page.items[0],company);
  }
  const row=await request<Reference>(owner(source),'GET',path(company,source)+'/'+id,undefined,undefined,signal);
  if(row.id!==id||row.company_id!==company)throw new Error('Report reference ownership could not be verified.');
  if(source==='accounts'&&accountKind&&row.kind!==accountKind)throw new Error('Choose a '+accountKind.toLowerCase()+' account.');
  return option(row,company);
}

async function frozenReferences(company:string,source:ReportReferenceSource,generation:string,filter:{q?:string;cursor?:string|null;id?:string;item?:string},signal:AbortSignal) {
  const params=new URLSearchParams({kind:source==='items'?'ITEM':source==='warehouses'?'LOCATION':source==='batches'?'LOT':'GROUP',limit:'50'});
  if(filter.item){if(!trackingId.test(filter.item))throw new Error('Choose a valid product before filtering its batches.');params.set('item_id',filter.item);}
  if(filter.q)params.set('q',filter.q.trim());if(filter.cursor)params.set('cursor',filter.cursor);if(filter.id)params.set('object_id',filter.id);
  const page=await request<{generation_id:string;items:Reference[];next_cursor:string|null}>('reports','GET','/v2/companies/'+company+'/report-generations/'+generation+'/inventory?'+params,undefined,undefined,signal);
  if(page.generation_id!==generation||!Array.isArray(page.items)||page.items.length>50||page.next_cursor!==null&&(typeof page.next_cursor!=='string'||page.next_cursor.length>4096))throw new Error('Frozen stock references could not be verified.');
  return page;
}
