import definitions from './finance-definitions.json';
import {trialJob,trialProps,uuid} from './trial-balance-fixture';
import type {FinanceReportCode} from '../app/lib/finance-workspace';

/** Real catalog schemas and projections, with synthetic financial records. */
export function financeFixture(code:FinanceReportCode,view='default') {
  const definition=definitions[code];
  const parameters:Record<string,unknown>={date_to:'2026-04-30'};
  for(const [key,raw] of Object.entries(definition.parameter_schema.properties)) {
    const field=raw as {default?:unknown};
    if(field.default!==undefined&&field.default!==null)parameters[key]=field.default;
    if(key==='date_from')parameters[key]='2026-04-01';
  }
  if(code.startsWith('BANK_RECONCILIATION'))parameters.account_id=uuid(5);
  if(code==='BANK_RECONCILIATION')parameters.statement_balance='100.0000';
  if(['BANK_RECONCILIATION_EVIDENCE','BANK_RECONCILIATION_WORKLIST'].includes(code))parameters.currency='INR';
  if(code==='BANK_RECONCILIATION_EVIDENCE')parameters.session_id=uuid(6);
  const job={...trialJob,code,title:code.replaceAll('_',' '),parameters,view,views:definition.definition.views,completed_rows:1,result:{evidence:{}}};
  const columns=job.views.find(item=>item.key===view)!.columns;
  const data=Object.fromEntries(columns.map(column=>[column.key,column.kind==='MONEY'?'-999999999999999.9999':column.kind==='DATE'?'2026-04-30':column.kind==='BOOLEAN'?true:column.kind==='DECIMAL'?'1.0000':({account_name:'Verified account',account_code:'1101',period:'CURRENT',currency:'INR',report_currency:'INR',row_kind:code==='INCOME_EXPENSE'?'NET_SURPLUS_DEFICIT':'ENTRY'} as Record<string,string>)[column.key]??'Recorded detail']));
  async function request(service:unknown,method:string,path:string,body?:unknown):Promise<unknown>{
    if(service==='accounting')return {id:path.split('/').at(-1),company_id:trialProps.company,account_id:uuid(5),kind:code==='CASH_BOOK'?'CASH':'BANK',name:'Operating bank',code:'1101',currency:'INR',period_from:'2026-04-01',period_to:'2026-04-30',status:'FINALIZED'};
    if(path.includes('/report-definitions/'))return definition;
    if(path.includes('/report-generations?'))return {items:[{id:uuid(9),status:'READY'}],page:{next_cursor:null}};
    if(path.includes('/report-generations/'))return {id:uuid(9),status:'READY',verified_at:'2026-11-03T08:00:00Z',manifest:{control:{coverage_start:'2020-01-01'}}};
    if(path.includes('/rows?'))return {items:[{ordinal:1,data,drilldowns:[]}],page:{next_cursor:null}};
    if(path.endsWith('/exports'))return {...job,id:uuid(40),kind:'EXPORT',parameters:body};
    if(path.endsWith('/report-runs')&&method==='POST')return {...job,...body as object};
    return job;
  }
  return {definition,job,data,request};
}
