import {act,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {beforeEach,afterEach,expect,it,vi} from 'vitest';
import {ProfitLossWorkspace} from '../app/components/ProfitLossWorkspace';
import {productFieldRequest} from '../app/lib/product-fields';
import {goTo} from '../app/lib/navigate';
import {comparisonDates} from '../app/lib/profit-loss';
import {trialCompany,uuid,trialProps} from './trial-balance-fixture';

vi.mock('../app/lib/product-fields',async importOriginal=>({...await importOriginal<typeof import('../app/lib/product-fields')>(),productFieldRequest:vi.fn()}));
vi.mock('../app/lib/navigate',()=>({goTo:vi.fn()}));
vi.mock('../app/components/ReportWorkspace',()=>({ReportWorkspace:()=>null}));
const api=vi.mocked(productFieldRequest);
const display={company_label:'Example Company',base_currency:'INR',amount_precision:2,quantity_precision:3,rounding_mode:'half_up',date_format:'dd MMM yyyy',datetime_format:'dd MMM yyyy HH:mm',digit_grouping:'indian',currency_display:'code',currency_symbol_position:'prefix',decimal_separator:'.',thousands_separator:',',negative_format:'minus',timezone:'Asia/Kolkata',locale:'en-IN'};
const statement=[{key:'default',title:'Statement',calculation:'profit_statement',columns:[{key:'label',title:'Account / group',kind:'TEXT'},{key:'amount',title:'Current',kind:'MONEY',currency_key:'currency'},{key:'currency',title:'Currency',kind:'TEXT'}]},
  {key:'comparison',title:'Period comparison',calculation:'profit_comparison',columns:[{key:'label',title:'Account / group',kind:'TEXT'},{key:'amount',title:'Current',kind:'MONEY',currency_key:'currency'},{key:'previous_amount',title:'Previous',kind:'MONEY',currency_key:'currency'},{key:'currency',title:'Currency',kind:'TEXT'}]}];
const definition={definition:{code:'PROFIT_LOSS',version:6,title:'Profit and Loss',views:statement},parameter_schema:{properties:{}},run_enabled:true,export_limits:['PDF','XLSX','CSV','HTML'].map(format=>({format,max_rows:5000,max_cells:200000}))};
const result={evidence:{profit_summary:{currency:'INR',sections:{},totals:{TOTAL_INCOME:{current:'100.0000',previous:'90.0000'},TOTAL_EXPENSE:{current:'30.0000',previous:'20.0000'},GROSS_PROFIT:{current:'70.0000',previous:'70.0000'},NET_PROFIT:{current:'70.0000',previous:'70.0000'}}}}};
const job={id:uuid(31),kind:'RUN',code:'PROFIT_LOSS',version:6,status:'COMPLETE',generation_id:uuid(9),parameters:{date_from:'2026-04-01',date_to:'2026-04-30',show_zero:false},view:'default',views:statement,display,completed_rows:12,result};
const rows=[
  {ordinal:1,data:{row_kind:'SECTION',section:'DIRECT_INCOME',label:'Direct income',amount:'100.0000',currency:'INR'},drilldowns:[]},
  {ordinal:2,data:{row_kind:'GROUP',section:'DIRECT_INCOME',label:'Sales',group_id:'group-sales',group_code:'SALES',amount:'100.0000',currency:'INR'},drilldowns:[]},
  {ordinal:3,data:{row_kind:'ACCOUNT',section:'DIRECT_INCOME',label:'Sales revenue',group_id:'group-sales',group_name:'Sales',account_id:uuid(5),account_code:'4000',amount:'100.0000',previous_amount:'90.0000',change_amount:'10.0000',change_percent:'11.11%',currency:'INR'},drilldowns:[{key:'account_entries',title:'Account entries',token:'account-token'},{key:'comparison_account_entries',title:'Previous entries',token:'previous-token'}]},
];
const props={...trialProps,permissions:['report.read','report.export','report.definition.manage']};
function mock(_service:unknown,method:string,path:string,body?:unknown):Promise<unknown>{
  if(path.endsWith('/report-definitions/PROFIT_LOSS'))return Promise.resolve(definition);
  if(path.includes('/report-generations?'))return Promise.resolve({items:[{id:uuid(9),status:'READY'}],page:{next_cursor:null}});
  if(path.endsWith('/report-generations/'+uuid(9)))return Promise.resolve({id:uuid(9),status:'READY',manifest:{control:{coverage_start:'2020-01-01'}}});
  if(path.endsWith('/report-runs')&&method==='POST')return Promise.resolve({...job,id:uuid(body&&typeof body==='object'&&(body as {view?:string}).view==='comparison'?32:31),view:(body as {view:string}).view,parameters:(body as {parameters:object}).parameters});
  if(path.includes('/rows?'))return Promise.resolve({items:rows,page:{next_cursor:null,has_more:false,limit:200}});
  if(path.endsWith('/exports'))return Promise.resolve({...job,id:uuid(40),kind:'EXPORT',status:'COMPLETE',parameters:body});
  if(path.endsWith('/drilldowns'))return Promise.resolve({...job,id:uuid(41),code:'ACCOUNT_LEDGER'});
  if(path.includes('/report-runs?'))return Promise.resolve({items:[],page:{next_cursor:null}});
  return Promise.resolve(job);
}
beforeEach(()=>{api.mockReset();api.mockImplementation(mock as typeof productFieldRequest);vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(()=>{});});
afterEach(()=>{vi.restoreAllMocks();});

it('derives exact comparison dates including leap days',()=>{
  expect(comparisonDates('2026-04-01','2026-04-30','PREVIOUS')).toEqual({from:'2026-03-02',to:'2026-03-31'});
  expect(comparisonDates('2024-02-29','2024-03-31','LAST_YEAR')).toEqual({from:'2023-02-28',to:'2023-03-31'});
});

it('opens the statement with zero accounts unchecked and collapsible groups',async()=>{
  render(<ProfitLossWorkspace {...props}/>);
  await screen.findByText('Sales revenue');
  expect(screen.getByRole('radio',{name:'Statement'})).toHaveAttribute('aria-checked','true');
  expect(screen.queryByRole('region',{name:'Profit and Loss filters'})).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'Filters'}));
  expect(screen.getByRole('checkbox',{name:'Include zero accounts'})).not.toBeChecked();
  fireEvent.click(screen.getByRole('button',{name:'Collapse Sales'}));
  expect(screen.queryByText('Sales revenue')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'Expand Sales'}));
  expect(screen.getByText('Sales revenue')).toBeInTheDocument();
  expect(screen.getByText('Gross profit')).toBeInTheDocument();
});

