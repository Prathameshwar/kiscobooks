import definitions from './analytics-definitions.json';
import {trialJob,trialProps,uuid} from './trial-balance-fixture';
import {isAnalyticsReport,type AnalyticsSummary} from '../app/lib/analytics-workspace';

export type CompletionCode=keyof typeof definitions;
export function completionFixture(code:CompletionCode,view='default'){
 const definition=definitions[code];
 const parameters:Record<string,unknown>=code==='SOURCE_RECONCILIATION'?{}:{date_from:'2026-04-01',date_to:code==='BALANCE_CONTINUITY'?'2027-03-31':'2026-04-30'};
 const summary:AnalyticsSummary|undefined=isAnalyticsReport(code)?{code,calculation_version:3,date_from:'2026-04-01',date_to:'2026-04-30',comparison_present:false,amounts:{CURRENT:{INR:{net_sales:'1000',net_profit:'600',total_expenses:'400',closing_cash:'600'}}},trends:[{period:'CURRENT',currency:'INR',date:'2026-04-01',net_sales:'1000',amount:'600'}],notices:['Figures retain their recorded currency and verified period.']}:undefined;
 if(summary&&(code==='BUYER_PROFIT'||code==='PRODUCT_PROFIT')){
  summary.amounts.CURRENT.INR={net_sales:'1000',cost:'400',gross_profit:'600',margin_percent:'60',unavailable_line_count:0};
  summary.trends=[];
  summary.notices=['Gross profit is net sales excluding GST, less verified actual stock cost, before shared overheads.',...(view==='groups'?['Overlapping group rows are not additive; summary totals count each source line once.']:[])];
 }
 const job={...trialJob,code,title:definition.definition.title,version:definition.definition.version,parameters,view,views:definition.definition.views,completed_rows:1,result:{evidence:summary?{analytics:summary}:{}}};
 const columns=job.views.find(item=>item.key===view)!.columns;
 const data=Object.fromEntries(columns.map(column=>[column.key,column.kind==='MONEY'?'-999999999999999.9999':column.kind==='DATE'?'2026-04-30':column.kind==='BOOLEAN'?true:column.kind==='INTEGER'?1:column.kind==='DECIMAL'?'12.0000':({label:'Verified buyer',account_name:'Operating account',account_code:'1101',bill_reference:'SALE-001',reference:'OPEN-001',period:'CURRENT',kind:'SOURCE_COUNT',source:'journal_line',currency:'INR',row_kind:code==='BALANCE_CONTINUITY'?'ACCOUNT_CONTINUITY':'ENTRY'} as Record<string,string>)[column.key]??'Verified evidence']));
 async function request(_service:unknown,method:string,path:string,body?:unknown):Promise<unknown>{
  if(path.includes('/report-definitions/'))return definition;
  if(path.includes('/report-generations?'))return {items:[{id:uuid(9),status:'READY'}],page:{next_cursor:null}};
  if(path.includes('/report-generations/'))return {id:uuid(9),status:'READY',manifest:{control:{coverage_start:'2020-01-01'}}};
  if(path.includes('/report-runs?'))return {items:[],page:{next_cursor:null}};
  if(path.includes('/rows?'))return {items:[{ordinal:1,data,drilldowns:[]}],page:{next_cursor:null}};
  if(path.endsWith('/exports'))return {...job,id:uuid(40),kind:'EXPORT',parameters:body};
  if(path.endsWith('/report-runs')&&method==='POST')return {...job,...body as object};
  return job;
 }
 return {definition,job,data,request,props:trialProps};
}
