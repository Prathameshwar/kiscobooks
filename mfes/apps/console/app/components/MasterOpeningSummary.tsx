'use client';
import {Card,CardBody,ReviewList,SectionHeader,useFormatters} from '@janso/ui';
import {request} from '../lib/financial-opening';
import {masterHeldPath,type MasterHeldPage} from '../lib/master-opening';
import {verifyMasterPage} from '../lib/master-opening-held';
import {useServiceRead} from '../lib/service-resource';
import {AccountingFailure} from './AccountingConfigurationCommon';
import {FinancialOpeningMoney} from './FinancialOpeningCommon';

export function MasterOpeningSummary({company,account,onLeave}:{company:string;account:string;onLeave?:React.MouseEventHandler<HTMLAnchorElement>}){
  const format=useFormatters();
  const held=useServiceRead<MasterHeldPage>(masterHeldPath(company)+'?'+new URLSearchParams({account_id:account,limit:'1'}),request,value=>{verifyMasterPage(company,value);if(value.items.some(item=>item.account_id!==account))throw {status:502,message:'The account opening could not be verified.'};});
  if(held.failure?.status===403||held.loading||!held.failure&&!held.data?.items.length)return null;
  const item=held.data?.items[0];
  if(item&&(item.company_id!==company||item.account_id!==account))return null;
  return <Card><CardBody><div className="janso-flow">
    <SectionHeader title={item?.status==='POSTED'?'Opening posted during creation':'Opening saved during creation'}/>
    <AccountingFailure failure={held.failure} retry={held.refresh}/>
    {item&&<><ReviewList items={[{label:'Opening balance',value:<><FinancialOpeningMoney value={item.entry.amount} currency={item.entry.currency}/> {item.entry.side==='DEBIT'?'Dr':'Cr'}</>},{label:'Opening date',value:format.date(item.opening_date)},{label:'Status',value:item.status==='REVERSED'?'Reversed':item.status==='POSTED'?'Posted':item.status==='POSTING'?'Posting pending — retry the same creation':item.status==='WITHDRAWN'?'Withdrawn':item.included?'In the company opening declaration':'Saved for company opening review'},{label:'Allocation',value:item.entry.documents.length===1&&item.entry.documents[0]!.document_kind==='ON_ACCOUNT'?'On account':item.entry.documents.length?`${item.entry.documents.length} pending bills`:'Balance only'}]}/>
    {item.status==='POSTED'?<p className="janso-fine">Included in the account ledger. No further opening action is required.</p>:item.status==='PENDING'&&<a className="janso-link" href={'/accounting/opening?'+new URLSearchParams({account_id:account})} onClick={onLeave}>Review company opening worksheet</a>}</>}
  </div></CardBody></Card>;
}