it('runs the comparison with selected dates and exports that same view',async()=>{
  render(<ProfitLossWorkspace {...props}/>);await screen.findByText('Sales revenue');
  fireEvent.click(screen.getByRole('radio',{name:'Period comparison'}));
  await waitFor(()=>expect(api.mock.calls.filter(call=>call[2].endsWith('/report-runs')&&call[1]==='POST')).toHaveLength(2));
  const request=api.mock.calls.filter(call=>call[2].endsWith('/report-runs')&&call[1]==='POST')[1][3] as {view:string;parameters:Record<string,string>};
  expect(request.view).toBe('comparison');
  const initial=api.mock.calls.filter(call=>call[2].endsWith('/report-runs')&&call[1]==='POST')[0][3] as {parameters:{date_from:string;date_to:string}};
  const expected=comparisonDates(initial.parameters.date_from,initial.parameters.date_to,'PREVIOUS');
  expect(request.parameters).toMatchObject({comparative_from:expected.from,comparative_to:expected.to});
  await screen.findByRole('button',{name:'View previous entries for Sales revenue'});
  fireEvent.click(screen.getByRole('button',{name:'View previous entries for Sales revenue'}));
  await waitFor(()=>expect(api.mock.calls.some(call=>call[2].endsWith('/drilldowns')&&JSON.stringify(call[3])==='{"token":"previous-token"}')).toBe(true));
  fireEvent.click(screen.getByRole('button',{name:'Export PDF'}));
  await screen.findByRole('link',{name:'Download PDF'});
  expect(api.mock.calls.find(call=>call[2].endsWith('/exports'))![3]).toMatchObject({format:'PDF',view:'comparison'});
});

it('opens an account ledger through its scoped report drilldown',async()=>{
  render(<ProfitLossWorkspace {...props}/>);await screen.findByText('Sales revenue');
  fireEvent.click(screen.getByRole('button',{name:'Sales revenue'}));
  await waitFor(()=>expect(goTo).toHaveBeenCalledWith(expect.stringContaining('report=ACCOUNT_LEDGER')));
  expect(api.mock.calls.find(call=>call[2].endsWith('/drilldowns'))![3]).toEqual({token:'account-token'});
});

