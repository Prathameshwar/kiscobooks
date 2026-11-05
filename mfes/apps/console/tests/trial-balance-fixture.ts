export const trialCompany='01990000-0000-7000-8000-000000000001';
export const trialRun='01990000-0000-7000-8000-000000000002';
export const uuid=(suffix:number)=>'01990000-0000-7000-8000-'+String(suffix).padStart(12,'0');
export const head='head:'+uuid(3),group='group:'+uuid(4),account='account:'+uuid(5);
const amount={opening_debit:'100.0000',opening_credit:'100.0000',period_debit:'220.0000',period_credit:'220.0000',closing_debit:'260.0000',closing_credit:'260.0000'};
const summary={...amount,currency:'INR',account_count:3,opening_difference:'0.0000',period_difference:'0.0000',closing_difference:'0.0000'};
export const row=(kind:string,key:string,parent:string,name:string,depth:number,children:number)=>({ordinal:depth+1,data:{...amount,row_kind:kind,node_key:key,parent_key:parent,code:name.slice(0,5),name,depth,child_count:children,group_child_count:kind==='HEAD'?1:0,account_count:3,is_zero:false,period:'CURRENT',currency:'INR',head_id:uuid(3)},drilldowns:kind==='ACCOUNT'?[{key:'row_detail',title:'Details',token:'detail'},{key:'account_entries',title:'Account entries',token:'signed-account'}]:[]});
const display={company_label:'Example Company',base_currency:'INR',amount_precision:2,quantity_precision:3,rounding_mode:'half_up',date_format:'dd MMM yyyy',datetime_format:'dd MMM yyyy HH:mm',digit_grouping:'indian',currency_display:'code',currency_symbol_position:'prefix',decimal_separator:'.',thousands_separator:',',negative_format:'minus',timezone:'Asia/Kolkata',locale:'en-IN'};
const columns=[{key:'name',title:'Account / group',kind:'TEXT'},{key:'closing_debit',title:'Debit',kind:'MONEY'},{key:'closing_credit',title:'Credit',kind:'MONEY'}];
export const trialDefinition={definition:{code:'TRIAL_BALANCE',version:6,title:'Trial Balance',views:[{key:'default',title:'Closing balances',columns},{key:'detailed',title:'Opening and movement',columns}]},parameter_schema:{properties:{}},run_enabled:true,export_limits:['PDF','XLSX','CSV','HTML'].map(format=>({format,max_rows:5000,max_cells:200000}))};
export const trialJob={id:trialRun,kind:'RUN',code:'TRIAL_BALANCE',version:6,status:'COMPLETE',generation_id:uuid(9),parameters:{date_from:'2026-04-01',date_to:'2026-04-30'},view:'default',views:trialDefinition.definition.views,display,completed_rows:7};
export function trialMock(_service:unknown,method:string,path:string,body?:unknown,_key?:string,_signal?:AbortSignal):Promise<unknown>{
  if(path.endsWith('/report-definitions/TRIAL_BALANCE'))return Promise.resolve(trialDefinition);
  if(path.includes('/report-generations?'))return Promise.resolve({items:[{id:uuid(9),status:'READY'}],page:{next_cursor:null}});
  if(path.endsWith('/report-generations/'+uuid(9)))return Promise.resolve({id:uuid(9),status:'READY',manifest:{control:{coverage_start:'2020-01-01'}}});
  if(path.includes('/hierarchy?')){
    const query=new URLSearchParams(path.split('?')[1]),parent=query.get('parent');
    const items=parent==='root'?[row('HEAD',head,'root','Assets',0,1)]:parent===head?[row('GROUP',group,head,'Current assets',1,1)]:[row('ACCOUNT',account,group,'Cash in hand',2,0)];
    return Promise.resolve({items,summary,page:{next_cursor:null,has_more:false,limit:50},periods:['CURRENT']});
  }
  if(path.endsWith('/exports'))return Promise.resolve({...trialJob,id:uuid(10),kind:'EXPORT',parameters:body,status:'COMPLETE'});
  if(path.includes('/report-runs?'))return Promise.resolve({items:[],page:{next_cursor:null}});
  return Promise.resolve(trialJob);
}
export const trialProps={company:trialCompany,companyName:'Example Company',actor:uuid(8),permissions:['report.read','report.export'],year:{id:uuid(20),code:'FY2026',startDate:'2026-04-01',endDate:'2027-03-31',current:true,open:true}};
