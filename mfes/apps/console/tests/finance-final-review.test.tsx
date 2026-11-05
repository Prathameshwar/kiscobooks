import {act,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {beforeEach,afterEach,expect,it,vi} from 'vitest';
import {FinanceReportWorkspace} from '../app/components/FinanceReportWorkspace';
import {productFieldRequest} from '../app/lib/product-fields';
import {financeFixture} from './finance-fixture';
import {trialProps,trialJob,uuid} from './trial-balance-fixture';
vi.mock('../app/lib/product-fields',()=>({productFieldRequest:vi.fn()}));
const api=vi.mocked(productFieldRequest);
beforeEach(()=>{api.mockReset();localStorage.clear();vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(()=>{});});
afterEach(()=>vi.restoreAllMocks());

it('review: opening history clears the previous result download',async()=>{
 const f=financeFixture('INCOME_EXPENSE');
 api.mockImplementation(async(service,method,path,body)=>{
  if(path.includes('/report-runs?'))return {items:[{...f.job,id:uuid(77),created_at:'2026-11-01T10:00:00Z'}],page:{next_cursor:null}};
  if(path.endsWith('/report-runs/'+uuid(77)))return {...f.job,id:uuid(77),parameters:{date_from:'2026-05-01',date_to:'2026-05-31'}};
  if(path.includes('/'+uuid(77)+'/rows?'))return {items:[{ordinal:1,data:{...f.data,account_name:'Historical account'},drilldowns:[]}],page:{next_cursor:null}};
  return f.request(service,method,path,body);
 });
 render(<FinanceReportWorkspace {...trialProps} report="INCOME_EXPENSE" initialRun={trialJob.id}/>);
 await screen.findByText('Verified account');fireEvent.click(screen.getByRole('button',{name:'Print / PDF'}));await screen.findByRole('link',{name:'Download report'});
 fireEvent.click(screen.getByRole('button',{name:'Income and expenditure history'}));fireEvent.click(await screen.findByRole('button',{name:/Completed/}));await screen.findByText('Historical account');
 expect(screen.queryByRole('link',{name:'Download report'})).not.toBeInTheDocument();
});

it('review: retained report opens when new runs are disabled',async()=>{
 const f=financeFixture('ACCOUNT_LEDGER');api.mockImplementation(async(service,method,path,body)=>path.includes('/report-definitions/')?{...f.definition,run_enabled:false}:f.request(service,method,path,body));
 await act(async()=>{render(<FinanceReportWorkspace {...trialProps} report="ACCOUNT_LEDGER" initialRun={trialJob.id}/>);});
 expect(api.mock.calls.some(call=>call[1]==='GET'&&call[2].endsWith('/report-runs/'+trialJob.id))).toBe(true);
});

it('review: Income and expenditure preserves fiscal-year start for eligible imported YTD',async()=>{
 const f=financeFixture('INCOME_EXPENSE');api.mockImplementation(async(service,method,path,body)=>path.includes('/report-generations/')?{id:uuid(9),status:'READY',manifest:{control:{coverage_start:'2026-10-31'}}}:f.request(service,method,path,body));
 render(<FinanceReportWorkspace {...trialProps} report="INCOME_EXPENSE"/>);await screen.findByText('Verified account');
 const command=api.mock.calls.find(call=>call[1]==='POST'&&call[2].endsWith('/report-runs'));
 expect(command?.[3]).toMatchObject({parameters:{date_from:'2026-04-01'}});
});

it('review: a ledger opened from a statement still offers export',async()=>{
 const f=financeFixture('ACCOUNT_LEDGER');api.mockImplementation(async(service,method,path,body)=>path.endsWith('/report-runs/'+trialJob.id)?{...f.job,origin:{parent_id:uuid(80),key:'account_entries'}}:f.request(service,method,path,body));
 render(<FinanceReportWorkspace {...trialProps} report="ACCOUNT_LEDGER" initialRun={trialJob.id}/>);
 await screen.findByText('Verified account');
 expect(screen.queryByRole('button',{name:'Print / PDF'})).toBeInTheDocument();
});

it('searches frozen rows through the bounded worker and exports that selected result',async()=>{
 const f=financeFixture('DAY_BOOK'),selected={...f.job,id:uuid(88),result:{selection:{parent_id:f.job.id},evidence:{}}};
 api.mockImplementation(async(service,method,path,body)=>{
  if(path.endsWith('/queries'))return selected;
  return f.request(service,method,path,body);
 });
 render(<FinanceReportWorkspace {...trialProps} report="DAY_BOOK" initialRun={f.job.id}/>);
 await screen.findByRole('form',{name:'Search report rows'});
 fireEvent.change(screen.getByLabelText('Search report'),{target:{value:'SALE'}});
 fireEvent.click(screen.getByRole('button',{name:'Search / sort'}));
 await screen.findByText(/Running balances retain the original calculation/);
 expect(api.mock.calls.find(call=>call[2].endsWith('/queries'))?.[3]).toEqual({q:'SALE',sort:'ordinal',filters:{}});
 fireEvent.click(screen.getByRole('button',{name:'Print / PDF'}));await screen.findByRole('link',{name:'Download report'});
 expect(api.mock.calls.some(call=>call[2].endsWith('/'+uuid(88)+'/exports'))).toBe(true);
 fireEvent.click(screen.getByRole('button',{name:'Clear row selection'}));
 await waitFor(()=>expect(screen.queryByText(/Running balances retain/)).not.toBeInTheDocument());
});

it('refreshes an aged source automatically before calculating a new report',async()=>{
 const f=financeFixture('INCOME_EXPENSE');
 api.mockImplementation(async(service,method,path,body)=>{
  if(path.endsWith('/report-generations')&&method==='POST')return {id:uuid(90),status:'READY'};
  if(path.includes('/report-generations/'))return {id:path.split('/').at(-1),status:'READY',verified_at:path.endsWith(uuid(9))?'2020-01-01T00:00:00Z':new Date().toISOString(),manifest:{control:{coverage_start:'2020-01-01'}}};
  return f.request(service,method,path,body);
 });
 render(<FinanceReportWorkspace {...trialProps} permissions={[...trialProps.permissions,'report.definition.manage']} report="INCOME_EXPENSE"/>);
 await screen.findByText('Verified account');
 expect(api.mock.calls.find(call=>call[1]==='POST'&&call[2].endsWith('/report-runs'))?.[3]).toMatchObject({generation_id:uuid(90)});
 expect(api.mock.calls.filter(call=>call[1]==='POST'&&call[2].endsWith('/report-generations'))).toHaveLength(1);
});

it('uses the retained money and date formats in summaries and the completed period caption',async()=>{
 const f=financeFixture('DAY_BOOK');
 api.mockImplementation(async(service,method,path,body)=>path.endsWith('/report-runs/'+f.job.id)?{...f.job,display:{...f.job.display,amount_precision:4,date_format:'yyyy-MM-dd'},result:{evidence:{book_summary:{code:'DAY_BOOK',record_count:1,entry_count:1,amounts:{INR:{debit:'1234.5678',credit:'1234.5678'}}}}}}:f.request(service,method,path,body));
 render(<FinanceReportWorkspace {...trialProps} report="DAY_BOOK" initialRun={f.job.id}/>);
 await screen.findByText(/^2026-04-01 to 2026-04-30/);
 expect(screen.getByLabelText('Day book summary')).toHaveTextContent('1,234.5678');
});
