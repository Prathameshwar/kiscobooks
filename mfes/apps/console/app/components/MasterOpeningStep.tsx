'use client';
import {useState} from 'react';
import {Button,ConfirmDialog,Notice,SectionHeader,SegmentedControl,Select,TextField,useFormatters} from '@janso/ui';
import {AccountingFailure} from './AccountingConfigurationCommon';
import {decimal,sum} from '../lib/financial-opening';
import {billErrors,billKinds,blankOpening,canOpen,hasBillDraft,newBill,openingDirty,pendingTotal,type OpeningAccount,type OpeningBillDraft,type OpeningCapture,type OpeningDraft} from '../lib/master-opening';
import type {RequestFailure} from '../lib/service-call';

export function MasterOpeningStep({draft,onChange,metadata,loading,failure,retry,account,disabled=false,errors={}}:{
  draft:OpeningDraft;onChange:(value:OpeningDraft)=>void;metadata:OpeningCapture|null;
  loading:boolean;failure:RequestFailure|null;retry:()=>void;account:OpeningAccount;
  disabled?:boolean;errors?:Record<string,string>;
}){
  const format=useFormatters(),[billProblems,setBillProblems]=useState<Record<string,string>>({}),[clearRequested,setClearRequested]=useState(false);
  const date=draft.date||metadata?.opening_date||'';
  const currency=account.currencyMode==='FIXED'?account.currency??metadata?.currency:metadata?.currency;
  const foreign=!!currency&&!!metadata&&currency!==metadata.currency;
  const canBills=account.party&&['CUSTOMER','SUPPLIER'].includes(account.role??'');
  const stock=account.inventory||account.kind==='INVENTORY_CONTROL';
  const locked=disabled||loading||!canOpen(metadata,account)||!!stock;
  const update=(value:Partial<OpeningDraft>)=>{if(!disabled){setBillProblems({});onChange({...draft,...value});}};
  const edit=(value:Partial<OpeningBillDraft>)=>draft.editor&&update({editor:{...draft.editor,...value}});
  const mainError=(key:string)=>errors['opening.'+key];
  const total=draft.bills.every(bill=>decimal(bill.pending,true))?pendingTotal(draft.bills):'';
  function changeMode(mode:OpeningDraft['mode']){
    if(locked||mode===draft.mode)return;
    if(hasBillDraft(draft.editor)){setBillProblems({mode:'Add or update the bill, or cancel the bill before switching modes.'});return;}
    const change:Partial<OpeningDraft>={mode,editor:mode==='bills'&&!draft.bills.length?newBill(account,draft.side):null};
    if(mode==='simple'&&draft.bills.length>0){
      change.amount=total;
      if(foreign&&draft.bills.every(bill=>decimal(bill.base,true)))change.base=sum(draft.bills.map(bill=>bill.base));
    }
    update(change);
  }
  function clearOpening(){if(!disabled){setBillProblems({});onChange(blankOpening());setClearRequested(false);}}
  function saveBill(){
    if(locked||!draft.editor)return;
    const bill=draft.editor,next=billErrors(bill,account,draft.side,date,foreign);
    if(draft.bills.some(item=>item.id!==bill.id&&item.reference.trim().toLowerCase()===bill.reference.trim().toLowerCase()))next.reference='Bill numbers must be unique.';
    if(draft.bills.length>=200&&!draft.bills.some(item=>item.id===bill.id))next.reference='At most 200 bills can be entered during creation.';
    setBillProblems(next);if(Object.keys(next).length)return;
    const index=draft.bills.findIndex(item=>item.id===bill.id),bills=[...draft.bills];
    if(index<0)bills.push(bill);else bills[index]=bill;
    onChange({...draft,bills,editor:null});
  }
  return <div className="janso-master-opening">
    <SectionHeader title="Opening balance" description="Optional. Enter the balance at the start of your books. Leave it blank to create without an opening."/>
    <AccountingFailure failure={failure} retry={retry}/>
    {loading&&<p role="status">Checking opening balance access…</p>}
    {!loading&&metadata&&!canOpen(metadata,account)&&<Notice tone="warning">Opening capture is unavailable for this company or your current access. You can create without an opening balance.</Notice>}
    {stock&&<Notice>Enter inventory quantities and values in the stock opening worksheet.</Notice>}
    {(canBills||draft.mode==='bills')&&<SegmentedControl label="Opening entry mode" value={draft.mode} options={canBills?[{value:'simple',label:'Balance only'},{value:'bills',label:'Bill-wise'}]:[{value:'simple',label:'Balance only'}]} disabled={locked} onChange={changeMode}/>}
    {billProblems.mode&&<p role="alert">{billProblems.mode}</p>}
    <div className="janso-master-opening__fields">
      <TextField name="opening.amount" label="Opening balance" inputMode="decimal" value={draft.mode==='bills'?total:draft.amount} readOnly={draft.mode==='bills'} disabled={locked} error={mainError('amount')} onChange={event=>update({amount:event.target.value})} optionalNote={currency??''}/>
      <Select name="opening.side" label="Dr / Cr" value={draft.side} options={[{value:'',label:'Choose Dr / Cr'},{value:'DEBIT',label:'Dr · Debit'},{value:'CREDIT',label:'Cr · Credit'}]} disabled={locked} error={mainError('side')} onChange={side=>update({side})}/>
      <TextField name="opening.opening_date" label="Opening date" type="date" value={date} disabled={locked} error={mainError('opening_date')} hint="Company books-begin date" onChange={event=>update({date:event.target.value})}/>
    </div>
    {foreign&&<div className="janso-master-opening__fields">
      <TextField label="Opening exchange rate" inputMode="decimal" value={draft.rate} disabled={locked} error={mainError('exchange_rate')} onChange={event=>update({rate:event.target.value})}/>
      <TextField label="Historical opening value" inputMode="decimal" value={draft.base} disabled={locked} optionalNote={metadata?.currency} error={mainError('base_amount')} onChange={event=>update({base:event.target.value})}/>
    </div>}
    {account.kind==='CASH'&&draft.side==='CREDIT'&&<TextField label="Credit cash opening reason" value={draft.cashReason} maxLength={500} disabled={locked} error={mainError('credit_cash_reason')} onChange={event=>update({cashReason:event.target.value})}/>}
    {draft.mode==='bills'&&<div className="janso-master-opening__bills">
      <p className="janso-fine">Enter only bills still outstanding. Bill amount records the original value; Pending amount contributes to the opening balance.</p>
      {mainError('documents')&&<p role="alert">{mainError('documents')}</p>}
      {draft.editor&&<section className="janso-master-opening__editor" aria-label="Opening bill editor">
        <SectionHeader title={draft.bills.some(bill=>bill.id===draft.editor!.id)?'Edit opening bill':'Add opening bill'}/>
        <div className="janso-master-opening__fields">
          <TextField label="Bill number" value={draft.editor.reference} maxLength={120} disabled={locked} error={billProblems.reference} onChange={event=>edit({reference:event.target.value})}/>
          <Select label="Bill type" value={draft.editor.kind} options={billKinds(account,draft.side)} disabled={locked} error={billProblems.kind} onChange={kind=>edit({kind})}/>
          <TextField label="Bill amount" inputMode="decimal" value={draft.editor.original} disabled={locked} error={billProblems.original} onChange={event=>edit({original:event.target.value})}/>
          <TextField label="Pending amount" inputMode="decimal" value={draft.editor.pending} disabled={locked} error={billProblems.pending} onChange={event=>edit({pending:event.target.value})}/>
          <TextField label="Bill date" type="date" value={draft.editor.date} disabled={locked} error={billProblems.date} onChange={event=>edit({date:event.target.value})}/>
          <TextField label="Due date" type="date" value={draft.editor.due} disabled={locked} error={billProblems.due} onChange={event=>edit({due:event.target.value})}/>
          {foreign&&<TextField label="Pending historical value" inputMode="decimal" value={draft.editor.base} disabled={locked} optionalNote={metadata?.currency} error={billProblems.base} onChange={event=>edit({base:event.target.value})}/>}
        </div>
        <div className="janso-report-actions"><Button type="button" disabled={locked} onClick={saveBill}>{draft.bills.some(bill=>bill.id===draft.editor!.id)?'Update bill':'Add bill'}</Button><Button type="button" variant="ghost" disabled={disabled} onClick={()=>update({editor:null})}>Cancel bill</Button></div>
      </section>}
      {!draft.editor&&<Button type="button" variant="ghost" disabled={locked||draft.bills.length>=200} onClick={()=>update({editor:newBill(account,draft.side)})}>Add another bill</Button>}
      {draft.bills.length>0&&<div className="janso-master-opening__list" role="region" aria-label="Opening bills" tabIndex={0}>
        <table><caption className="janso-visually-hidden">Opening bills and pending amounts</caption><thead><tr><th scope="col">Bill</th><th scope="col">Type</th><th scope="col">Pending</th><th scope="col">Actions</th></tr></thead><tbody>{draft.bills.map((bill,index)=><tr key={bill.id}>
          <th scope="row">{bill.reference}<small>{format.date(bill.date)} · Due {format.date(bill.due)}</small>{Object.entries(errors).filter(([key])=>key.startsWith(`opening.documents.${index}.`)).map(([key,message])=><small role="alert" key={key}>{message}</small>)}</th>
          <td data-label="Type">{bill.kind==='INVOICE'?'Sales':bill.kind==='BILL'?'Purchase':bill.kind==='ADVANCE'?'Advance':'Credit note'}</td><td data-label="Pending" className="janso-figure">{format.money(bill.pending,{display:'none'})}</td>
          <td className="janso-master-opening__bill-actions"><div className="janso-report-actions"><Button type="button" variant="ghost" disabled={locked||hasBillDraft(draft.editor)} onClick={()=>update({editor:{...bill}})} aria-label={'Edit opening bill '+bill.reference}>Edit</Button><Button type="button" variant="ghost" disabled={locked} onClick={()=>update({bills:draft.bills.filter(item=>item.id!==bill.id),editor:draft.editor?.id===bill.id?null:draft.editor})} aria-label={'Remove opening bill '+bill.reference}>Remove</Button></div></td>
        </tr>)}</tbody><tfoot><tr><th scope="row" colSpan={2}>Total pending · {draft.bills.length} bills</th><td className="janso-figure">{decimal(total)?format.money(sum([total]),{display:'none'}):'Check amounts'}</td><td/></tr></tfoot></table>
      </div>}
    </div>}
    {draft.mode==='simple'&&draft.bills.length>0&&<p className="janso-fine">Switch to Bill-wise to include your bill allocations.</p>}
    {openingDirty(draft)&&<div className="janso-report-actions"><Button type="button" variant="ghost" disabled={disabled} onClick={()=>draft.bills.length||hasBillDraft(draft.editor)?setClearRequested(true):clearOpening()}>Clear opening balance</Button></div>}
    <ConfirmDialog open={clearRequested} tone="danger" title="Clear opening balance?" confirmLabel="Clear opening" cancelLabel="Keep opening" onConfirm={clearOpening} onCancel={()=>setClearRequested(false)}>
      This removes the entered balance and all opening bills from this draft.
    </ConfirmDialog>
    <p className="janso-fine">Creating this record also posts its opening balance and any pending bills. The balancing entry uses the company opening-balance offset account. No separate posting step is needed.</p>
  </div>;
}
