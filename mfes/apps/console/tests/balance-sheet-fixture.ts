import {trialJob,trialProps,uuid} from './trial-balance-fixture';
export const balanceProps={...trialProps,year:{...trialProps.year,current:false},years:[trialProps.year],permissions:['report.read','report.export','report.definition.manage']};
const columns=[{key:'label',title:'Account / group',kind:'TEXT'},{key:'amount',title:'Current',kind:'MONEY',currency_key:'currency'},{key:'currency',title:'Currency',kind:'TEXT'}];
export const balanceDefinition={definition:{code:'BALANCE_SHEET',version:6,title:'Balance Sheet',views:[{key:'default',title:'Standard',columns,calculation:'balance_standard'},{key:'comparison',title:'Comparative',columns:[...columns,{key:'previous_amount',title:'Previous',kind:'MONEY',currency_key:'currency'}],calculation:'balance_comparison'}]},run_enabled:true,export_limits:['PDF','XLSX','CSV','HTML'].map(format=>({format,max_rows:5000,max_cells:200000}))};
const totals={ASSET:{current:'100.0000',previous:'90.0000'},LIABILITY:{current:'30.0000',previous:'20.0000'},EQUITY:{current:'70.0000',previous:'70.0000'},LIABILITIES_EQUITY:{current:'100.0000',previous:'90.0000'}};
export const balanceJob={...trialJob,code:'BALANCE_SHEET',views:balanceDefinition.definition.views,parameters:{date_to:'2027-03-31',show_zero:false},result:{evidence:{balance_summary:{currency:'INR',balanced:true,difference:{current:'0.0000',previous:'0.0000'},totals}}}};
export const balanceRows=[
  {row_kind:'SECTION',section:'ASSET',side:'ASSETS',label:'Assets',amount:'100.0000'},
  {row_kind:'GROUP',section:'ASSET',side:'ASSETS',label:'Bank accounts',group_id:uuid(4),group_code:'BANK',amount:'100.0000'},
  {row_kind:'ACCOUNT',section:'ASSET',side:'ASSETS',label:'Operating bank account',group_id:uuid(4),group_name:'Bank accounts',account_id:uuid(5),account_code:'1001',amount:'100.0000'},
  {row_kind:'TOTAL',section:'ASSET',side:'ASSETS',label:'Total assets',amount:'100.0000'},
  {row_kind:'SECTION',section:'LIABILITY',side:'LIABILITIES_EQUITY',label:'Liabilities',amount:'30.0000'},
  {row_kind:'TOTAL',section:'LIABILITY',side:'LIABILITIES_EQUITY',label:'Total liabilities',amount:'30.0000'},
  {row_kind:'SECTION',section:'EQUITY',side:'LIABILITIES_EQUITY',label:'Equity',amount:'70.0000'},
  {row_kind:'EARNINGS',section:'EQUITY',side:'LIABILITIES_EQUITY',label:'Current year earnings',amount:'70.0000'},
  {row_kind:'TOTAL',section:'EQUITY',side:'LIABILITIES_EQUITY',label:'Total equity',amount:'70.0000'},
  {row_kind:'TOTAL',section:'LIABILITIES_EQUITY',side:'LIABILITIES_EQUITY',label:'Total liabilities and equity',amount:'100.0000'},
].map((data,index)=>({ordinal:index+1,data:{...data,currency:'INR',previous_amount:data.amount,change_amount:'0.0000',change_percent:'0.00%'},drilldowns:data.row_kind==='ACCOUNT'?[{key:'balance_account_entries',token:'current-token'},{key:'balance_comparison_entries',token:'prior-token'}]:[]}));
export async function balanceMock(_service:unknown,method:string,path:string,body?:unknown):Promise<unknown>{
  if(path.endsWith('/report-definitions/BALANCE_SHEET'))return balanceDefinition;
  if(path.includes('/report-generations?'))return {items:[{id:uuid(9),status:'READY'}],page:{next_cursor:null}};
  if(path.endsWith('/report-generations/'+uuid(9)))return {id:uuid(9),status:'READY',manifest:{control:{coverage_start:'2020-01-01'}}};
  if(path.endsWith('/report-runs')&&method==='POST')return {...balanceJob,view:(body as {view:string}).view,parameters:(body as {parameters:object}).parameters};
  if(path.includes('/rows?'))return {items:balanceRows,page:{next_cursor:null,has_more:false}};
  if(path.endsWith('/exports'))return {...balanceJob,id:uuid(40),kind:'EXPORT',parameters:body};
  if(path.endsWith('/drilldowns'))return {...balanceJob,id:uuid(41),code:'ACCOUNT_LEDGER'};
  if(path.includes('/report-runs?'))return {items:[balanceJob],page:{next_cursor:null}};
  return balanceJob;
}