it('keeps an invalid date range within the filter panel',async()=>{
  render(<ProfitLossWorkspace {...props}/>);await screen.findByText('Sales revenue');
  fireEvent.click(screen.getByRole('button',{name:'Filters'}));
  fireEvent.change(screen.getByLabelText('From date'),{target:{value:'2026-12-01'}});
  fireEvent.click(screen.getByRole('button',{name:'Apply filters'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('From date must be on or before To date');
  expect(screen.getByLabelText('From date')).toBeInTheDocument();
});

it('keeps the completed statement and export view when comparison fails',async()=>{
  render(<ProfitLossWorkspace {...props}/>);await screen.findByText('Sales revenue');
  let rejectComparison!:(error:Error)=>void;
  api.mockImplementation((service,method,path,body)=>{
    if(path.endsWith('/report-runs')&&method==='POST')return new Promise((_resolve,reject)=>{rejectComparison=reject;});
    return mock(service,method,path,body) as ReturnType<typeof productFieldRequest>;
  });
  fireEvent.click(screen.getByRole('radio',{name:'Period comparison'}));
  expect(screen.queryByRole('columnheader',{name:'Previous'})).not.toBeInTheDocument();
  expect(screen.getByRole('button',{name:'Sales revenue'})).toBeDisabled();
  expect(screen.getByRole('radio',{name:'Statement'})).toBeDisabled();
  await act(async()=>rejectComparison(new Error('Comparison is unavailable')));
  expect(await screen.findByRole('alert')).toHaveTextContent('Comparison is unavailable');
  expect(screen.queryByRole('columnheader',{name:'Previous'})).not.toBeInTheDocument();
  expect(screen.getByText(/Showing the last completed report/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'Export PDF'}));
  await screen.findByRole('link',{name:'Download PDF'});
  expect(api.mock.calls.find(call=>call[2].endsWith('/exports'))![3]).toMatchObject({view:'default'});
});

it('stops a queued replacement while retaining the completed statement',async()=>{
  render(<ProfitLossWorkspace {...props}/>);await screen.findByText('Sales revenue');
  api.mockImplementation(async(service,method,path,body)=>{
    if(path.endsWith('/report-runs')&&method==='POST')return {...job,id:uuid(32),status:'QUEUED',view:'comparison'};
    if(path.endsWith('/cancel'))return {...job,id:uuid(32),status:'CANCELLED'};
    return mock(service,method,path,body);
  });
  fireEvent.click(screen.getByRole('radio',{name:'Period comparison'}));
  await screen.findByRole('progressbar',{name:'Report queued'});
  fireEvent.click(screen.getByRole('button',{name:'Stop Profit and Loss report'}));
  await screen.findByText('Report stopped');
  expect(screen.queryByRole('columnheader',{name:'Previous'})).not.toBeInTheDocument();
  expect(screen.getByRole('button',{name:'Sales revenue'})).toBeEnabled();
  expect(api.mock.calls.find(call=>call[2].endsWith('/cancel'))?.[2]).toContain(uuid(32));
});

it('closes applied filters and returns keyboard focus to their trigger',async()=>{
  render(<ProfitLossWorkspace {...props}/>);await screen.findByText('Sales revenue');
  fireEvent.click(screen.getByRole('button',{name:'Filters'}));
  fireEvent.click(screen.getByRole('button',{name:'Apply filters'}));
  await waitFor(()=>expect(screen.queryByRole('region',{name:'Profit and Loss filters'})).not.toBeInTheDocument());
  expect(screen.getByRole('button',{name:'Filters'})).toHaveFocus();
});

it('preserves the fiscal-year start when detailed history starts after imported YTD',async()=>{
 api.mockImplementation(async(service,method,path,body)=>path.includes('/report-generations/')?{id:uuid(9),status:'READY',manifest:{control:{coverage_start:'2026-10-31'}}}:mock(service,method,path,body));
 render(<ProfitLossWorkspace {...props}/>);await screen.findByText('Sales revenue');
 expect(api.mock.calls.find(call=>call[1]==='POST'&&call[2].endsWith('/report-runs'))?.[3]).toMatchObject({parameters:{date_from:'2026-04-01'}});
});

it('loads older history pages with a company-scoped cursor',async()=>{
 api.mockImplementation(async(service,method,path,body)=>path.includes('/report-runs?')?{items:[],page:{next_cursor:path.includes('cursor=')?null:'older cursor'}}:mock(service,method,path,body));
 render(<ProfitLossWorkspace {...props}/>);await screen.findByText('Sales revenue');
 fireEvent.click(screen.getByText('Report history and source details'));
 fireEvent.click(screen.getByRole('button',{name:'Load history'}));
 fireEvent.click(await screen.findByRole('button',{name:'Older reports'}));
 await waitFor(()=>expect(api.mock.calls.some(call=>call[2].includes('code=PROFIT_LOSS&cursor=older%20cursor'))).toBe(true));
});
