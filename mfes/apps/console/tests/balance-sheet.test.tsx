import {act,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {BalanceSheetWorkspace} from '../app/components/BalanceSheetWorkspace';
import {productFieldRequest} from '../app/lib/product-fields';
import {balanceComparisonDate} from '../app/lib/balance-sheet';
import {balanceMock,balanceProps,balanceJob,balanceRows} from './balance-sheet-fixture';
import {uuid} from './trial-balance-fixture';

vi.mock('../app/lib/product-fields',async original=>({...await original<typeof import('../app/lib/product-fields')>(),productFieldRequest:vi.fn()}));
vi.mock('../app/lib/navigate',()=>({goTo:vi.fn()}));
vi.mock('../app/components/ReportWorkspace',()=>({ReportWorkspace:()=> <p>Legacy report</p>}));
const api=vi.mocked(productFieldRequest);
beforeEach(()=>{api.mockReset();api.mockImplementation(balanceMock as typeof productFieldRequest);vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(()=>{});});
afterEach(()=>vi.restoreAllMocks());
const submissions=()=>api.mock.calls.filter(call=>call[1]==='POST'&&call[2].endsWith('/report-runs'));

it('derives as-of comparison dates from financial years and leap dates',()=>{
  expect(balanceComparisonDate('2027-03-31','YEAR_END',balanceProps.years)).toBe('2026-03-31');
  expect(balanceComparisonDate('2024-03-15','MONTH_END',[])).toBe('2024-02-29');
  expect(balanceComparisonDate('2024-02-29','LAST_YEAR',[])).toBe('2023-02-28');
  expect(balanceComparisonDate('2028-04-01','YEAR_END',[])).toBe('');
  expect(balanceComparisonDate('2026-02-30','LAST_YEAR',[])).toBe('');
});

it('opens Standard with independent sides, earnings and zero accounts unchecked',async()=>{
  render(<BalanceSheetWorkspace {...balanceProps}/>);await screen.findByText('Operating bank account');
  expect(screen.getByText(/Example Company.*Assets, liabilities and equity/)).toBeVisible();
  expect(screen.getAllByText('Total assets')).toHaveLength(1);
  expect(screen.getByRole('radio',{name:'Standard'})).toHaveAttribute('aria-checked','true');
  expect(within(screen.getByRole('region',{name:'Balance Sheet assets statement'})).getByText('Operating bank account')).toBeVisible();
  expect(within(screen.getByRole('region',{name:'Balance Sheet liabilities and equity statement'})).getByText('Current year earnings')).toBeVisible();
  expect(submissions()[0][3]).toMatchObject({code:'BALANCE_SHEET',parameters:{date_to:'2027-03-31',show_zero:false}});
  expect((submissions()[0][3] as {parameters:object}).parameters).not.toHaveProperty('date_from');
  fireEvent.click(screen.getByRole('button',{name:'Filters'}));
  expect(screen.getByLabelText('As-of date')).toHaveValue('2027-03-31');
  expect(screen.queryByLabelText('From date')).not.toBeInTheDocument();
  expect(screen.getByLabelText('Include zero accounts')).not.toBeChecked();
  fireEvent.click(screen.getByRole('button',{name:'Collapse Bank accounts'}));
  expect(screen.queryByText('Operating bank account')).not.toBeInTheDocument();
});

it('compares two dates and exports and drills into the completed comparison',async()=>{
  render(<BalanceSheetWorkspace {...balanceProps}/>);await screen.findByText('Operating bank account');
  fireEvent.click(screen.getByRole('radio',{name:'Comparative'}));
  await screen.findByRole('columnheader',{name:/^Previous/});
  expect(submissions()[1][3]).toMatchObject({view:'comparison',parameters:{date_to:'2027-03-31',comparative_to:'2026-03-31'}});
  expect(screen.getByText(/versus 31 Mar 2026/)).toBeVisible();
  fireEvent.click(screen.getByRole('button',{name:'View previous entries for Operating bank account'}));
  await waitFor(()=>expect(api.mock.calls.find(call=>call[2].endsWith('/drilldowns'))?.[3]).toEqual({token:'prior-token'}));
  fireEvent.click(screen.getByRole('button',{name:'Export PDF'}));
  await screen.findByRole('link',{name:'Download PDF'});
  expect(api.mock.calls.find(call=>call[2].endsWith('/exports'))?.[3]).toEqual({format:'PDF',view:'comparison'});
});

it('retains the completed Standard view when a replacement fails',async()=>{
  render(<BalanceSheetWorkspace {...balanceProps}/>);await screen.findByText('Operating bank account');
  let reject!:(error:Error)=>void;
  api.mockImplementation((service,method,path,body)=>path.endsWith('/report-runs')&&method==='POST'?new Promise((_resolve,no)=>{reject=no;}):balanceMock(service,method,path,body));
  fireEvent.click(screen.getByRole('radio',{name:'Comparative'}));
  expect(screen.queryByRole('columnheader',{name:/^Previous/})).not.toBeInTheDocument();
  await act(async()=>reject(new Error('Source unavailable')));
  expect(await screen.findByRole('alert')).toHaveTextContent('Source unavailable');
  expect(screen.getByText(/Showing the last completed report \(Standard\)/)).toBeVisible();
});

it('rejects comparison dates outside source coverage without changing the chosen date',async()=>{
  api.mockImplementation(async(service,method,path,body)=>path.endsWith('/report-generations/'+uuid(9))?{id:uuid(9),status:'READY',manifest:{control:{coverage_start:'2026-04-01'}}}:balanceMock(service,method,path,body));
  render(<BalanceSheetWorkspace {...balanceProps}/>);await screen.findByText('Operating bank account');
  fireEvent.click(screen.getByRole('radio',{name:'Comparative'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('Choose a date within available history');
  expect(submissions()).toHaveLength(1);
  expect(screen.getByLabelText('As-of date')).toHaveValue('2027-03-31');
});

it('stops a queued report and restores enabled completed-result controls',async()=>{
  render(<BalanceSheetWorkspace {...balanceProps}/>);await screen.findByText('Operating bank account');
  api.mockImplementation(async(service,method,path,body)=>path.endsWith('/report-runs')&&method==='POST'?{...balanceJob,status:'QUEUED',id:uuid(32)}:path.endsWith('/cancel')?{...balanceJob,status:'CANCELLED'}:balanceMock(service,method,path,body));
  fireEvent.click(screen.getByRole('radio',{name:'Comparative'}));
  fireEvent.click(await screen.findByRole('button',{name:'Stop Balance Sheet report'}));
  await screen.findByText('Report stopped');
  expect(screen.getByRole('button',{name:'Operating bank account'})).toBeEnabled();
});

it('hides exports without permission and denies a report without read permission',async()=>{
  const mounted=render(<BalanceSheetWorkspace {...balanceProps} permissions={['report.read']}/>);
  await screen.findByText('Operating bank account');
  expect(screen.queryByRole('button',{name:'Export PDF'})).not.toBeInTheDocument();
  mounted.rerender(<BalanceSheetWorkspace {...balanceProps} permissions={[]}/>);
  await screen.findByRole('alert');
  expect(screen.queryByText('Operating bank account')).not.toBeInTheDocument();
});

it('automatically refreshes a failed verification once without shifting the as-of date',async()=>{
  let runs=0;
  api.mockImplementation(async(service,method,path,body)=>{
    if(path.endsWith('/report-runs')&&method==='POST'){
      runs++;
      return {...balanceJob,parameters:(body as {parameters:object}).parameters,...(runs===1?{status:'BLOCKED',failure_code:'REPORT_VERIFICATION_FAILED'}:{})};
    }
    if(path.endsWith('/report-generations')&&method==='POST')return {id:uuid(10),status:'READY',manifest:{control:{coverage_start:'2020-01-01'}}};
    return balanceMock(service,method,path,body);
  });
  render(<BalanceSheetWorkspace {...balanceProps}/>);await screen.findByText('Operating bank account');
  expect(runs).toBe(2);
  expect(submissions()[1][3]).toMatchObject({generation_id:uuid(10),parameters:{date_to:'2027-03-31'}});
  expect((submissions()[1][3] as {parameters:object}).parameters).not.toHaveProperty('date_from');
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});

it('loads Balance Sheet history with its server-side report filter',async()=>{
  render(<BalanceSheetWorkspace {...balanceProps}/>);await screen.findByText('Operating bank account');
  fireEvent.click(screen.getByText('Report history and source details'));
  fireEvent.click(screen.getByRole('button',{name:'Load history'}));
  await waitFor(()=>expect(api.mock.calls.some(call=>call[2].includes('/report-runs?limit=20&code=BALANCE_SHEET'))).toBe(true));
});

it('opens comparison filters when the preset is unavailable and explains the resolved date',async()=>{
  api.mockImplementation(async(service,method,path,body)=>path.endsWith('/report-generations/'+uuid(9))?{id:uuid(9),status:'READY',manifest:{control:{coverage_start:'2026-04-01'}}}:balanceMock(service,method,path,body));
  render(<BalanceSheetWorkspace {...balanceProps}/>);await screen.findByText('Operating bank account');
  fireEvent.click(screen.getByRole('radio',{name:'Comparative'}));
  await screen.findByRole('alert');
  expect(screen.getByRole('region',{name:'Balance Sheet filters'})).toBeVisible();
  expect(screen.getByLabelText('Compare with')).toHaveFocus();
  expect(screen.getByText('Comparison as at 31 Mar 2026')).toBeVisible();
  expect(screen.getByLabelText('As-of date')).toHaveAttribute('min','2026-04-01');
});

it('labels comparison columns with completed dates while new filters are being edited',async()=>{
  render(<BalanceSheetWorkspace {...balanceProps}/>);await screen.findByText('Operating bank account');
  fireEvent.click(screen.getByRole('radio',{name:'Comparative'}));
  await screen.findByRole('columnheader',{name:'Current As at 31 Mar 2027'});
  expect(screen.getByRole('columnheader',{name:'Previous As at 31 Mar 2026'})).toBeVisible();
  fireEvent.click(screen.getByRole('button',{name:'Filters'}));
  fireEvent.change(screen.getByLabelText('As-of date'),{target:{value:'2026-12-31'}});
  expect(screen.getByRole('columnheader',{name:'Current As at 31 Mar 2027'})).toBeVisible();
});

it('shows account detail on the next page even when its group was collapsed on the preceding page',async()=>{
  api.mockImplementation(async(service,method,path,body)=>path.includes('/rows?')?{items:path.includes('cursor=next')?[{...balanceRows[2],ordinal:201,data:{...balanceRows[2].data,label:'Second bank account'}}]:balanceRows,page:{next_cursor:path.includes('cursor=next')?null:'next'}}:balanceMock(service,method,path,body));
  render(<BalanceSheetWorkspace {...balanceProps}/>);await screen.findByText('Operating bank account');
  fireEvent.click(screen.getByRole('button',{name:'Collapse Bank accounts'}));
  fireEvent.click(screen.getByRole('button',{name:'Next'}));
  await screen.findByText('Page 2');
  expect(screen.getByText('Second bank account')).toBeVisible();
  expect(screen.getByText(/Totals cover the complete report/)).toBeVisible();
});
