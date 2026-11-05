import {trialAmounts} from '../app/lib/trial-balance';
import {row,trialMock,uuid} from './trial-balance-fixture';

export const hierarchyKeys={assets:'head:'+uuid(40),liabilities:'head:'+uuid(41),current:'group:'+uuid(42),wallet:'group:'+uuid(43),bank:'group:'+uuid(44),payables:'group:'+uuid(45)};
const amounts=(values:readonly number[])=>Object.fromEntries(trialAmounts.map((key,index)=>[key,values[index]+'.0000']));
function node(kind:string,key:string,parent:string,name:string,depth:number,children:number,groups:number,count:number,values:readonly number[]){
  const original=row(kind,key,parent,name,depth,children);
  return {...original,data:{...original.data,...amounts(values),group_child_count:groups,account_count:count,is_zero:values.every(value=>value===0)}};
}
const k=hierarchyKeys;
export const hierarchyRows={
  root:[node('HEAD',k.assets,'root','Assets',0,2,2,4,[30,0,12,9,33,0]),node('HEAD',k.liabilities,'root','Liabilities',0,1,1,1,[0,30,2,5,0,33])],
  [k.assets]:[node('GROUP',k.current,k.assets,'Current assets',1,1,1,3,[10,0,12,7,15,0]),node('GROUP',k.bank,k.assets,'Bank accounts',1,1,0,1,[20,0,0,2,18,0])],
  [k.current]:[node('GROUP',k.wallet,k.current,'Wallet accounts',2,3,0,3,[10,0,12,7,15,0])],
  [k.wallet]:[node('ACCOUNT','account:'+uuid(46),k.wallet,'Cash account',3,0,0,1,[10,0,5,0,15,0]),node('ACCOUNT','account:'+uuid(47),k.wallet,'Moving clearing',3,0,0,1,[0,0,7,7,0,0]),node('ACCOUNT','account:'+uuid(48),k.wallet,'Quiet account',3,0,0,1,[0,0,0,0,0,0])],
  [k.bank]:[node('ACCOUNT','account:'+uuid(49),k.bank,'Bank ledger',2,0,0,1,[20,0,0,2,18,0])],
  [k.liabilities]:[node('GROUP',k.payables,k.liabilities,'Current liabilities',1,1,0,1,[0,30,2,5,0,33])],
  [k.payables]:[node('ACCOUNT','account:'+uuid(50),k.payables,'Supplier payable',2,0,0,1,[0,30,2,5,0,33])],
};

/** Independent, balanced leaf amounts; clearing has movement and a zero closing. */
export async function hierarchyMock(...args:Parameters<typeof trialMock>):Promise<unknown>{
  if(!args[2].includes('/hierarchy?'))return trialMock(...args);
  const query=new URLSearchParams(args[2].split('?')[1]),period=query.get('period')??'CURRENT',factor=period==='COMPARATIVE'?2:1;
  const items=(hierarchyRows[query.get('parent') as keyof typeof hierarchyRows]??[])
    .filter(item=>query.get('show_zero')!=='false'||!item.data.is_zero)
    .map(item=>({...item,data:{...item.data,period,...Object.fromEntries(trialAmounts.map(key=>[key,String(BigInt(item.data[key].split('.')[0])*BigInt(factor))+'.0000']))}}));
  return {items,periods:['CURRENT','COMPARATIVE'],page:{next_cursor:null,has_more:false,limit:50},summary:{...amounts([30,30,14,14,33,33].map(value=>value*factor)),currency:'INR',account_count:5,opening_difference:'0.0000',period_difference:'0.0000',closing_difference:'0.0000'}};
}
