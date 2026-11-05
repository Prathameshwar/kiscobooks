"use client";
import {useMemo,useRef,useState} from 'react';
import {Button,CustomFields,SearchSelect,TextField,customPatch} from '@janso/ui';
import type {components} from '@janso/api-client/vouchers';
import type {components as catalogComponents} from '@janso/api-client/catalog';
import {productFieldRequest as request} from '../lib/product-fields';
import {customFields,lookup,type Choice,type FieldSet} from '../lib/voucher-fields';
import {stockAction} from '../lib/voucher-stock';
import {VoucherUnitReference} from './VoucherUnitReference';
type Line=components['schemas']['LineInput'];
type Scan=catalogComponents['schemas']['BarcodeResolution'];
export function VoucherItems({company,currency,metadata,lines,onChange,disabled,asOf='',canScan=false}:{company:string;currency:string;metadata:FieldSet;lines:Line[];onChange:(lines:Line[])=>void;disabled:boolean;asOf?:string;canScan?:boolean}){
  const choices=useRef(new Map<string,Choice>());
  const [scanValues,setScanValues]=useState<Record<string,string>>({});
  const [scanMessages,setScanMessages]=useState<Record<string,string>>({});
  const [scanBusy,setScanBusy]=useState(false);
  const items=useMemo(()=>lookup(company,'items',rows=>rows.forEach(row=>choices.current.set(row.id,row))),[company]);
  const lineSchema=metadata.native.properties?.lines;
  const native=lineSchema?.items?.properties?.item?.properties??{};
  const fields=customFields(metadata,'vouchers.voucher_item');
  const planned=metadata.configuration.kind==='SALES_ORDER'||metadata.configuration.kind==='PURCHASE_ORDER'||(metadata.configuration.kind==='STOCK_JOURNAL'&&metadata.configuration.profile==='REQUISITION');
  const physical=!!stockAction(metadata.configuration.kind,metadata.configuration.profile)&&!!metadata.configuration.policy.stock;
  const permitted=!!lineSchema&&!lineSchema.readOnly&&!metadata.configuration.policy.forbidden_sections?.includes('ITEMS');
  if(!permitted)return null;
  const locked=disabled||scanBusy;
  function update(index:number,next:Line){onChange(lines.map((line,i)=>i===index?next:line));}
  async function scan(index:number,line:Line){
    const value=scanValues[line.line_key]??'';if(!value||!asOf)return;
    setScanBusy(true);setScanMessages(current=>({...current,[line.line_key]:''}));
    try{
      if(value!==value.trim())throw new Error('Barcode has leading or trailing whitespace. Scan again.');
      const result=await request<Scan>('catalog','POST','/v1/companies/'+company+'/barcodes/resolve',{scan_value:value,as_of:asOf});
      if(result.lot_hint||result.expiry_yymmdd_hint||result.serial_hint)throw new Error('This scan contains lot, expiry or serial data that this voucher form cannot record.');
      if(physical&&result.usage_role!=='BASE')throw new Error('This barcode identifies an alternate product unit. For this stock form, use its base-unit barcode or select the product and enter the quantity in its base unit.');
      choices.current.set(result.item_id,{id:result.item_id,name:result.name,sku:result.sku,row_version:result.item_version,...(result.usage_role==='BASE'?{base_unit_id:result.unit_id}:{})});
      update(index,{...line,item:{...line.item,item_id:result.item_id,item_version:result.item_version,unit_id:result.unit_id}});
      setScanMessages(current=>({...current,[line.line_key]:'Selected '+result.name+' ('+result.sku+')'}));
    }catch(error){setScanMessages(current=>({...current,[line.line_key]:error instanceof Error?error.message:'Barcode lookup failed'}));}
    finally{setScanBusy(false);}
  }
  return <fieldset className="janso-fieldgroup janso-flow" disabled={locked}><legend>Items</legend>{lines.map((line,index)=><fieldset className="janso-fieldgroup janso-flow" key={line.line_key}><legend>Item {index+1}</legend>
    {canScan&&asOf&&native.item_id&&!native.item_id.readOnly&&native.unit_id&&!native.unit_id.readOnly&&<><TextField label={'Scan barcode '+(index+1)} value={scanValues[line.line_key]??''} disabled={locked} onChange={event=>setScanValues(current=>({...current,[line.line_key]:event.target.value}))} onKeyDown={event=>{if(event.key==='Enter'){event.preventDefault();void scan(index,line);}}}/><Button type="button" disabled={locked||!scanValues[line.line_key]?.trim()} onClick={()=>void scan(index,line)}>Resolve barcode {index+1}</Button>{scanMessages[line.line_key]&&<p role="status">{scanMessages[line.line_key]}</p>}</>}
    {native.item_id&&<SearchSelect label={'Product '+(index+1)} value={line.item.item_id||null} selected={choices.current.get(line.item.item_id)?{id:line.item.item_id,label:choices.current.get(line.item.item_id)?.name??choices.current.get(line.item.item_id)?.sku??line.item.item_id,meta:choices.current.get(line.item.item_id)?.sku}:undefined} disabled={locked||native.item_id.readOnly} loadOptions={items} minQueryLength={0} onChange={id=>{const item=choices.current.get(id??'');update(index,{...line,item:{...line.item,item_id:id??'',item_version:item?.row_version??0,unit_id:item?.base_unit_id??''}});}}/>}
    {native.unit_id&&<VoucherUnitReference company={company} label={'Unit '+(index+1)} value={line.item.unit_id} disabled={locked||!!native.unit_id.readOnly} baseOnly={physical} onChange={id=>update(index,{...line,item:{...line.item,unit_id:id??''}})}/>}
    {planned&&native.planned_quantity&&<TextField label={'Planned quantity '+(index+1)} inputMode="decimal" value={line.item.planned_quantity??''} disabled={locked||native.planned_quantity.readOnly} required onChange={event=>update(index,{...line,item:{...line.item,planned_quantity:event.target.value}})}/>}
    {!planned&&(['actual_quantity','billed_quantity'] as const).filter(key=>native[key]&&(!physical||key!=='billed_quantity')).map(key=><TextField key={key} label={(key==='actual_quantity'?'Actual quantity ':'Billed quantity ')+(index+1)} inputMode="decimal" value={line.item[key]} disabled={locked||native[key].readOnly} required onChange={event=>update(index,{...line,item:{...line.item,[key]:event.target.value}})}/>)}
    {lineSchema.items?.properties?.description&&<TextField label={'Item description '+(index+1)} value={line.description??''} disabled={locked} required={metadata.configuration.policy.line_description_required} onChange={event=>update(index,{...line,description:event.target.value})}/>}
    <CustomFields fields={fields} values={line.item.custom_fields??{}} nativeValues={line.item} creating disabled={locked} currencies={[currency]} loadOptions={source=>lookup(company,source)} onChange={values=>update(index,{...line,item:{...line.item,custom_fields:customPatch(fields,values,{})}})}/>
    <Button type="button" disabled={locked} onClick={()=>onChange(lines.filter((_,i)=>i!==index))}>Remove item {index+1}</Button>
  </fieldset>)}<Button type="button" disabled={locked||lines.length>=Math.min(metadata.configuration.policy.max_lines??200,physical?100:200)} onClick={()=>onChange([...lines,{line_key:crypto.randomUUID(),line_kind:'ITEM',description:'',item:{item_id:'',item_version:0,unit_id:'',actual_quantity:planned?'0':'1',billed_quantity:planned||physical?'0':'1',...(planned?{planned_quantity:'1'}:{}),custom_fields:{}}}])}>Add item</Button></fieldset>;
}
