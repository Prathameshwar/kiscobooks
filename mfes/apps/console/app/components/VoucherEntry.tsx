'use client';
import {useState} from 'react';
import {Button,Card,CardBody,PageHeader,PageNavigation,Select,TextField,CustomFields,Notice,customPatch,type CustomField} from '@janso/ui';
import type {components} from '@janso/api-client/vouchers';
import {productFieldRequest as request} from '../lib/product-fields';
import {customFields,lookup,voucherCommandRequest,type FieldSet} from '../lib/voucher-fields';
import {useServiceCommand,useServiceDestination} from '../lib/service-resource';
import {useAccessDraft} from './AccessCommon';
import {VoucherItems} from './VoucherItems';
import {VoucherFulfillment,initialFulfillmentTerms} from './VoucherFulfillment';
import {VoucherRelated} from './VoucherRelated';
import {VoucherWorkflow} from './VoucherWorkflow';
import {VoucherMoney,type MoneyInput} from './VoucherMoney';
import {VoucherStock} from './VoucherStock';
import {buildStockCapture,initialStockDraft,type StockDraft} from '../lib/voucher-stock';
import {trackingId} from '../lib/stock-tracking-resources';
import {PurchaseInvoice} from './PurchaseInvoice';
import {buildPurchase,initialPurchase,PurchaseValidationError,type PurchaseDraft} from '../lib/purchase-entry';
import {kindLabel} from '../lib/voucher-kinds';
import {operateReturn,withReturn} from '../lib/operate-navigation';
export function VoucherEntry({company,currency,canCreate,permissions=[],openingOnly=false,initialItemId,initialKind,initialTypeId,returnTo}:{company:string;currency:string;canCreate:boolean;permissions?:readonly string[];openingOnly?:boolean;initialItemId?:string;initialKind?:string;initialTypeId?:string;returnTo?:string}) {
  const [types,setTypes]=useState<{id:string;name?:string}[]>([]),[type,setType]=useState(initialTypeId??'');
  const back=operateReturn(returnTo),[moreTypes,setMoreTypes]=useState(false);
  const [date,setDate]=useState(''),[narration,setNarration]=useState(''),[metadata,setMetadata]=useState<FieldSet|null>(null);
  const [custom,setCustom]=useState<Record<string,unknown>>({}),[busy,setBusy]=useState(false),[message,setMessage]=useState('');
  const [lines,setLines]=useState<components['schemas']['LineInput'][]>([]),[mode,setMode]=useState<components['schemas']['VoucherInput']['mode']>('ACCOUNTS'),[saved,setSaved]=useState('');
  const [parties,setParties]=useState<components['schemas']['PartyInput'][]>([]),[references,setReferences]=useState<components['schemas']['ReferenceInput'][]>([]);
  const [fulfillmentTerms,setFulfillmentTerms]=useState<components['schemas']['FulfillmentTermsInput']|null>(null);
  const [classes,setClasses]=useState<{id:string;name?:string;code?:string}[]>([]),[selectedClass,setSelectedClass]=useState(''),[classAccessible,setClassAccessible]=useState(false);
  const [financial,setFinancial]=useState<MoneyInput|null>(null),[postingDate,setPostingDate]=useState('');
  const [stock,setStock]=useState<StockDraft|null>(null);
  const quantityPending=!!stock&&(Object.values(stock.dimensions).some(dimension=>dimension.quantity_pending)||(stock.action==='COUNT'&&lines.some(line=>!stock.dimensions[line.line_key]?.count)));
  function itemLines(next:components['schemas']['LineInput'][]){
    setLines(next);
    setStock(current=>{
      if(!current)return current;
      const dimensions={...current.dimensions};
      for(const previous of lines){
        const changed=next.find(line=>line.line_key===previous.line_key);
        if(!changed||changed.item.item_id!==previous.item.item_id)delete dimensions[previous.line_key];
        else if(changed.item.actual_quantity!==previous.item.actual_quantity||changed.item.unit_id!==previous.item.unit_id){
          const selected=dimensions[previous.line_key];
          if(selected)dimensions[previous.line_key]={...selected,quantity_entry:null,count:null,quantity_pending:current.action==='COUNT'};
        }
      }
      return {...current,dimensions};
    });
  }
  const [purchase,setPurchase]=useState<PurchaseDraft|null>(null);
  const [purchaseErrors,setPurchaseErrors]=useState<Record<string,string>>({});
  const [purchaseBusy,setPurchaseBusy]=useState(false);
  const [typesLoaded,setTypesLoaded]=useState(false);
  const command=useServiceCommand(voucherCommandRequest),locked=busy||purchaseBusy||command.pending||command.uncertain;
  const destination=useServiceDestination(command.pending);
  const guard=useAccessDraft(!!metadata||command.uncertain,command.pending);
  const base='/v1/companies/'+company;
  async function action(work:()=>Promise<void>) {setBusy(true);setMessage('');try{await work();}catch(error){if(error instanceof PurchaseValidationError){setPurchaseErrors({[error.field]:error.message});setMessage('Correct the highlighted purchase field and save again.');}else setMessage(error instanceof Error?error.message:'Unable to save voucher');}finally{setBusy(false);}}
  const fields:CustomField[]=metadata?customFields(metadata,'vouchers.voucher'):[];
  return <section className="janso-page" aria-label="Voucher entry">
    {!openingOnly&&!metadata&&<PageNavigation back={{href:back??'/vouchers',label:back?'voucher list':'voucher drafts'}} />}
    <PageHeader title={initialKind?'New '+kindLabel(initialKind).toLowerCase():openingOnly?'Record opening stock':'New voucher draft'} lede={openingOnly?'Choose your opening stock voucher type and the date your books begin. Review the saved draft before posting.':'Choose a voucher type and date, prepare its details, then review the saved draft before approval and posting.'} />
    {!canCreate&&<Notice>Your role can review voucher setup. Voucher creation access is required to prepare a draft.</Notice>}
    <Card><CardBody><fieldset className="janso-fieldgroup janso-flow" disabled={locked}>
    <Button disabled={busy} onClick={()=>void action(async()=>{
      type TypeRow={id:string;name?:string;kind?:string;company_id?:string;status?:string};
      const result=initialTypeId?{items:[await request<TypeRow>('vouchers','GET',base+'/voucher-types/'+initialTypeId)]}:await request<{items:TypeRow[];page?:{has_more:boolean}}>('vouchers','GET',base+'/voucher-types?status=ACTIVE&limit=200'+(initialKind?'&kind='+initialKind:''));
      if(initialKind&&(!Array.isArray(result.items)||result.items.some(row=>!trackingId.test(row.id)||row.company_id!==company||row.kind!==initialKind||initialTypeId&&(row.id!==initialTypeId||row.status!=='ACTIVE'))))throw new Error('Voucher type ownership and kind could not be verified.');
      setTypes(result.items);setMoreTypes('page' in result&&!!result.page?.has_more);setTypesLoaded(true);
    })}>Load voucher types</Button>
    <Select label="Voucher type" value={type} options={types.map(row=>({value:row.id,label:row.name??row.id}))} disabled={busy} onChange={value=>{setType(value);setSelectedClass('');setClasses([]);setMetadata(null);setCustom({});setLines([]);setParties([]);setReferences([]);setFinancial(null);setFulfillmentTerms(null);setPostingDate(date);}}/>
    <TextField label="Document date" type="date" value={date} hint={openingOnly?'Use the books-begin date set in Company settings.':undefined} disabled={busy} onChange={event=>{setDate(event.target.value);setMetadata(null);}}/>
    <Button disabled={busy||!type||!date||!!initialTypeId&&!typesLoaded} onClick={()=>void action(async()=>{
      const data=await request<FieldSet>('vouchers','GET',base+'/voucher-types/'+type+'/field-set?date='+encodeURIComponent(date)+(selectedClass?'&class_id='+encodeURIComponent(selectedClass):''));
      if(initialKind&&(data?.configuration?.kind!==initialKind||!trackingId.test(data.configuration.type_revision_id)||!data.configuration.policy||!data.native||!Array.isArray(data.custom)))throw new Error('The selected type does not match this voucher entry.');
      if(openingOnly&&initialStockDraft(data,date)?.action!=='OPENING')throw new Error('Choose a stock journal type configured for opening stock, with permission to enter stock.');
      let initialLines:components['schemas']['LineInput'][]=[];
      if(openingOnly&&initialItemId){const item=await request<{id:string;company_id:string;status?:string;row_version?:number;base_unit_id?:string}>('catalog','GET',base+'/items/'+initialItemId);if(item.id!==initialItemId||item.company_id!==company||item.status!=='ACTIVE'||!item.row_version||!trackingId.test(item.base_unit_id??''))throw new Error('The product is unavailable or not active for opening stock.');initialLines=[{line_key:crypto.randomUUID(),line_kind:'ITEM',item:{item_id:item.id,item_version:item.row_version,unit_id:item.base_unit_id!,actual_quantity:'1',billed_quantity:'0',custom_fields:{}}}];}
      setMetadata(data);setNarration(data.configuration.policy.default_narration??'');setMode(initialStockDraft(data,date)||initialFulfillmentTerms(data)?'ITEMS':data.configuration.policy.default_mode??'ACCOUNTS');setCustom({});setLines(initialLines);setParties([]);setReferences([]);setFinancial(null);setFulfillmentTerms(initialFulfillmentTerms(data));setStock(initialStockDraft(data,date));setPostingDate(initialFulfillmentTerms(data)?'':date);setPurchase(initialKind==='PURCHASE'?initialPurchase(date):null);
      const classPage=await request<{items:{id:string;name?:string;code?:string}[]}>('vouchers','GET',base+'/voucher-classes?type_revision_id='+data.configuration.type_revision_id+'&limit=200');setClasses(classPage.items);setClassAccessible(!!data.native.properties?.class_id&&!data.native.properties.class_id.readOnly);
    })}>Load entry fields</Button>
    {initialKind&&typesLoaded&&!types.length&&<Notice>No active {initialKind.toLowerCase()} voucher types are available for this company. <a className="janso-link" href="/masters/voucher-types">Review voucher types</a></Notice>}
    {moreTypes&&<Notice>More voucher types are available. Open a specific type from its workflow page to use a type beyond this selection.</Notice>}
    {classes.length>0&&classAccessible&&<Select label="Voucher class" value={selectedClass} options={[{value:'',label:'No class'},...classes.map(row=>({value:row.id,label:row.name??row.code??row.id}))]} disabled={busy} onChange={value=>{setSelectedClass(value);setMetadata(null);}}/>}
    </fieldset></CardBody></Card>
    {metadata&&<form className="janso-flow" noValidate={!!purchase} onSubmit={event=>{event.preventDefault();void action(async()=>{
      if(!canCreate) throw new Error('Voucher creation is not permitted');
      const body:components['schemas']['VoucherInput']={type_revision_id:metadata.configuration.type_revision_id,document_date:date,currency,custom_fields:customPatch(fields,custom,{})};
      if(selectedClass&&metadata.native.properties?.class_id&&!metadata.native.properties.class_id.readOnly)body.class_id=selectedClass;
      if(metadata.native.properties?.mode&&!metadata.native.properties.mode.readOnly) body.mode=mode;
      if(financial&&metadata.native.properties?.financial&&!metadata.native.properties.financial.readOnly)body.financial=financial;
      if(fulfillmentTerms&&metadata.native.properties?.fulfillment_terms&&!metadata.native.properties.fulfillment_terms.readOnly)body.fulfillment_terms=fulfillmentTerms;
      if(postingDate&&metadata.native.properties?.posting_date&&!metadata.native.properties.posting_date.readOnly)body.posting_date=postingDate;
      if(lines.length)body.lines=lines;
      if(stock){if(!metadata.native.properties?.stock_date||metadata.native.properties.stock_date.readOnly)throw new Error('Stock movement date write access is required.');body.stock=buildStockCapture(stock,lines,currency,metadata);body.stock_date=stock.date;}
      if(parties.length)body.parties=parties;
      if(references.length)body.references=references;
      if(purchase)Object.assign(body,buildPurchase(company,purchase,date,metadata));
      if(metadata.native.properties?.narration&&!metadata.native.properties.narration.readOnly) body.narration=narration;
      const result=await command.execute<{id:string;company_id:string}>({method:'POST',path:base+'/vouchers',body},value=>{if(!trackingId.test(value.id)||value.company_id!==company)throw{status:502,message:'The saved voucher could not be verified. Retry the same save.'};});
      if(result){setSaved(result.id);setMessage('Draft saved: '+result.id);setMetadata(null);destination.setDestination(withReturn('/vouchers/'+result.id,back));}
    });}}>
      <fieldset className="janso-fieldgroup janso-flow" disabled={locked||!canCreate}>
      {!purchase&&metadata.native.properties?.mode&&<Select label="Entry mode" value={mode??'ACCOUNTS'} options={(metadata.configuration.policy.allowed_modes??['ACCOUNTS']).map(value=>({value,label:value}))} disabled={busy||metadata.native.properties.mode.readOnly} onChange={value=>{setMode(value as typeof mode);if(value==='ACCOUNTS')setLines([]);}}/>}
      {metadata.native.properties?.narration&&<TextField label="Narration" value={narration} disabled={busy||metadata.native.properties.narration.readOnly} onChange={event=>setNarration(event.target.value)}/>}
      {!fulfillmentTerms&&metadata.native.properties?.posting_date&&<TextField label="Posting date" type="date" value={postingDate} disabled={busy||metadata.native.properties.posting_date.readOnly} onChange={event=>setPostingDate(event.target.value)}/>}
      <VoucherMoney company={company} currency={currency} metadata={metadata} value={financial} onChange={setFinancial} disabled={busy||!canCreate}/>
      <VoucherFulfillment metadata={metadata} value={fulfillmentTerms} onChange={setFulfillmentTerms} disabled={busy||!canCreate}/>
      <CustomFields fields={fields} values={custom} nativeValues={{document_date:date,narration}} creating disabled={busy||!canCreate} currencies={[currency]} loadOptions={source=>lookup(company,source)} onChange={setCustom}/>
      {purchase?<PurchaseInvoice key={metadata.configuration.type_revision_id+':'+selectedClass} company={company} currency={currency} metadata={metadata} value={purchase} errors={purchaseErrors} onChange={value=>{setPurchase(value);setPurchaseErrors({});}} onPendingChange={setPurchaseBusy} disabled={locked||!canCreate}/>:<>
      <VoucherRelated company={company} metadata={metadata} parties={parties} references={references} onParties={setParties} onReferences={setReferences} disabled={busy||!canCreate}/>
      {mode!=='ACCOUNTS'&&<VoucherItems company={company} currency={currency} metadata={metadata} lines={lines} onChange={itemLines} disabled={locked||!canCreate} asOf={postingDate||date} canScan={permissions.includes('item.read')}/>}</>}
      {stock&&<VoucherStock company={company} currency={currency} metadata={metadata} lines={lines} value={stock} onChange={setStock} canReviewCount={permissions.includes('accounting.stock.configure')} onQuantity={(key,quantity)=>setLines(current=>current.map(line=>line.line_key===key?{...line,item:{...line.item,actual_quantity:quantity}}:line))} disabled={locked||!canCreate}/>}
      </fieldset>
      {quantityPending&&<Notice tone="warning">{stock?.action==='COUNT'?'Record each native physical count observation before saving.':'Validate and apply each entered product quantity, or use base quantity, before saving.'}</Notice>}
      <Button type="submit" disabled={busy||purchaseBusy||command.pending||quantityPending||!canCreate||!currency} loading={busy||command.pending}>{command.uncertain?'Retry the same save':'Save draft'}</Button>
      {!openingOnly&&<a className="janso-link" href={back??'/vouchers'} onClick={guard.leave}>Cancel draft</a>}
    </form>}
    {message&&<p role="status">{message}</p>}
    {command.failure&&<Notice tone="danger">{command.failure.message}{command.uncertain?' Your save is unconfirmed. Retry the same save to recover its result.':''}</Notice>}
    {saved&&<a className="janso-link" href={withReturn('/vouchers/'+saved,back)}>Open saved voucher</a>}
    {saved&&<VoucherWorkflow key={saved} company={company} voucherId={saved} permissions={permissions}/>}
    {guard.confirmation}
  </section>;
}
