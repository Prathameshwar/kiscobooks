import { beforeAll, afterAll } from 'vitest';
import { configure, getConfig } from '@testing-library/react';
import {act,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {FrameworkReports,ReportWorkspace} from '../app/components/ReportWorkspace';
import {productFieldRequest} from '../app/lib/product-fields';

// Allow asynchronous UI effects to settle while local services share the runner's CPU.
const previousAsyncTimeout = getConfig().asyncUtilTimeout;
beforeAll(() => configure({ asyncUtilTimeout: 10000 }));
afterAll(() => configure({ asyncUtilTimeout: previousAsyncTimeout }));

vi.mock('../app/lib/product-fields',()=>({productFieldRequest:vi.fn()}));
vi.mock('../app/components/FinancialReports',()=>({FinancialReports:()=> <p>Classic reporting</p>}));
const api=vi.mocked(productFieldRequest);
const display={base_currency:'EUR',amount_precision:2,quantity_precision:3,rounding_mode:'half_even',
  date_format:'dd.MM.yyyy',datetime_format:'dd.MM.yyyy HH:mm',digit_grouping:'western',currency_display:'code',
  currency_symbol_position:'suffix',decimal_separator:',',thousands_separator:'.',negative_format:'parentheses',
  timezone:'Europe/Berlin',locale:'de-DE'};
const columns=[{key:'id',title:'Document',kind:'IDENTIFIER'},{key:'amount',title:'Amount',kind:'MONEY'}];
const definition={definition:{code:'TRIAL_BALANCE',version:2,title:'Trial balance',description:'Frozen company balances.',
  views:[{key:'default',title:'Statement',columns}]},parameter_schema:{properties:{date_from:{title:'From date',format:'date'},date_to:{title:'To date',format:'date'}},required:['date_from','date_to']},
  run_enabled:true,formats:['CSV','XLSX','HTML','PDF'],export_limits:['CSV','XLSX','HTML','PDF'].map(format=>({format,max_rows:5000,max_cells:200000}))};
const run={id:'run',code:'TRIAL_BALANCE',version:2,kind:'RUN',generation_id:'snapshot',title:'Trial balance',status:'COMPLETE',
  completed_rows:2,display,origin:null,views:definition.definition.views,parameters:{date_from:'2026-04-01',date_to:'2026-04-30'}};
beforeEach(()=>{
  sessionStorage.clear();
  api.mockReset();api.mockImplementation(async(_,method,path)=>{
    if(path.endsWith('/report-definitions'))return {items:[definition]};
    if(path.includes('/report-generations'))return {items:[{id:'snapshot',status:'READY',applied_sequence:20}]};
    if(path.includes('/report-runs?'))return {items:[],page:{next_cursor:null}};
    if(path.includes('/report-exports?'))return {items:[],page:{next_cursor:null}};
    if(path.endsWith('/cancel'))return {...run,status:'CANCELLED'};
    if(path.endsWith('/drilldowns'))return {...run,id:'child',status:'QUEUED',origin:{parent_id:'run'}};
    if(path.endsWith('/exports'))return {...run,id:'export',kind:'EXPORT',status:'QUEUED'};
    if(path.includes('/report-exports/'))return {...run,id:'export',kind:'EXPORT',status:'COMPLETE'};
    if(path.includes('/rows'))return {items:[{ordinal:path.includes('cursor')?51:1,data:{id:path.includes('cursor')?'second':'first',amount:'1234.5000'},drilldowns:[{key:'account_entries',title:'View account entries',token:'signed-row'}]}],page:{next_cursor:path.includes('cursor')?null:'next'}};
    return method==='POST'?{...run,status:'QUEUED'}:run;
  });
});
it('follows the selected year until custom dates are entered, then preserves dates and the retained result',async()=>{
  const original=api.getMockImplementation()!;let frozenParameters:Record<string,string>={};
  api.mockImplementation(async(...args)=>{
    if(args[1]==='POST'&&args[2].endsWith('/report-runs')){frozenParameters=(args[3] as {parameters:Record<string,string>}).parameters;return {...run,status:'QUEUED',parameters:frozenParameters};}
    if(args[1]==='GET'&&args[2].endsWith('/report-runs/run'))return {...run,parameters:frozenParameters};
    return original(...args);
  });
  const previous={id:'old',code:'FY2026',startDate:'2026-04-01',endDate:'2027-03-31',current:false,open:true};
  const selected={id:'new',code:'FY2027',startDate:'2027-04-01',endDate:'2028-03-31',current:true,open:true};
  const props={company:'company',permissions:['report.read'],years:[previous,selected]};
  const result=render(<FrameworkReports {...props} year={selected}/>);
  fireEvent.click(screen.getByText('Load report workspace'));await screen.findByRole('option',{name:'Trial balance'});
  fireEvent.change(screen.getByLabelText('Report'),{target:{value:'TRIAL_BALANCE'}});
  fireEvent.change(screen.getByLabelText('Source snapshot'),{target:{value:'snapshot'}});
  await waitFor(()=>expect(screen.getByLabelText('From date')).toHaveValue(selected.startDate));
  expect(screen.getByLabelText('To date')).toHaveValue(selected.endDate);
  fireEvent.change(screen.getByLabelText('Report period'),{target:{value:'previous'}});
  await waitFor(()=>expect(screen.getByLabelText('From date')).toHaveValue(previous.startDate));
  fireEvent.change(screen.getByLabelText('From date'),{target:{value:'2026-06-01'}});
  fireEvent.click(screen.getByText('Create report'));await screen.findByText(/^Report: QUEUED/);
  fireEvent.click(screen.getByText('Refresh report'));await screen.findByText('1.234,50');
  result.rerender(<FrameworkReports {...props} year={previous}/>);
  expect(screen.getByLabelText('From date')).toHaveValue('2026-06-01');
  expect(screen.getByText('1.234,50')).toBeVisible();
});
afterEach(()=>{vi.useRealTimers();vi.restoreAllMocks();});
function view(permissions=['report.read','report.export']){render(<FrameworkReports company="company" permissions={permissions}/>);}
async function choose(){
  fireEvent.click(screen.getByRole('button',{name:'Load report workspace'}));await screen.findByRole('option',{name:'Trial balance'});
  fireEvent.change(screen.getByLabelText('Report'),{target:{value:'TRIAL_BALANCE'}});
  fireEvent.change(screen.getByLabelText('Source snapshot'),{target:{value:'snapshot'}});
  fireEvent.change(screen.getByLabelText('From date'),{target:{value:'2026-04-01'}});
  fireEvent.change(screen.getByLabelText('To date'),{target:{value:'2026-04-30'}});
}
it('preselects the native report from its card after discovery without creating a run',async()=>{
  render(<FrameworkReports company="company" permissions={['report.read']} initialReport="TRIAL_BALANCE"/>);
  fireEvent.click(screen.getByRole('button',{name:'Load report workspace'}));await screen.findByRole('option',{name:'Trial balance'});
  await waitFor(()=>expect(screen.getByLabelText('Report')).toHaveValue('TRIAL_BALANCE'));
  expect(api.mock.calls.every(call=>call[1]==='GET')).toBe(true);
});

it('loads native discovery, sources and history automatically without creating a report',async()=>{
 render(<FrameworkReports company="company" permissions={['report.read']} initialReport="TRIAL_BALANCE"/>);
 await screen.findByRole('option',{name:'Trial balance'});
 await waitFor(()=>expect(screen.getByLabelText('Report')).toHaveValue('TRIAL_BALANCE'));
 expect(api.mock.calls.every(call=>call[1]==='GET')).toBe(true);
 expect(api.mock.calls.some(call=>call[2].includes('/report-runs?'))).toBe(true);
});
it('preselects a party ledger reference and prevents execution when its company scope fails',async()=>{
 const party='10000000-0000-7000-8000-000000000001';
 const original=api.getMockImplementation()!;
 const ledger={...definition,definition:{...definition.definition,code:'PARTY_LEDGER',title:'Party ledger'},parameter_schema:{properties:{party_id:{title:'Party',type:'string',format:'uuid'}},required:['party_id']}};
 api.mockImplementation(async(...args)=>args[2].endsWith('/report-definitions')?{items:[ledger]}:args[2].includes('/parties/')?{id:party,company_id:'foreign',name:'Wrong-company party'}:original(...args));
 render(<FrameworkReports company="company" permissions={['report.read']} initialReport="PARTY_LEDGER" initialParty={party}/>);
 await screen.findByText('Report reference ownership could not be verified.');
 fireEvent.change(screen.getByLabelText('Source snapshot'),{target:{value:'snapshot'}});
 expect(screen.getByRole('button',{name:'Create report'})).toBeDisabled();
 expect(screen.queryByText('Wrong-company party')).not.toBeInTheDocument();
 await act(async()=>{fireEvent.submit(screen.getByRole('button',{name:'Create report'}).closest('form')!);});
 expect(api.mock.calls.every(call=>call[1]==='GET')).toBe(true);
});

it('distinguishes repeated native history entries by timestamp and identity',async()=>{
 const original=api.getMockImplementation()!;
 api.mockImplementation(async(...args)=>args[2].includes('/report-runs?')?{items:[{id:'first',code:'TRIAL_BALANCE',status:'COMPLETE',created_at:'2026-10-30T01:00:00Z'},{id:'second',code:'TRIAL_BALANCE',status:'COMPLETE',created_at:'2026-10-30T02:00:00Z'}],page:{next_cursor:null}}:original(...args));
 view();fireEvent.click(screen.getByRole('button',{name:'Load report workspace'}));
 const first=await screen.findByRole('button',{name:/TRIAL BALANCE.*first/});
 expect(first).not.toHaveAccessibleName(screen.getByRole('button',{name:/TRIAL BALANCE.*second/}).getAttribute('aria-label')??'');
});
it('does not select a stale or unauthorised card report that discovery no longer advertises',async()=>{
  render(<FrameworkReports company="company" permissions={['report.read']} initialReport="BALANCE_SHEET"/>);
  fireEvent.click(screen.getByRole('button',{name:'Load report workspace'}));
  expect(await screen.findByText(/The selected report is not available/)).toBeVisible();
  expect(screen.getByLabelText('Report')).toHaveValue('');
  expect(api.mock.calls.every(call=>call[1]==='GET')).toBe(true);
});
it('sends native integer-array report parameters as arrays instead of comma-separated text',async()=>{
  const original=api.getMockImplementation()!;
  const inventory={...definition,definition:{...definition.definition,code:'STOCK_AGEING',title:'Stock ageing'},parameter_schema:{properties:{as_of:{title:'As of',type:'string',format:'date'},buckets:{title:'Age buckets',type:'array',items:{type:'integer'},default:[30,60,90,180]}},required:['as_of']}};
  api.mockImplementation(async(...args)=>args[2].endsWith('/report-definitions')?{items:[inventory]}:original(...args));
  render(<FrameworkReports company="company" permissions={['report.read']} initialReport="STOCK_AGEING"/>);
  fireEvent.click(screen.getByText('Load report workspace'));await screen.findByLabelText('Age buckets');
  fireEvent.change(screen.getByLabelText('Source snapshot'),{target:{value:'snapshot'}});
  fireEvent.change(screen.getByLabelText('As of'),{target:{value:'2026-10-30'}});
  fireEvent.change(screen.getByLabelText('Age buckets'),{target:{value:'30, 90, 180'}});
  fireEvent.click(screen.getByText('Create report'));await screen.findByText(/^Report: QUEUED/);
  expect(api.mock.calls.find(call=>call[1]==='POST')?.[3]).toMatchObject({parameters:{buckets:[30,90,180]}});
});
it('renders native boolean report settings as checked controls',async()=>{
  const original=api.getMockImplementation()!;
  const inventory={...definition,parameter_schema:{properties:{include_inactive:{title:'Include inactive',type:'boolean',default:true}},required:[]}};
  api.mockImplementation(async(...args)=>args[2].endsWith('/report-definitions')?{items:[inventory]}:original(...args));
  render(<FrameworkReports company="company" permissions={['report.read']} initialReport="TRIAL_BALANCE"/>);
  fireEvent.click(screen.getByText('Load report workspace'));
  expect(await screen.findByRole('checkbox',{name:'Include inactive'})).toBeChecked();
});
it('uses inventory groups instead of financial account groups for stock report selection',async()=>{
  const original=api.getMockImplementation()!;
  const inventory={...definition,definition:{...definition.definition,code:'STOCK_SUMMARY',title:'Stock summary',datasets:['inventory']},parameter_schema:{properties:{group_id:{title:'Item group',anyOf:[{type:'string',format:'uuid'},{type:'null'}]}},required:[]}};
  api.mockImplementation(async(...args)=>{
    if(args[2].endsWith('/report-definitions'))return {items:[inventory]};
    if(args[2].includes('/item-groups?')||args[2].includes('/account-groups?'))return {items:[],page:{next_cursor:null}};
    return original(...args);
  });
  render(<FrameworkReports company="company" permissions={['report.read']} initialReport="STOCK_SUMMARY"/>);
  fireEvent.click(screen.getByText('Load report workspace'));const control=await screen.findByRole('combobox',{name:'Item group'});
  fireEvent.focus(control);
  await waitFor(()=>expect(api.mock.calls.some(call=>call[0]==='catalog'&&call[2].includes('/item-groups?'))).toBe(true));
  expect(api.mock.calls.some(call=>call[2].includes('/account-groups?'))).toBe(false);
});
it('creates a report, formats frozen rows, keeps paging bounded and exports independently',async()=>{
  view();await choose();fireEvent.click(screen.getByText('Create report'));await screen.findByText(/^Report: QUEUED/);
  fireEvent.click(screen.getByText('Refresh report'));await screen.findByText('1.234,50');
  expect(api.mock.calls.find(call=>call[1]==='POST')?.[3]).toMatchObject({generation_id:'snapshot',view:'default',parameters:{date_from:'2026-04-01',date_to:'2026-04-30'}});
  fireEvent.click(screen.getByText('Next report page'));await screen.findByText('second');expect(screen.queryByText('first')).not.toBeInTheDocument();
  fireEvent.click(screen.getByText('First report page'));await screen.findByText('first');
  fireEvent.click(screen.getByText('Export PDF'));await screen.findByText(/^Export: QUEUED/);
  fireEvent.click(screen.getByText('Refresh export'));expect(await screen.findByRole('link',{name:'Download export'})).toHaveAttribute('href','/api/report-download?company=company&export=export');
  expect(screen.getByRole('table')).toBeInTheDocument();
});
it('preserves submission identity after a network failure and offers cancellation',async()=>{
  const base=api.getMockImplementation()!;let attempts=0;
  api.mockImplementation(async(...args)=>args[1]==='POST'&&args[2].endsWith('/report-runs')&&attempts++===0?Promise.reject(new Error('Offline')):base(...args));
  view();await choose();fireEvent.click(screen.getByText('Create report'));await screen.findByText('Offline');
  fireEvent.click(screen.getByText('Create report'));await screen.findByText(/^Report: QUEUED/);
  const calls=api.mock.calls.filter(call=>call[1]==='POST');expect(calls[0][4]).toBe(calls[1][4]);
  fireEvent.click(screen.getByText('Cancel report'));await screen.findByText(/^Report: CANCELLED/);
});
it('uses the signed drilldown and can return to its parent',async()=>{
  view();await choose();fireEvent.click(screen.getByText('Create report'));await screen.findByText(/^Report: QUEUED/);
  fireEvent.click(screen.getByText('Refresh report'));await screen.findByText('View account entries');
  fireEvent.click(screen.getByText('View account entries'));await screen.findByText('Back to parent report');
  expect(api.mock.calls.find(call=>call[2].endsWith('/drilldowns'))?.[3]).toEqual({token:'signed-row'});
  fireEvent.click(screen.getByText('Back to parent report'));await screen.findByRole('table');
});
it('reads and closes retained row detail with its signed GET token',async()=>{
  const base=api.getMockImplementation()!;
  api.mockImplementation(async(...args)=>{
    if(args[2].includes('/rows/1?token='))return {ordinal:1,data:{reference:'INV-DETAIL',amount:'10.0000'},drilldowns:[]};
    if(args[2].includes('/rows'))return {items:[{ordinal:1,data:{id:'first',amount:'1234.5000'},drilldowns:[{key:'row_detail',title:'View retained row detail',method:'GET',token:'signed-detail'}]}],page:{next_cursor:null}};
    return base(...args);
  });
  view();await choose();fireEvent.click(screen.getByText('Create report'));await screen.findByText(/^Report: QUEUED/);
  fireEvent.click(screen.getByText('Refresh report'));await screen.findByText('View retained row detail');
  fireEvent.click(screen.getByText('View retained row detail'));await screen.findByText('INV-DETAIL');
  expect(screen.getByText('10,00')).toBeInTheDocument();
  expect(api.mock.calls.find(call=>call[2].includes('/rows/1?token='))?.[1]).toBe('GET');
  expect(api.mock.calls.some(call=>call[2].endsWith('/drilldowns'))).toBe(false);
  fireEvent.click(screen.getByText('Close row detail'));expect(screen.queryByText('INV-DETAIL')).not.toBeInTheDocument();
});
it('hides exports without permission and disables unavailable admission',async()=>{
  const base=api.getMockImplementation()!;
  api.mockImplementation(async(...args)=>args[2].endsWith('/report-definitions')?{items:[{...definition,run_enabled:false,formats:[],export_limits:[]}]}:base(...args));
  view(['report.read']);await choose();expect(screen.getByText('Create report')).toBeDisabled();
  expect(screen.queryByText('Export CSV')).not.toBeInTheDocument();expect(screen.queryByText('Refresh report sources')).not.toBeInTheDocument();
});
it.each(['401 Session expired','403 Access denied','422 Invalid selection','500 Service unavailable'])('shows %s without losing the workspace',async error=>{
  api.mockRejectedValue(new Error(error));view();fireEvent.click(screen.getByText('Load report workspace'));
  expect(await screen.findByRole('alert')).toHaveTextContent(error);expect(screen.getByRole('heading',{name:'Reports'})).toBeInTheDocument();
});
it('preserves access to the existing reports screen',async()=>{
  render(<ReportWorkspace company="company" permissions={['report.read']}/>);
  fireEvent.click(screen.getByText('Classic reports and banking'));await screen.findByText('Classic reporting');
  fireEvent.click(screen.getByRole('button',{name:'Report workspace'}));await waitFor(()=>expect(screen.getByRole('heading',{name:'Reports'})).toBeInTheDocument());
});
it('displays completed rows when the automatic poll finishes before a slower rows request',async()=>{
  const base=api.getMockImplementation()!;
  let finishRows!:()=>void;
  api.mockImplementation(async(...args)=>{
    if(args[2].includes('/rows'))await new Promise<void>(resolve=>{finishRows=resolve;});
    return base(...args);
  });
  view();await choose();vi.useFakeTimers();
  await act(async()=>{fireEvent.click(screen.getByText('Create report'));});
  await act(async()=>{await vi.advanceTimersByTimeAsync(2500);});
  await act(async()=>{finishRows();});
  expect(screen.getByText('1.234,50')).toBeInTheDocument();
});
it('restores saved filters when opening history instead of carrying a previous selection',async()=>{
  const base=api.getMockImplementation()!;
  api.mockImplementation(async(...args)=>args[2].includes('/report-runs?')?
    {items:[{id:'saved',code:'TRIAL_BALANCE',status:'COMPLETE'}],page:{next_cursor:null}}:base(...args));
  view();await choose();
  fireEvent.change(screen.getByLabelText('From date'),{target:{value:'2025-01-01'}});
  fireEvent.click(screen.getByRole('button',{name:/^TRIAL BALANCE · COMPLETE .*saved/}));
  await screen.findByRole('table');
  expect(screen.getByLabelText('From date')).toHaveValue('2026-04-01');
});

it('offers bulk execution, restores a named view and submits packaged presentation exports',async()=>{
  const base=api.getMockImplementation()!;
  const views=[...definition.definition.views,{key:'compact',title:'Compact',columns}];
  api.mockImplementation(async(...args)=>{
    if(args[2].endsWith('/report-definitions'))return {items:[{...definition,definition:{...definition.definition,views},execution_limits:{STANDARD:100,BULK:1000000},package_limits:{max_parts:100,max_rows:1000000}}]};
    if(args[2].includes('/report-runs?'))return {items:[{id:'saved',code:'TRIAL_BALANCE',status:'COMPLETE'}],page:{next_cursor:null}};
    if(args[2].endsWith('/saved'))return {...run,id:'saved',views,view:'compact',execution:'BULK'};
    return base(...args);
  });
  view();await choose();
  fireEvent.change(screen.getByLabelText('Report size'),{target:{value:'BULK'}});
  fireEvent.change(screen.getByLabelText('Report view'),{target:{value:'compact'}});
  fireEvent.click(screen.getByText('Create report'));await screen.findByText(/^Report: QUEUED/);
  expect(api.mock.calls.find(call=>call[1]==='POST')?.[3]).toMatchObject({view:'compact',execution:'BULK'});
  fireEvent.click(screen.getByRole('button',{name:/^TRIAL BALANCE · COMPLETE .*saved/}));await screen.findByRole('table');
  expect(screen.getByLabelText('Report view')).toHaveValue('compact');
  expect(screen.getByLabelText('Report size')).toHaveValue('BULK');
  fireEvent.change(screen.getByLabelText('PDF and HTML delivery'),{target:{value:'PACKAGE'}});
  fireEvent.click(screen.getByText('Export PDF'));await screen.findByText(/^Export: QUEUED/);
  expect(api.mock.calls.find(call=>call[2].endsWith('/exports'))?.[3]).toMatchObject({view:'compact',delivery:'PACKAGE'});
});
