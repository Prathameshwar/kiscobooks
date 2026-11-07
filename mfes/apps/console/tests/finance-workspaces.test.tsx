import {act,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {beforeEach,afterEach,expect,it,vi} from 'vitest';
import {FinanceReportWorkspace} from '../app/components/FinanceReportWorkspace';
import {financeWorkspaces,type FinanceReportCode} from '../app/lib/finance-workspace';
import {productFieldRequest} from '../app/lib/product-fields';
import {trialProps,trialJob,uuid} from './trial-balance-fixture';
vi.mock('../app/lib/product-fields',()=>({productFieldRequest:vi.fn()}));
const api=vi.mocked(productFieldRequest);
let code:FinanceReportCode='INCOME_EXPENSE';
const columns=[{key:'row_kind',title:'Line type',kind:'TEXT'},{key:'account_name',title:'Account',kind:'TEXT'},{key:'currency',title:'Currency',kind:'TEXT'},{key:'amount',title:'Amount',kind:'MONEY',currency_key:'currency'}];
const definition=()=>({definition:{code,version:6,views:[{key:'default',title:'Statement',columns,calculation:'detail'}]},parameter_schema:{required:['date_from','date_to'],properties:{date_from:{type:'string',format:'date'},date_to:{type:'string',format:'date'}}},run_enabled:true,export_limits:['PDF','XLSX','CSV'].map(format=>({format,max_rows:1000,max_cells:10000}))});
const job=()=>({...trialJob,code,title:financeWorkspaces[code].title,parameters:{date_from:'2026-04-01',date_to:'2027-03-31'},views:definition().definition.views,completed_rows:1,result:{evidence:{}}});
async function mock(_service:unknown,method:string,path:string,body?:unknown,_key?:string,_signal?:AbortSignal):Promise<unknown>{
 if(path.includes('/report-definitions/'))return definition();
 if(path.includes('/report-generations?'))return {items:[{id:uuid(9),status:'READY'}],page:{next_cursor:null}};
 if(path.includes('/report-generations/'))return {id:uuid(9),status:'READY',manifest:{control:{coverage_start:'2020-01-01'}}};
 if(path.endsWith('/report-generations')&&method==='POST')return {id:uuid(9),status:'READY'};
 if(path.endsWith('/report-runs')&&method==='POST')return {...job(),parameters:(body as {parameters:object}).parameters,view:(body as {view:string}).view};
 if(path.includes('/rows?'))return {items:[{ordinal:1,data:{row_kind:'NET_SURPLUS_DEFICIT',account_name:'Verified account',amount:'1234.5600',currency:'INR'},drilldowns:[]}],page:{next_cursor:null}};
 if(path.endsWith('/exports'))return {...job(),id:uuid(40),kind:'EXPORT',parameters:body};
 if(path.endsWith('/cancel'))return {...job(),status:'CANCELLED'};
 return job();
}
const mount=(permissions=['report.read','report.export','report.definition.manage'],initialRun?:string)=>render(<FinanceReportWorkspace {...trialProps} report={code} permissions={permissions} initialRun={initialRun}/>);
beforeEach(()=>{code='INCOME_EXPENSE';localStorage.clear();api.mockReset();api.mockImplementation(mock as typeof productFieldRequest);vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(()=>{});});
afterEach(()=>vi.restoreAllMocks());
it.each(Object.keys(financeWorkspaces) as FinanceReportCode[])('prepares %s with its own title, report identity and export',async report=>{
 code=report;mount();await screen.findByText('Verified account');expect(screen.getByRole('heading',{name:financeWorkspaces[code].title})).toBeVisible();
 expect(screen.getByRole('link',{name:'Finance'})).toHaveAttribute('href','/reports/finance');
 expect(screen.queryByRole('form')).not.toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'Print / PDF'}));await screen.findByRole('link',{name:'Download report'});
 expect(HTMLAnchorElement.prototype.click).toHaveBeenCalledOnce();
 expect(api.mock.calls.find(call=>call[2].endsWith('/exports'))?.[3]).toMatchObject({format:'PDF',view:'default'});
});
it('shows editable filters and preserves the completed result when replacement fails',async()=>{
 mount();await screen.findByText('Verified account');fireEvent.click(screen.getByRole('button',{name:'Filters'}));
 fireEvent.change(screen.getByLabelText('From date'),{target:{value:'2026-05-01'}});
 expect(screen.getByRole('button',{name:'Print / PDF'})).toBeDisabled();
 api.mockImplementation(async(...args)=>args[1]==='POST'&&args[2].endsWith('/report-runs')?Promise.reject(new Error('Unavailable source')):mock(...args));
 fireEvent.click(screen.getByRole('button',{name:'Apply'}));await screen.findByText('Unavailable source');expect(screen.getByText('Verified account')).toBeVisible();
});
it('automatically prepares a missing source',async()=>{
 api.mockImplementation(async(...args)=>args[2].includes('/report-generations?')?{items:[],page:{next_cursor:null}}:mock(...args));mount();await screen.findByText('Verified account');
 expect(api.mock.calls.filter(call=>call[1]==='POST'&&call[2].endsWith('/report-generations'))).toHaveLength(1);
});
it('refreshes a verification failure once then retains the completed result',async()=>{
 let count=0;api.mockImplementation(async(...args)=>args[1]==='POST'&&args[2].endsWith('/report-runs')&&++count===1?{...job(),status:'BLOCKED',failure_code:'REPORT_VERIFICATION_FAILED'}:mock(...args));
 mount();await screen.findByText('Verified account');expect(count).toBe(2);
});
it('rebuilds a quarantined refresh as a fully verified snapshot without changing report dates',async()=>{
 let runs=0;api.mockImplementation(async(...args)=>{
  if(args[1]==='POST'&&args[2].endsWith('/report-runs')&&++runs===1)return {...job(),status:'BLOCKED',failure_code:'REPORT_VERIFICATION_FAILED'};
  if(args[1]==='POST'&&args[2].endsWith('/report-generations')&&(args[3] as {strategy:string}).strategy==='REFRESH')return {id:uuid(30),status:'QUARANTINED'};
  return mock(...args);
 });
 mount();await screen.findByText('Verified account');
 expect(api.mock.calls.filter(call=>call[1]==='POST'&&call[2].endsWith('/report-generations')).map(call=>call[3])).toEqual([{strategy:'REFRESH',base_generation_id:uuid(9)},{strategy:'FRESH'}]);
 const commands=api.mock.calls.filter(call=>call[1]==='POST'&&call[2].endsWith('/report-runs'));expect(commands[0][3]).toMatchObject({parameters:(commands[1][3] as {parameters:object}).parameters});
});
it('stops recovery after one refresh and one rejected full rebuild',async()=>{
 api.mockImplementation(async(...args)=>{
  if(args[1]==='POST'&&args[2].endsWith('/report-runs'))return {...job(),status:'BLOCKED',failure_code:'REPORT_VERIFICATION_FAILED'};
  if(args[1]==='POST'&&args[2].endsWith('/report-generations'))return {id:uuid(30),status:'QUARANTINED'};
  return mock(...args);
 });
 mount();await screen.findByText(/Accounting source rebuild did not complete/);
 expect(api.mock.calls.filter(call=>call[1]==='POST'&&call[2].endsWith('/report-generations'))).toHaveLength(2);
 expect(screen.queryByText('Verified account')).not.toBeInTheDocument();
});
it('stops a queued run from the top progress control',async()=>{
 api.mockImplementation(async(...args)=>args[1]==='POST'&&args[2].endsWith('/report-runs')?{...job(),status:'QUEUED'}:mock(...args));
 mount();fireEvent.click(await screen.findByRole('button',{name:'Stop report'}));await screen.findByText('Report stopped. Apply filters to run it again.');
 expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
});
it('opens a retained report without creating a new one',async()=>{
 mount(undefined,trialJob.id);await screen.findByText('Verified account');expect(api.mock.calls.filter(call=>call[1]==='POST')).toHaveLength(0);
});
it('keeps the return link for an account ledger opened from Trial Balance',async()=>{
 code='ACCOUNT_LEDGER';render(<FinanceReportWorkspace {...trialProps} report={code} initialRun={trialJob.id} trialBalanceRun={uuid(99)}/>);
 await screen.findByText('Verified account');expect(screen.getByRole('link',{name:'Back to Trial Balance'})).toHaveAttribute('href','/reports/workspace?report=TRIAL_BALANCE&run='+uuid(99));
});
it('removes retained amounts when the server revokes access',async()=>{
 mount();await screen.findByText('Verified account');api.mockRejectedValue(Object.assign(new Error('Access revoked'),{status:403}));
 fireEvent.click(screen.getByRole('button',{name:'Refresh'}));await screen.findByRole('alert');expect(screen.queryByText('Verified account')).not.toBeInTheDocument();
});
it('clears financial rows when history discovery revokes access',async()=>{
 mount();await screen.findByText('Verified account');api.mockRejectedValue(Object.assign(new Error('Access revoked'),{status:403}));
 fireEvent.click(screen.getByRole('button',{name:'Income and expenditure history'}));await screen.findByRole('alert');expect(screen.queryByText('Verified account')).not.toBeInTheDocument();
});
it('does not request data without report permission',()=>{mount([]);expect(screen.getByRole('alert')).toBeVisible();expect(api).not.toHaveBeenCalled();});

it('keeps explanatory text collapsed in one compact scope row',async()=>{
 mount();await screen.findByText('Verified account');const note=screen.getByText(financeWorkspaces[code].note);
 expect(note.closest('details')).not.toHaveAttribute('open');expect(note).not.toBeVisible();
});
it('does not refresh source data for a report worker version mismatch',async()=>{
 api.mockImplementation(async(...args)=>args[1]==='POST'&&args[2].endsWith('/report-runs')?{...job(),status:'BLOCKED',failure_code:'REPORT_IMPLEMENTATION_UNAVAILABLE'}:mock(...args));
 mount();await screen.findByText(/report service was updated/i);
 expect(api.mock.calls.filter(call=>call[1]==='POST'&&call[2].endsWith('/report-generations'))).toHaveLength(0);
});
