'use client';
import {useEffect,useRef,useState} from 'react';
import {Button,Card,CardBody,ConfirmDialog,DataTable,Notice,SectionHeader,TextField,type Column} from '@janso/ui';
import {request,type Access,type Entry} from '../lib/financial-opening';
import {masterHeldPath,type MasterHeld,type MasterHeldPage} from '../lib/master-opening';
import {addableMaster,masterEntry,verifyMasterItem,verifyMasterPage} from '../lib/master-opening-held';
import {useServiceCommand,useServiceRead} from '../lib/service-resource';
import {AccountingFailure} from './AccountingConfigurationCommon';
import {FinancialOpeningAccount,FinancialOpeningMoney} from './FinancialOpeningCommon';

export function FinancialOpeningMasterBalances({company,rows,date,access,editable,onAdd,onDirty,onLeave}:{company:string;rows:Entry[];date:string;access:Access;editable:boolean;onAdd:(rows:Entry[])=>void;onDirty:(value:boolean)=>void;onLeave?:React.MouseEventHandler<HTMLAnchorElement>}){
  const [cursor,setCursor]=useState<string|null>(null),[previous,setPrevious]=useState<(string|null)[]>([]),[target,setTarget]=useState<MasterHeld|null>(null),[reason,setReason]=useState(''),[error,setError]=useState(''),[message,setMessage]=useState('');
  const params=new URLSearchParams({status:'PENDING',limit:'25'});if(cursor)params.set('cursor',cursor);
  const held=useServiceRead<MasterHeldPage>(masterHeldPath(company)+'?'+params,request,value=>verifyMasterPage(company,value));
  const command=useServiceCommand(request,'saved opening balance');
  const frozen=useRef<Parameters<typeof command.execute>[0]|null>(null);
  useEffect(()=>{onDirty(!!target||command.pending||command.uncertain);return()=>onDirty(false);},[target,command.pending,command.uncertain,onDirty]);
  const open=addableMaster((held.data?.items??[]).filter(item=>item.company_id===company),rows,date);
  useEffect(()=>{
    if(target&&held.data&&!held.loading&&!command.pending&&!command.uncertain){
      const current=open.find(item=>item.id===target.id);
      if(!current)setTarget(null);else if(current.row_version!==target.row_version)setTarget(current);
    }
  },[held.data,held.loading,command.pending,command.uncertain,target,open]);
  if(held.failure?.status===403)return null;
  if(!held.failure&&(held.loading||(!open.length&&!held.data?.page.has_more&&!previous.length&&!message)))return null;
  async function withdraw(){
    if(!access.manage||command.pending||!target||target.company_id!==company)return;
    if(!command.uncertain){
      if(reason.trim().length<3||reason.trim().length>500||/[\x00-\x1f\x7f]/.test(reason)){setError('Enter a printable reason between 3 and 500 characters.');return;}
      frozen.current={path:masterHeldPath(company)+'/'+target.id+'/withdraw',method:'POST',body:{expected_version:target.row_version,reason:reason.trim()}};
    }
    if(!frozen.current)return;
    const done=await command.execute<MasterHeld>(frozen.current,value=>{verifyMasterItem(company,value);if(value.id!==target.id||value.status!=='WITHDRAWN')throw {status:502,message:'The opening withdrawal could not be verified.'};});
    if(done){setTarget(null);setReason('');setError('');setMessage('Saved opening withdrawn.');frozen.current=null;command.clear();held.refresh();}
    else if(!command.uncertain)held.refresh();
  }
  const busy=!!target||command.pending||command.uncertain;
  const columns:Column<MasterHeld>[]=[
    {type:'custom',key:'account',header:'Account',render:item=><FinancialOpeningAccount company={company} id={item.account_id} onLeave={onLeave}/>},
    {type:'custom',key:'side',header:'Dr / Cr',render:item=>item.entry.side==='DEBIT'?'Dr':'Cr'},
    {type:'custom',key:'amount',header:'Opening balance',render:item=><FinancialOpeningMoney value={item.entry.amount} currency={item.entry.currency}/>},
    {type:'custom',key:'bills',header:'Bills',render:item=>item.entry.documents.length===1&&item.entry.documents[0]!.document_kind==='ON_ACCOUNT'?'On account':item.entry.documents.length?`${item.entry.documents.length} pending bills`:'Balance only'},
    {type:'custom',key:'actions',header:'Actions',render:item=><div className="janso-report-actions"><Button variant="ghost" disabled={!editable||busy||rows.length>=10000} aria-label={'Add saved opening '+item.source_key} onClick={()=>onAdd([masterEntry(item)])}>Add</Button><Button variant="ghost" disabled={!access.manage||busy} aria-label={'Withdraw saved opening '+item.source_key} onClick={()=>{setTarget(item);setReason('');setError('');command.clear();}}>Withdraw</Button></div>},
  ];
  return <Card><CardBody><div className="janso-flow">
    <SectionHeader title="Openings saved during creation" description="Add these balances and bills to this worksheet for review. Activate draft accounts before validating the company opening."/>
    <AccountingFailure failure={held.failure} retry={()=>{setCursor(null);setPrevious([]);held.refresh();}}/>
    {message&&<Notice tone="success"><span role="status">{message}</span></Notice>}
    <DataTable caption="Saved master opening balances" columns={columns} rows={open} rowId={item=>item.id} rowLabel={item=>item.source_key} emptyTitle="No available balances on this page" emptyBody="Use the next page to review more saved openings."/>
    <div className="janso-form-actions"><Button variant="ghost" disabled={busy||!previous.length||held.loading} onClick={()=>{setCursor(previous.at(-1)??null);setPrevious(previous.slice(0,-1));}}>Previous saved balances</Button><Button variant="ghost" disabled={busy||!held.data?.page.has_more||held.loading} onClick={()=>{if(held.data?.page.next_cursor){setPrevious([...previous,cursor]);setCursor(held.data.page.next_cursor);}}}>Next saved balances</Button></div>
    <ConfirmDialog open={!!target} busy={command.pending} title="Withdraw saved opening?" confirmLabel={command.uncertain?'Retry the same request':'Withdraw opening'} onCancel={()=>{if(!command.uncertain)setTarget(null);}} onConfirm={()=>void withdraw()}>
      <p>This removes the saved opening from the available list. The account remains, and the original evidence is retained.</p>
      {target&&<FinancialOpeningMoney value={target.entry.amount} currency={target.entry.currency}/>}
      <TextField label="Withdrawal reason" value={reason} maxLength={500} disabled={command.pending||command.uncertain} onChange={event=>setReason(event.target.value)}/>
      {error&&<p role="alert">{error}</p>}{command.failure&&<p role="alert">{command.failure.message}</p>}
    </ConfirmDialog>
  </div></CardBody></Card>;
}
