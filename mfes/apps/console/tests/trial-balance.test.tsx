import {act,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {TrialBalanceWorkspace} from '../app/components/TrialBalanceWorkspace';
import {productFieldRequest,ProductFieldError} from '../app/lib/product-fields';
import {initialTrialPresentation,restoreTrial,trialExpanded} from '../app/lib/trial-balance';
import type {TrialNode} from '../app/lib/trial-balance';
import {goTo} from '../app/lib/navigate';
import userEvent from '@testing-library/user-event';
import type {ReactElement} from 'react';

vi.mock('../app/lib/product-fields',async importOriginal=>({...await importOriginal<typeof import('../app/lib/product-fields')>(),productFieldRequest:vi.fn()}));
vi.mock('../app/lib/navigate',()=>({goTo:vi.fn()}));
vi.mock('../app/components/ReportWorkspace',()=>({ReportWorkspace:({initialRun}:{initialRun:string})=><p>Legacy result {initialRun}</p>}));
const api=vi.mocked(productFieldRequest);
import {trialCompany,trialRun,trialJob,trialDefinition,trialMock,trialProps as props,uuid,head,group,row} from './trial-balance-fixture';
import {hierarchyKeys,hierarchyMock} from './trial-balance-hierarchy-fixture';
beforeEach(()=>{sessionStorage.clear();api.mockReset();api.mockImplementation(trialMock as typeof productFieldRequest);vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(()=>{});});
afterEach(()=>{vi.restoreAllMocks();vi.unstubAllGlobals();});

/** Existing report workflows now begin by opening the optional filter panel. */
function renderWithFilters(element:ReactElement){
  const mounted=render(element);
  const filters=screen.queryByRole('button',{name:'Filter'});
  if(filters)fireEvent.click(filters);
  return mounted;
}
function chooseCsvExport(){
  const primary=screen.queryByRole('button',{name:'Export CSV'});
  if(primary)fireEvent.click(primary);
  else{fireEvent.click(screen.getByRole('button',{name:'Export format'}));fireEvent.click(screen.getByRole('menuitem',{name:'CSV spreadsheet'}));}
}

it('starts with a compact toolbar and keeps filters hidden until the Filter button is clicked',async()=>{
  render(<TrialBalanceWorkspace {...props} permissions={[...props.permissions,'report.definition.manage']}/>);
  await screen.findByText('Current assets');
  const filters=screen.getByRole('button',{name:'Filter'});
  expect(filters).toHaveTextContent('Filter');
  expect(filters).not.toHaveAttribute('aria-label');
  expect(filters.querySelector('svg')).toHaveAttribute('aria-hidden','true');
  expect(filters).toHaveAttribute('aria-expanded','false');
  expect(screen.queryByRole('region',{name:'Trial Balance filters'})).not.toBeInTheDocument();
  expect(screen.queryByLabelText('From date')).not.toBeInTheDocument();
  const toolbar=screen.getByRole('group',{name:'Trial Balance actions'});
  expect([...toolbar.querySelectorAll('button,select')].map(control=>control.getAttribute('aria-label')??control.textContent)).toEqual([
    'Refresh accounting data','Filter','Current hierarchyAll ledgers','Export PDF','Export format',
  ]);
  const posts=api.mock.calls.filter(call=>call[1]==='POST').length;
  fireEvent.click(filters);
  expect(filters).toHaveAttribute('aria-expanded','true');
  expect(screen.getByRole('region',{name:'Trial Balance filters'})).toHaveAttribute('id',filters.getAttribute('aria-controls'));
  fireEvent.change(screen.getByLabelText('To date'),{target:{value:'2026-05-31'}});
  fireEvent.click(filters);
  expect(screen.queryByLabelText('To date')).not.toBeInTheDocument();
  fireEvent.click(filters);
  expect(screen.getByLabelText('To date')).toHaveValue('2026-05-31');
  expect(screen.getByRole('radio',{name:'Closing balances'})).toHaveAttribute('aria-checked','true');
  expect(api.mock.calls.filter(call=>call[1]==='POST')).toHaveLength(posts);
});

it('closes filters with Escape, restores focus and preserves the edited period',async()=>{
  const user=userEvent.setup();
  render(<TrialBalanceWorkspace {...props}/>);await screen.findByText('Current assets');
  await user.click(screen.getByRole('button',{name:'Filter'}));
  fireEvent.change(screen.getByLabelText('To date'),{target:{value:'2026-05-31'}});
  screen.getByLabelText('To date').focus();await user.keyboard('{Escape}');
  expect(screen.queryByRole('region',{name:'Trial Balance filters'})).not.toBeInTheDocument();
  expect(screen.getByRole('button',{name:'Filter'})).toHaveFocus();
  await user.click(screen.getByRole('button',{name:'Filter'}));
  expect(screen.getByLabelText('To date')).toHaveValue('2026-05-31');
});

it('exports PDF by default and switches export formats through the keyboard accessible split menu',async()=>{
  const user=userEvent.setup();
  render(<TrialBalanceWorkspace {...props}/>);await screen.findByText('Current assets');
  await user.click(screen.getByRole('button',{name:'Export PDF'}));
  await screen.findByRole('link',{name:'Download PDF'});
  expect(api.mock.calls.find(call=>call[2].endsWith('/exports'))![3]).toMatchObject({format:'PDF',trial_balance:{hierarchy:'CURRENT'}});
  const trigger=screen.getByRole('button',{name:'Export format'});trigger.focus();
  await user.keyboard('{ArrowDown}');
  expect(screen.getByRole('menu',{name:'Export format'})).toBeInTheDocument();
  await user.keyboard('{Escape}');expect(trigger).toHaveFocus();
  await user.click(trigger);await user.click(screen.getByRole('menuitem',{name:'Excel workbook'}));
  await screen.findByRole('button',{name:'Export Excel'});
  await waitFor(()=>expect(api.mock.calls.filter(call=>call[2].endsWith('/exports'))).toHaveLength(2));
  expect(api.mock.calls.filter(call=>call[2].endsWith('/exports'))[1][3]).toMatchObject({format:'XLSX'});
  expect(screen.queryByRole('menu')).not.toBeInTheDocument();
});

it('starts the PDF download when ready and keeps its fallback beside the export control',async()=>{
  const clicked:string[]=[];
  const download=vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(function(this:HTMLAnchorElement){clicked.push(this.href);});
  try{
    render(<TrialBalanceWorkspace {...props}/>);await screen.findByText('Current assets');
    fireEvent.click(screen.getByRole('button',{name:'Export PDF'}));
    const link=await screen.findByRole('link',{name:'Download PDF'});
    expect(link.closest('header')).toBeTruthy();
    expect(clicked).toEqual([expect.stringContaining('/api/report-download?')]);
    expect(clicked[0]).toContain('export='+uuid(10));
  }finally{download.mockRestore();}
});

it('disables both export actions as soon as submission starts, before a job is returned',async()=>{
  let complete!:(job:unknown)=>void;
  api.mockImplementation(async(...args)=>args[2].endsWith('/exports')?new Promise(resolve=>{complete=resolve;}):trialMock(...args));
  render(<TrialBalanceWorkspace {...props}/>);await screen.findByText('Current assets');
  fireEvent.click(screen.getByRole('button',{name:'Export PDF'}));
  expect(screen.getByRole('button',{name:'Exporting…'})).toBeDisabled();
  expect(screen.getByRole('button',{name:'Export format'})).toBeDisabled();
  expect(screen.getByLabelText('Export hierarchy')).toBeDisabled();
  await act(async()=>complete({...trialJob,id:uuid(91),kind:'EXPORT',parameters:{format:'PDF'}}));
  await screen.findByRole('link',{name:'Download PDF'});
  expect(screen.getByRole('button',{name:'Export PDF'})).toBeEnabled();
  expect(api.mock.calls.filter(call=>call[2].endsWith('/exports'))).toHaveLength(1);
});

it('keeps available alternatives usable when the selected export format exceeds its limit',async()=>{
  api.mockImplementation(async(...args)=>args[2].endsWith('/report-definitions/TRIAL_BALANCE')?{...trialDefinition,export_limits:trialDefinition.export_limits.map(limit=>({...limit,max_rows:['PDF','HTML'].includes(limit.format)?1:limit.max_rows}))}:trialMock(...args));
  render(<TrialBalanceWorkspace {...props}/>);await screen.findByText('Current assets');
  expect(screen.getByRole('button',{name:'Export PDF'})).toBeDisabled();
  expect(screen.getByRole('button',{name:'Export PDF'})).toHaveAttribute('title',expect.stringContaining('up to 1 rows'));
  const count=api.mock.calls.filter(call=>call[1]==='POST').length;
  fireEvent.click(screen.getByRole('button',{name:'Export format'}));
  const html=screen.getByRole('menuitem',{name:/HTML document/});
  expect(html).toHaveAttribute('aria-disabled','true');fireEvent.click(html);
  expect(api.mock.calls.filter(call=>call[1]==='POST')).toHaveLength(count);
  fireEvent.click(screen.getByRole('menuitem',{name:'CSV spreadsheet'}));
  await screen.findByRole('link',{name:'Download CSV'});
  expect(screen.getByRole('button',{name:'Export CSV'})).toBeEnabled();
});

it('exports HTML with the selected hierarchy and remembers the format for the primary action',async()=>{
  render(<TrialBalanceWorkspace {...props}/>);await screen.findByText('Current assets');
  fireEvent.change(screen.getByLabelText('Export hierarchy'),{target:{value:'ALL'}});
  fireEvent.click(screen.getByRole('button',{name:'Export format'}));fireEvent.click(screen.getByRole('menuitem',{name:'HTML document'}));
  await screen.findByRole('link',{name:'Download HTML'});
  expect(api.mock.calls.find(call=>call[2].endsWith('/exports'))![3]).toMatchObject({format:'HTML',view:'default',trial_balance:{hierarchy:'ALL'}});
  fireEvent.click(screen.getByRole('button',{name:'Export HTML'}));
  await waitFor(()=>expect(api.mock.calls.filter(call=>call[2].endsWith('/exports'))).toHaveLength(2));
  fireEvent.click(screen.getByRole('button',{name:'Export format'}));
  fireEvent.click(screen.getByRole('menuitem',{name:'PDF report'}));
  await waitFor(()=>expect(api.mock.calls.filter(call=>call[2].endsWith('/exports'))).toHaveLength(3));
  expect(screen.getByRole('button',{name:'Export PDF'})).toBeEnabled();
});

it('defaults to closing balances and switches without a new calculation or losing expansion',async()=>{
  renderWithFilters(<TrialBalanceWorkspace {...props}/>);
  await screen.findByText('Current assets');
  fireEvent.click(screen.getByRole('button',{name:'Expand Current assets'}));await screen.findByText('Cash in hand');
  const posts=api.mock.calls.filter(call=>call[1]==='POST').length;
  expect(screen.getByRole('radio',{name:'Closing balances'})).toHaveAttribute('aria-checked','true');
  const scroll=screen.getByRole('region',{name:'Trial Balance accounts'});scroll.scrollTop=75;
  fireEvent.click(screen.getByRole('radio',{name:'Opening and movement'}));
  expect(screen.getByRole('columnheader',{name:'Opening balance'})).toHaveAttribute('colspan','2');
  expect(screen.getByRole('button',{name:'Collapse Current assets'})).toHaveAttribute('aria-expanded','true');
  expect(scroll.scrollTop).toBe(75);expect(api.mock.calls.filter(call=>call[1]==='POST')).toHaveLength(posts);
  expect(within(screen.getByRole('row',{name:/Grand total/})).getAllByText('260.00')).toHaveLength(2);
});

it('applies hierarchy presets without recalculating totals and zero filtering changes branch reads only',async()=>{
  renderWithFilters(<TrialBalanceWorkspace {...props}/>);await screen.findByText('Current assets');
  fireEvent.change(screen.getByLabelText('Expand hierarchy'),{target:{value:'HEADS'}});
  expect(screen.queryByText('Current assets')).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Expand hierarchy'),{target:{value:'LEDGERS'}});await screen.findByText('Cash in hand');
  fireEvent.click(screen.getByLabelText('Show zero rows'));
  await waitFor(()=>expect(api.mock.calls.some(call=>call[2].includes('show_zero=true'))).toBe(true));
  expect(api.mock.calls.filter(call=>call[1]==='POST'&&call[2].endsWith('/report-runs'))).toHaveLength(1);
});

it('excludes zero rows by default and includes them when requested',async()=>{
  api.mockImplementation(hierarchyMock as typeof productFieldRequest);
  renderWithFilters(<TrialBalanceWorkspace {...props}/>);
  await screen.findByText('Current assets');
  expect(screen.getByLabelText('Show zero rows')).not.toBeChecked();
  expect(api.mock.calls.find(call=>call[2].includes('/hierarchy?'))![2]).toContain('show_zero=false');
  fireEvent.change(screen.getByLabelText('Expand hierarchy'),{target:{value:'LEDGERS'}});
  await screen.findByText('Cash account');
  expect(screen.queryByText('Quiet account')).not.toBeInTheDocument();
  fireEvent.click(screen.getByLabelText('Show zero rows'));
  await screen.findByText('Quiet account');
});

it('exports the selected layout and complete hierarchy choices independent of the visible branch page',async()=>{
  renderWithFilters(<TrialBalanceWorkspace {...props}/>);await screen.findByText('Current assets');
  fireEvent.click(screen.getByRole('radio',{name:'Opening and movement'}));
  fireEvent.change(screen.getByLabelText('Export hierarchy'),{target:{value:'ALL'}});
  chooseCsvExport();await screen.findByRole('link',{name:'Download CSV'});
  const payload=api.mock.calls.find(call=>call[2].endsWith('/exports'))![3];
  expect(payload).toMatchObject({format:'CSV',view:'detailed',trial_balance:{hierarchy:'ALL',level:'GROUPS',show_zero:false}});
});

it.each([401,403])('clears financial rows when hierarchy access returns %s',async status=>{
  renderWithFilters(<TrialBalanceWorkspace {...props}/>);await screen.findByText('Current assets');
  api.mockImplementation(async()=>{throw new ProductFieldError('Access changed',{},status);});
  fireEvent.click(screen.getByLabelText('Show zero rows'));
  await screen.findByText(/Your report access is unavailable/);expect(screen.queryByText('Grand total')).not.toBeInTheDocument();
});

it('retains the completed report when preparing a new period fails',async()=>{
  renderWithFilters(<TrialBalanceWorkspace {...props}/>);await screen.findByText('Current assets');
  api.mockImplementation(async()=>{throw new ProductFieldError('Reporting service unavailable',{},500);});
  fireEvent.change(screen.getByLabelText('To date'),{target:{value:'2026-05-31'}});fireEvent.click(screen.getByRole('button',{name:'Apply period'}));
  await screen.findByText('Reporting service unavailable');expect(screen.getByText('Current assets')).toBeInTheDocument();expect(screen.getByText('Grand total')).toBeInTheDocument();
});

it('retains the previous completed rows when the replacement hierarchy read fails',async()=>{
  renderWithFilters(<TrialBalanceWorkspace {...props}/>);await screen.findByText('Current assets');
  api.mockImplementation(async(...args)=>{
    if(args[2].includes('/hierarchy?'))throw new ProductFieldError('New hierarchy unavailable',{},500);
    return {...trialJob,id:uuid(30),parameters:{date_from:'2026-04-01',date_to:'2026-05-31'}};
  });
  fireEvent.change(screen.getByLabelText('To date'),{target:{value:'2026-05-31'}});fireEvent.click(screen.getByRole('button',{name:'Apply period'}));
  await screen.findByText('New hierarchy unavailable');expect(screen.getByText('Current assets')).toBeInTheDocument();expect(screen.getByText('Grand total')).toBeInTheDocument();
});

it('reuses the same idempotency key for a failed submission retry',async()=>{
  let attempts=0;api.mockImplementation(async(...args)=>{
    if(args[1]==='POST'&&args[2].endsWith('/report-runs')&&++attempts===1)throw new Error('Connection lost');
    return trialMock(...args);
  });
  renderWithFilters(<TrialBalanceWorkspace {...props}/>);await screen.findByText('Connection lost');
  fireEvent.click(screen.getByRole('button',{name:'Retry'}));await screen.findByText('Current assets');
  const commands=api.mock.calls.filter(call=>call[1]==='POST');expect(commands).toHaveLength(2);expect(commands[0][4]).toBe(commands[1][4]);
});

it('gates export and source preparation and distinguishes an absent source from an empty trial balance',async()=>{
  api.mockImplementation(async(...args)=>args[2].includes('/report-generations?')?{items:[],page:{next_cursor:null}}:trialMock(...args));
  renderWithFilters(<TrialBalanceWorkspace {...props} permissions={['report.read']}/>);
  await screen.findByText(/No prepared accounting snapshot/);
  expect(screen.queryByRole('button',{name:'Export PDF'})).not.toBeInTheDocument();expect(screen.queryByRole('button',{name:'Refresh accounting data'})).not.toBeInTheDocument();
  expect(api.mock.calls.some(call=>call[1]==='POST')).toBe(false);
});

it('restores layout and hierarchy identifiers from a signed ledger return without storing amounts',async()=>{
  sessionStorage.setItem('janso:trial-balance:'+props.company+':'+props.actor,JSON.stringify({run:trialRun,mode:'detailed',settings:{...initialTrialPresentation,expanded:[group]},scroll:25,cursors:{}}));
  renderWithFilters(<TrialBalanceWorkspace {...props} initialRun={trialRun}/>);await screen.findByText('Cash in hand');
  expect(screen.getByRole('radio',{name:'Opening and movement'})).toHaveAttribute('aria-checked','true');
  expect(api.mock.calls.some(call=>call[1]==='POST')).toBe(false);
  fireEvent.scroll(screen.getByRole('region',{name:'Trial Balance accounts'}));
  const saved=sessionStorage.getItem('janso:trial-balance:'+props.company+':'+props.actor)!;
  expect(saved).not.toContain('closing_debit');expect(saved).not.toContain('260.0000');
});

it('validates restored identifiers and distinguishes all groups from ledgers',()=>{
  const groupNode=row('GROUP',group,head,'Group',1,1).data as TrialNode;
  expect(trialExpanded(groupNode,{...initialTrialPresentation,level:'ALL_GROUPS'})).toBe(false);
  expect(trialExpanded(groupNode,{...initialTrialPresentation,level:'LEDGERS'})).toBe(true);
  expect(restoreTrial(JSON.stringify({run:trialRun,mode:'detailed',settings:{...initialTrialPresentation,expanded:['../foreign']},scroll:0}),trialRun)).toBeNull();
});

it('loads at most twenty branches when the ledger preset opens many visible groups',async()=>{
  api.mockImplementation(async(...args)=>{
    if(args[2].includes('/hierarchy?')){
      const parent=new URLSearchParams(args[2].split('?')[1]).get('parent');
      if(parent===head){
        const page=await trialMock(...args) as {items:unknown[]};
        return {...page,items:Array.from({length:50},(_,index)=>row('GROUP','group:'+uuid(index+100),head,'Group '+index,1,1))};
      }
      if(parent?.startsWith('group:')){
        const page=await trialMock(...args) as {items:unknown[]};
        return {...page,items:Array.from({length:50},(_,index)=>row('ACCOUNT','account:'+uuid(Number(parent.slice(-3))*100+index),parent,'Account '+parent.slice(-3)+'-'+index,2,0))};
      }
    }
    return trialMock(...args);
  });
  renderWithFilters(<TrialBalanceWorkspace {...props}/>);await screen.findByText('Group 49');
  fireEvent.change(screen.getByLabelText('Expand hierarchy'),{target:{value:'LEDGERS'}});
  await screen.findByText('Account 100-0');
  await waitFor(()=>expect(api.mock.calls.filter(call=>call[2].includes('/hierarchy?'))).toHaveLength(20));
  expect(screen.getAllByText(/Collapse a branch/).length).toBeGreaterThan(0);
});

it('keeps previous totals when zero-row presentation cannot be refreshed',async()=>{
  renderWithFilters(<TrialBalanceWorkspace {...props}/>);await screen.findByText('Current assets');
  api.mockImplementation(async()=>{throw new ProductFieldError('Hierarchy temporarily unavailable',{},500);});
  fireEvent.click(screen.getByLabelText('Show zero rows'));await screen.findByText('Hierarchy temporarily unavailable');
  expect(screen.getByText('Grand total')).toBeInTheDocument();expect(screen.getByText('Current assets')).toBeInTheDocument();
});

it('advances beyond the saved cursor window and can restart from the first accounts',async()=>{
  const saved={run:trialRun,mode:'default',settings:initialTrialPresentation,scroll:0,cursors:{root:{values:Array.from({length:100},(_,index)=>'cursor-'+index),position:99}}};
  sessionStorage.setItem('janso:trial-balance:'+props.company+':'+props.actor,JSON.stringify(saved));
  api.mockImplementation(async(...args)=>{
    if(args[2].includes('/hierarchy?')){const page=await trialMock(...args) as {items:unknown[]};return {...page,items:[row('HEAD',head,'root','Assets',0,0)],page:{has_more:true,next_cursor:'cursor-100'}};}
    return trialMock(...args);
  });
  renderWithFilters(<TrialBalanceWorkspace {...props} initialRun={trialRun}/>);await screen.findByText('Page 100');
  fireEvent.click(screen.getByRole('button',{name:'Next accounts'}));await screen.findByText('Page 101');
  expect(screen.getByRole('button',{name:'Next accounts'})).toBeEnabled();
  fireEvent.click(screen.getByRole('button',{name:'First accounts'}));await screen.findByText('Page 1');
});

it('follows a financial-year change for draft dates while retaining the completed statement',async()=>{
  const mounted=renderWithFilters(<TrialBalanceWorkspace {...props}/>);await screen.findByText('Current assets');
  mounted.rerender(<TrialBalanceWorkspace {...props} year={{...props.year,id:uuid(60),startDate:'2025-04-01',endDate:'2026-03-31',current:false}}/>);
  expect(screen.getByLabelText('From date')).toHaveValue('2025-04-01');expect(screen.getByLabelText('To date')).toHaveValue('2026-03-31');
  expect(screen.getByText('Current assets')).toBeInTheDocument();
  expect(api.mock.calls.filter(call=>call[1]==='POST')).toHaveLength(1);
});

it('prepares a missing source automatically, waits for verification and uses that snapshot for the report',async()=>{
  const sourceId=uuid(70);
  api.mockImplementation(async(...args)=>{
    if(args[2].includes('/report-generations?'))return {items:[],page:{next_cursor:null}};
    if(args[1]==='POST'&&args[2].endsWith('/report-generations'))return {id:sourceId,status:'BUILDING'};
    if(args[2].endsWith('/report-generations/'+sourceId))return {id:sourceId,status:'READY'};
    return trialMock(...args);
  });
  renderWithFilters(<TrialBalanceWorkspace {...props} permissions={[...props.permissions,'report.definition.manage']}/>);
  await screen.findByText('Current assets',{}, {timeout:4000});
  expect(api.mock.calls.find(call=>call[1]==='POST'&&call[2].endsWith('/report-generations'))![3]).toEqual({strategy:'FRESH'});
  expect(api.mock.calls.find(call=>call[1]==='POST'&&call[2].endsWith('/report-runs'))![3]).toMatchObject({generation_id:sourceId});
});

it('refreshes an unverified source once before showing the report',async()=>{
  const sourceId=uuid(70);
  let runs=0;
  api.mockImplementation(async(...args)=>{
    if(args[1]==='POST'&&args[2].endsWith('/report-runs'))return {...trialJob,status:++runs===1?'BLOCKED':'COMPLETE',failure_code:runs===1?'REPORT_VERIFICATION_FAILED':null,parameters:(args[3] as {parameters:typeof trialJob.parameters}).parameters};
    if(args[1]==='POST'&&args[2].endsWith('/report-generations'))return {id:sourceId,status:'READY',manifest:{control:{coverage_start:'2026-10-31'}}};
    return trialMock(...args);
  });
  renderWithFilters(<TrialBalanceWorkspace {...props} permissions={[...props.permissions,'report.definition.manage']}/>);
  await screen.findByText('Current assets');
  expect(runs).toBe(2);
  expect(api.mock.calls.filter(call=>call[1]==='POST'&&call[2].endsWith('/report-generations'))).toHaveLength(1);
  expect(api.mock.calls.filter(call=>call[1]==='POST'&&call[2].endsWith('/report-runs'))[1][3]).toMatchObject({generation_id:sourceId,parameters:{date_from:'2026-04-01'}});
});

it('keeps the requested period when repairing a blocked report opened from history',async()=>{
  const blockedId=uuid(76),sourceId=uuid(77);
  api.mockImplementation(async(...args)=>{
    if(args[2].endsWith('/report-runs/'+blockedId))return {...trialJob,id:blockedId,status:'BLOCKED',failure_code:'REPORT_VERIFICATION_FAILED',parameters:{date_from:'2026-10-01',date_to:'2026-11-01'}};
    if(args[1]==='POST'&&args[2].endsWith('/report-generations'))return {id:sourceId,status:'READY',manifest:{control:{coverage_start:'2026-10-31'}}};
    if(args[1]==='POST'&&args[2].endsWith('/report-runs'))return {...trialJob,parameters:(args[3] as {parameters:typeof trialJob.parameters}).parameters};
    return trialMock(...args);
  });
  render(<TrialBalanceWorkspace {...props} initialRun={blockedId} permissions={[...props.permissions,'report.definition.manage']}/>);
  await screen.findByText('Current assets');
  expect(api.mock.calls.find(call=>call[1]==='POST'&&call[2].endsWith('/report-runs'))![3]).toMatchObject({parameters:{date_from:'2026-10-01',date_to:'2026-11-01'}});
});

it('starts at retained accounting coverage and rejects earlier trial balance dates',async()=>{
  const sourceId=uuid(9);
  api.mockImplementation(async(...args)=>{
    if(args[2].endsWith('/report-generations/'+sourceId))return {id:sourceId,status:'READY',manifest:{control:{coverage_start:'2026-10-31'}}};
    if(args[1]==='POST'&&args[2].endsWith('/report-runs'))return {...trialJob,parameters:(args[3] as {parameters:typeof trialJob.parameters}).parameters};
    return trialMock(...args);
  });
  renderWithFilters(<TrialBalanceWorkspace {...props}/>);
  await screen.findByText('Current assets');
  expect(screen.getByLabelText('From date')).toHaveValue('2026-10-31');
  expect(screen.getByText(/Accounting records begin/)).toHaveTextContent('31 Oct 2026');
  const posts=api.mock.calls.filter(call=>call[1]==='POST'&&call[2].endsWith('/report-runs'));
  expect(posts).toHaveLength(1);
  expect(posts[0][3]).toMatchObject({parameters:{date_from:'2026-10-31'}});
  fireEvent.change(screen.getByLabelText('From date'),{target:{value:'2026-04-01'}});
  fireEvent.click(screen.getByRole('button',{name:'Apply period'}));
  expect(screen.getByRole('alert')).toHaveTextContent(/Choose a From date on or after/);
  expect(api.mock.calls.filter(call=>call[1]==='POST'&&call[2].endsWith('/report-runs'))).toHaveLength(1);
});

it('cancels a queued calculation through the existing job without exposing partial rows',async()=>{
  api.mockImplementation(async(...args)=>{
    if(args[2].endsWith('/report-runs'))return {...trialJob,status:'QUEUED'};
    if(args[2].endsWith('/cancel'))return {...trialJob,status:'CANCELLED'};
    return trialMock(...args);
  });
  renderWithFilters(<TrialBalanceWorkspace {...props}/>);
  const progress=await screen.findByRole('region',{name:'Trial Balance progress'});
  expect(progress.previousElementSibling?.tagName).toBe('HEADER');
  expect(within(progress).getByText('Report queued')).toBeInTheDocument();
  expect(within(progress).getByText(/Waiting for a report worker/)).toBeInTheDocument();
  expect(within(progress).getByRole('progressbar',{name:'Trial Balance preparation'})).not.toHaveAttribute('aria-valuenow');
  fireEvent.click(within(progress).getByRole('button',{name:'Stop Trial Balance report'}));
  await waitFor(()=>expect(api.mock.calls.some(call=>call[2].endsWith('/cancel'))).toBe(true));
  expect(await within(progress).findByText('Report stopped')).toBeInTheDocument();
  expect(within(progress).queryByRole('progressbar')).not.toBeInTheDocument();
  expect(screen.queryByText('Grand total')).not.toBeInTheDocument();
});

it('shows the calculating stage and keeps Stop disabled while the stop request is pending',async()=>{
  let finishStop!:(value:unknown)=>void;
  api.mockImplementation(async(...args)=>{
    if(args[1]==='POST'&&args[2].endsWith('/report-runs'))return {...trialJob,status:'RUNNING'};
    if(args[2].endsWith('/cancel'))return new Promise(resolve=>{finishStop=resolve;});
    return trialMock(...args);
  });
  render(<TrialBalanceWorkspace {...props}/>);
  const progress=await screen.findByRole('region',{name:'Trial Balance progress'});
  expect(within(progress).getByText('Calculating report')).toBeInTheDocument();
  expect(within(progress).getByText('Calculate')).toHaveAttribute('data-state','current');
  fireEvent.click(within(progress).getByRole('button',{name:'Stop Trial Balance report'}));
  expect(within(progress).getByText('Stopping report')).toBeInTheDocument();
  expect(within(progress).getByRole('button',{name:'Stop Trial Balance report'})).toBeDisabled();
  await act(async()=>finishStop({...trialJob,status:'CANCELLED'}));
  expect(within(progress).getByText('Report stopped')).toBeInTheDocument();
});

it('retries a failed calculation with the retained job identity',async()=>{
  let parameters:unknown;
  api.mockImplementation(async(...args)=>{
    if(args[1]==='POST'&&args[2].endsWith('/report-runs')){parameters=(args[3] as {parameters:unknown}).parameters;return {...trialJob,parameters,status:'FAILED'};}
    if(args[2].endsWith('/retry'))return {...trialJob,parameters,status:'COMPLETE'};
    return trialMock(...args);
  });
  renderWithFilters(<TrialBalanceWorkspace {...props}/>);await screen.findByText(/Trial Balance could not complete/);
  fireEvent.click(screen.getByRole('button',{name:'Apply period'}));await screen.findByText('Current assets');
  expect(api.mock.calls.filter(call=>call[1]==='POST'&&call[2].endsWith('/report-runs'))).toHaveLength(1);
  expect(api.mock.calls.some(call=>call[2].endsWith('/report-runs/'+trialRun+'/retry'))).toBe(true);
});

it('opens completed history without creating a new report',async()=>{
  const historyId=uuid(80);
  api.mockImplementation(async(...args)=>{
    if(args[2].includes('/report-runs?'))return {items:[{id:historyId,code:'TRIAL_BALANCE',status:'COMPLETE',created_at:'2026-04-30T00:00:00Z'}],page:{next_cursor:null}};
    if(args[2].endsWith('/report-runs/'+historyId))return {...trialJob,id:historyId};
    return trialMock(...args);
  });
  renderWithFilters(<TrialBalanceWorkspace {...props}/>);await screen.findByText('Current assets');
  fireEvent.click(screen.getByText('Report history and source details'));fireEvent.click(screen.getByRole('button',{name:'Load history'}));
  fireEvent.click(await screen.findByRole('button',{name:/30 Apr 2026/}));
  await waitFor(()=>expect(api.mock.calls.some(call=>call[2].endsWith('/report-runs/'+historyId))).toBe(true));
  expect(api.mock.calls.filter(call=>call[1]==='POST')).toHaveLength(1);
});

it('invalidates an old export when the displayed layout changes',async()=>{
  api.mockImplementation(async(...args)=>{
    if(args[2].endsWith('/exports'))return {...trialJob,id:uuid(10),kind:'EXPORT',status:'QUEUED',parameters:args[3]};
    if(args[2].endsWith('/cancel'))return {...trialJob,id:uuid(10),kind:'EXPORT',status:'CANCELLED'};
    return trialMock(...args);
  });
  renderWithFilters(<TrialBalanceWorkspace {...props}/>);await screen.findByText('Current assets');
  chooseCsvExport();await screen.findByRole('button',{name:'Cancel export'});
  fireEvent.click(screen.getByRole('radio',{name:'Opening and movement'}));
  expect(api.mock.calls.find(call=>call[2].endsWith('/exports'))![3]).toMatchObject({view:'default'});
  expect(screen.queryByRole('button',{name:'Cancel export'})).not.toBeInTheDocument();
  expect(screen.queryByRole('link',{name:'Download CSV'})).not.toBeInTheDocument();
  expect(screen.getByRole('button',{name:'Export CSV'})).toBeEnabled();
});

it('retries a failed export without submitting a second export',async()=>{
  api.mockImplementation(async(...args)=>{
    if(args[2].endsWith('/exports'))return {...trialJob,id:uuid(10),kind:'EXPORT',status:'FAILED',parameters:args[3]};
    if(args[2].endsWith('/retry'))return {...trialJob,id:uuid(10),kind:'EXPORT',status:'COMPLETE'};
    return trialMock(...args);
  });
  renderWithFilters(<TrialBalanceWorkspace {...props}/>);await screen.findByText('Current assets');chooseCsvExport();
  fireEvent.click(await screen.findByRole('button',{name:'Retry export'}));await screen.findByRole('link',{name:'Download CSV'});
  expect(api.mock.calls.filter(call=>call[2].endsWith('/exports'))).toHaveLength(1);
});

it('uses the signed account mapping and a local ledger return URL',async()=>{
  api.mockImplementation(async(...args)=>args[2].endsWith('/drilldowns')?{...trialJob,id:uuid(90),code:'ACCOUNT_LEDGER',status:'QUEUED'}:trialMock(...args));
  renderWithFilters(<TrialBalanceWorkspace {...props}/>);await screen.findByText('Current assets');
  fireEvent.click(screen.getByRole('button',{name:'Expand Current assets'}));fireEvent.click(await screen.findByRole('button',{name:'Cash in hand'}));
  await waitFor(()=>expect(goTo).toHaveBeenCalledWith('/reports/workspace?'+new URLSearchParams({report:'ACCOUNT_LEDGER',run:uuid(90),trial_balance_run:trialRun})));
  expect(api.mock.calls.find(call=>call[2].endsWith('/drilldowns'))![3]).toEqual({token:'signed-account'});
});

it('loads expanded branches through the viewport observer',async()=>{
  let observes=0;
  vi.stubGlobal('IntersectionObserver',class {
    constructor(private callback:IntersectionObserverCallback){}
    observe(target:Element){observes++;this.callback([{target,isIntersecting:true} as IntersectionObserverEntry],this as unknown as IntersectionObserver);}
    disconnect(){}
  });
  renderWithFilters(<TrialBalanceWorkspace {...props}/>);await screen.findByText('Current assets');expect(observes).toBeGreaterThan(0);
});

it('opens older completed runs through their retained layout',async()=>{
  api.mockImplementation(async(...args)=>args[2].endsWith('/report-runs/'+trialRun)?{...trialJob,version:5}:trialMock(...args));
  renderWithFilters(<TrialBalanceWorkspace {...props} initialRun={trialRun}/>);await screen.findByText('Legacy result '+trialRun);
  expect(screen.getByRole('button',{name:'Prepare current Trial Balance'})).toBeInTheDocument();
  expect(api.mock.calls.some(call=>call[2].includes('/hierarchy?'))).toBe(false);
});

it('formats retained money using a non-English company display',async()=>{
  api.mockImplementation(async(...args)=>args[2].endsWith('/report-runs')?{...trialJob,display:{...trialJob.display,base_currency:'EUR',decimal_separator:',',thousands_separator:'.',digit_grouping:'western',locale:'de-DE'}}:trialMock(...args));
  renderWithFilters(<TrialBalanceWorkspace {...props}/>);await screen.findByText('Current assets');
  expect(within(screen.getByRole('row',{name:/Grand total/})).getAllByText('260,00')).toHaveLength(2);
});

it('polls the known queued report and publishes its completed hierarchy',async()=>{
  api.mockImplementation(async(...args)=>args[1]==='POST'&&args[2].endsWith('/report-runs')?{...trialJob,status:'QUEUED'}:trialMock(...args));
  renderWithFilters(<TrialBalanceWorkspace {...props}/>);await screen.findByRole('button',{name:'Stop Trial Balance report'});
  await screen.findByText('Current assets',{}, {timeout:4000});
  expect(api.mock.calls.filter(call=>call[1]==='POST')).toHaveLength(1);
});

it('does not submit an unsupported hierarchy to an older Reports deployment',async()=>{
  api.mockImplementation(async(...args)=>args[2].endsWith('/report-definitions/TRIAL_BALANCE')?{...trialDefinition,definition:{...trialDefinition.definition,version:5}}:trialMock(...args));
  renderWithFilters(<TrialBalanceWorkspace {...props}/>);await screen.findByText(/New report preparation is unavailable/);
  expect(api.mock.calls.some(call=>call[1]==='POST')).toBe(false);
});

it.each([null, {id:uuid(99),code:'Earlier',startDate:'2025-04-01',endDate:'2026-03-31',current:false,open:true}, {id:uuid(98),code:'Future',startDate:'2028-04-01',endDate:'2029-03-31',current:false,open:true}])('initializes a valid date range without an active current year',async year=>{
  renderWithFilters(<TrialBalanceWorkspace {...props} year={year}/>);await screen.findByText('Current assets');
  const body=api.mock.calls.find(call=>call[1]==='POST')![3] as {parameters:{date_from:string;date_to:string}};
  expect(body.parameters.date_from<=body.parameters.date_to).toBe(true);
});

it('ignores malformed and foreign saved settings and cursors',()=>{
  const saved={run:trialRun,mode:'default',settings:initialTrialPresentation,scroll:0,cursors:{root:{values:[null],position:0}}};
  for(const raw of [null,'{', 'x'.repeat(180_001),JSON.stringify({...saved,run:uuid(99)}),JSON.stringify({...saved,settings:{...initialTrialPresentation,collapsed:['bad']}}),JSON.stringify({...saved,scroll:-1})])expect(restoreTrial(raw,trialRun)).toBeNull();
  const restored=restoreTrial(JSON.stringify({...saved,cursors:{root:{values:[null],position:0},bad:{values:['x'],position:0},[head]:{values:['x'],position:3}}}),trialRun);
  expect(Object.keys(restored!.cursors)).toEqual(['root']);
  expect(trialExpanded({...row('GROUP',group,head,'Group',1,1).data,group_child_count:1} as TrialNode,{...initialTrialPresentation,level:'ALL_GROUPS'})).toBe(true);
  expect(trialExpanded(row('GROUP',group,head,'Group',1,0).data as TrialNode,{...initialTrialPresentation,level:'LEDGERS'})).toBe(false);
  expect(trialExpanded(row('GROUP',group,head,'Group',1,1).data as TrialNode,{...initialTrialPresentation,expanded:[group],collapsed:[group]})).toBe(false);
});

it('restores a completed report at the first page when its saved root cursor has expired',async()=>{
  sessionStorage.setItem('janso:trial-balance:'+trialCompany+':'+props.actor,JSON.stringify({run:trialRun,mode:'detailed',settings:initialTrialPresentation,scroll:0,cursors:{root:{values:[null,'expired'],position:1}}}));
  api.mockImplementation(async(...args)=>{
    if(args[2].includes('cursor=expired'))throw new ProductFieldError('Cursor expired',{},422);
    return trialMock(...args);
  });
  renderWithFilters(<TrialBalanceWorkspace {...props} initialRun={trialRun}/>);
  await screen.findByText('Current assets');
  expect(screen.getByRole('radio',{name:'Opening and movement'})).toHaveAttribute('aria-checked','true');
  expect(api.mock.calls.some(call=>call[1]==='POST')).toBe(false);
});

it('refreshes an expired ledger mapping in its branch and lets the account be opened again',async()=>{
  let expired=true;
  api.mockImplementation(async(...args)=>{
    if(args[2].endsWith('/drilldowns')){
      if(expired){expired=false;throw new ProductFieldError('Ledger link expired',{},422);}
      return {...trialJob,id:uuid(91),code:'ACCOUNT_LEDGER'};
    }
    const page=trialMock(...args);
    return page;
  });
  renderWithFilters(<TrialBalanceWorkspace {...props}/>);await screen.findByText('Current assets');
  fireEvent.click(screen.getByRole('button',{name:'Expand Current assets'}));
  fireEvent.click(await screen.findByRole('button',{name:'Cash in hand'}));
  await screen.findByText('Ledger link refreshed. Open the account again.');
  expect(api.mock.calls.filter(call=>call[2].includes('parent='+encodeURIComponent(group)))).toHaveLength(2);
  expect(screen.getByText('Grand total')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'Cash in hand'}));
  await waitFor(()=>expect(goTo).toHaveBeenCalledWith(expect.stringContaining('run='+uuid(91))));
});

it('retries discovery after a temporary outage',async()=>{
  let failed=false;
  api.mockImplementation(async(...args)=>{
    if(!failed&&args[2].endsWith('/report-definitions/TRIAL_BALANCE')){failed=true;throw new ProductFieldError('Discovery unavailable',{},500);}
    return trialMock(...args);
  });
  renderWithFilters(<TrialBalanceWorkspace {...props}/>);await screen.findByText('Discovery unavailable');
  fireEvent.click(screen.getByRole('button',{name:'Retry'}));await screen.findByText('Current assets');
});

it('selects a financial year and submits its dates while rejecting reversed dates',async()=>{
  const earlier={...props.year,id:uuid(95),code:'Earlier year',current:false,startDate:'2025-04-01',endDate:'2026-03-31'};
  renderWithFilters(<TrialBalanceWorkspace {...props} years={[props.year,earlier]}/>);await screen.findByText('Current assets');
  fireEvent.change(screen.getByLabelText('Financial year'),{target:{value:earlier.id}});
  expect(screen.getByLabelText('From date')).toHaveValue(earlier.startDate);
  fireEvent.change(screen.getByLabelText('Financial year'),{target:{value:'custom'}});
  fireEvent.change(screen.getByLabelText('From date'),{target:{value:'2026-05-01'}});
  expect(screen.getByRole('button',{name:'Apply period'})).toBeDisabled();expect(screen.getByText(/From date must/)).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('From date'),{target:{value:earlier.startDate}});
  fireEvent.submit(screen.getByRole('button',{name:'Apply period'}).closest('form')!);
  await waitFor(()=>expect(api.mock.calls.filter(call=>call[1]==='POST')).toHaveLength(2));
  expect(api.mock.calls.filter(call=>call[1]==='POST')[1][3]).toMatchObject({parameters:{date_from:earlier.startDate,date_to:earlier.endDate}});
});

it('switches comparative branches within the same retained report',async()=>{
  api.mockImplementation(async(...args)=>{
    const result=await trialMock(...args);
    return args[2].includes('/hierarchy?')?{...(result as object),periods:['CURRENT','COMPARATIVE']}:result;
  });
  renderWithFilters(<TrialBalanceWorkspace {...props}/>);await screen.findByText('Current assets');
  fireEvent.change(screen.getByLabelText('Statement period'),{target:{value:'COMPARATIVE'}});
  await waitFor(()=>expect(api.mock.calls.some(call=>call[2].includes('period=COMPARATIVE'))).toBe(true));
  expect(api.mock.calls.filter(call=>call[1]==='POST')).toHaveLength(1);
});

it('returns to a previous sibling page and retains full totals',async()=>{
  api.mockImplementation(async(...args)=>{
    const result=await trialMock(...args);
    if(args[2].includes('/hierarchy?'))return {...result as object,items:[row('HEAD',head,'root','Assets',0,0)],page:{has_more:!args[2].includes('cursor='),next_cursor:'second-page'}};
    return result;
  });
  renderWithFilters(<TrialBalanceWorkspace {...props}/>);await screen.findByText('Assets');
  fireEvent.click(screen.getByRole('button',{name:'Next accounts'}));await screen.findByText('Page 2');
  fireEvent.click(screen.getByRole('button',{name:'Previous accounts'}));await screen.findByText('Page 1');
  expect(screen.getByText('Grand total')).toBeInTheDocument();
});

it('refreshes a pending export status using its existing identity',async()=>{
  api.mockImplementation(async(...args)=>{
    if(args[2].endsWith('/exports'))return {...trialJob,id:uuid(10),kind:'EXPORT',status:'QUEUED'};
    if(args[2].endsWith('/report-exports/'+uuid(10)))return {...trialJob,id:uuid(10),kind:'EXPORT',status:'COMPLETE'};
    return trialMock(...args);
  });
  renderWithFilters(<TrialBalanceWorkspace {...props}/>);await screen.findByText('Current assets');chooseCsvExport();
  fireEvent.click(await screen.findByRole('button',{name:'Refresh export status'}));await screen.findByRole('link',{name:'Download CSV'});
  expect(api.mock.calls.filter(call=>call[2].endsWith('/exports'))).toHaveLength(1);
});

it('denies reading without making requests',()=>{
  renderWithFilters(<TrialBalanceWorkspace {...props} permissions={[]}/>);
  expect(screen.getByText(/Your report access is unavailable/)).toBeInTheDocument();expect(api).not.toHaveBeenCalled();
});

it('distinguishes an empty prepared snapshot and retains a truthful zero total',async()=>{
  api.mockImplementation(async(...args)=>{
    const result=await trialMock(...args);
    if(args[2].includes('/hierarchy?'))return {...result as {summary:object},items:[],summary:{...(result as {summary:object}).summary,account_count:0,closing_debit:'0.0000',closing_credit:'0.0000'}};
    return result;
  });
  renderWithFilters(<TrialBalanceWorkspace {...props}/>);await screen.findByText(/No accounts are present/);
  expect(within(screen.getByRole('row',{name:/Grand total/})).getAllByText('0.00')).toHaveLength(2);
});

it('retries a failed branch read and keeps completed totals visible',async()=>{
  let failOnce=true;
  api.mockImplementation(async(...args)=>{
    if(failOnce&&args[2].includes('parent='+encodeURIComponent(group))){failOnce=false;throw new ProductFieldError('Branch unavailable',{},500);}
    return trialMock(...args);
  });
  renderWithFilters(<TrialBalanceWorkspace {...props}/>);await screen.findByText('Current assets');
  fireEvent.click(screen.getByRole('button',{name:'Expand Current assets'}));await screen.findByText('Branch unavailable');
  expect(screen.getByText('Grand total')).toBeInTheDocument();fireEvent.click(screen.getByRole('button',{name:'Retry'}));await screen.findByText('Cash in hand');
});

it('rejects a mismatched ledger response and retains the trial balance',async()=>{
  api.mockImplementation(async(...args)=>args[2].endsWith('/drilldowns')?{...trialJob,kind:'EXPORT'}:trialMock(...args));
  renderWithFilters(<TrialBalanceWorkspace {...props}/>);await screen.findByText('Current assets');
  fireEvent.click(screen.getByRole('button',{name:'Expand Current assets'}));fireEvent.click(await screen.findByRole('button',{name:'Cash in hand'}));
  await screen.findByText(/The ledger response differs/);expect(screen.getByText('Grand total')).toBeInTheDocument();
});

it('finds a ready snapshot on a subsequent bounded source page',async()=>{
  api.mockImplementation(async(...args)=>{
    if(args[2].includes('/report-generations?')&&!args[2].includes('cursor='))return {items:[{id:uuid(70),status:'BUILDING'}],page:{next_cursor:'source-next'}};
    return trialMock(...args);
  });
  renderWithFilters(<TrialBalanceWorkspace {...props}/>);await screen.findByText('Current assets');
  expect(api.mock.calls.some(call=>call[2].includes('cursor=source-next'))).toBe(true);
});

it.each([{code:'ACCOUNT_SUMMARY',status:'COMPLETE',message:'Select a Trial Balance prepared'}, {code:'TRIAL_BALANCE',status:'BLOCKED',message:'The accounting snapshot could not be verified'}])('rejects an incompatible retained run or unverified snapshot',async scenario=>{
  api.mockImplementation(async(...args)=>args[2].endsWith('/report-runs/'+trialRun)?{...trialJob,code:scenario.code,status:scenario.status,failure_code:scenario.status==='BLOCKED'?'REPORT_VERIFICATION_FAILED':null}:trialMock(...args));
  renderWithFilters(<TrialBalanceWorkspace {...props} initialRun={trialRun}/>);await screen.findByText(new RegExp(scenario.message));
  expect(screen.queryByText('Grand total')).not.toBeInTheDocument();
});

it('clears completed rows when company or actor changes',async()=>{
  const mounted=renderWithFilters(<TrialBalanceWorkspace {...props}/>);await screen.findByText('Current assets');
  api.mockImplementation(()=>new Promise(()=>{}));
  mounted.rerender(<TrialBalanceWorkspace {...props} company={uuid(96)} actor={uuid(97)}/>);
  expect(screen.queryByText('Grand total')).not.toBeInTheDocument();expect(screen.queryByText('Current assets')).not.toBeInTheDocument();
});

it('retains a completed statement while a failed refresh automatically falls back to a fresh source',async()=>{
  let refreshes=0;
  api.mockImplementation(async(...args)=>{
    if(args[1]==='POST'&&args[2].endsWith('/report-generations'))return {id:uuid(70),status:++refreshes===1?'FAILED':'READY'};
    return trialMock(...args);
  });
  renderWithFilters(<TrialBalanceWorkspace {...props} permissions={[...props.permissions,'report.definition.manage']}/>);await screen.findByText('Current assets');
  fireEvent.click(screen.getByRole('button',{name:'Refresh accounting data'}));
  expect(screen.getByText('Grand total')).toBeInTheDocument();
  await waitFor(()=>expect(refreshes).toBe(2));
  expect(api.mock.calls.find(call=>call[2].endsWith('/report-generations'))![3]).toMatchObject({strategy:'REFRESH',base_generation_id:trialJob.generation_id});
});

it('retries source preparation after both bounded builds fail while keeping completed rows',async()=>{
 let attempts=0;
 api.mockImplementation(async(...args)=>args[1]==='POST'&&args[2].endsWith('/report-generations')?{id:uuid(70),status:++attempts<=2?'FAILED':'READY'}:trialMock(...args));
 renderWithFilters(<TrialBalanceWorkspace {...props} permissions={[...props.permissions,'report.definition.manage']}/>);
 await screen.findByText('Current assets');
 fireEvent.click(screen.getByRole('button',{name:'Refresh accounting data'}));
 await screen.findByText(/could not be verified after rebuilding/);
 expect(screen.getByText('Grand total')).toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'Retry'}));
 await waitFor(()=>expect(attempts).toBe(3));
});

it('rejects malformed saved layout values and ignores invalid cursor windows',()=>{
  const saved={run:trialRun,mode:'default',settings:initialTrialPresentation,scroll:0,cursors:{root:{values:[null],position:0}}};
  for(const changes of [{mode:'other'},{settings:null},{settings:{...initialTrialPresentation,level:'other'}},{settings:{...initialTrialPresentation,period:'other'}},{settings:{...initialTrialPresentation,show_zero:'true'}},{settings:{...initialTrialPresentation,expanded:null}},{settings:{...initialTrialPresentation,expanded:Array(2001).fill(group)}}])expect(restoreTrial(JSON.stringify({...saved,...changes}),trialRun)).toBeNull();
  for(const entry of [{values:[null],position:0,offset:-1},{values:[null],position:-1},{values:Array(101).fill(null),position:0},{values:['x'.repeat(4097)],position:0},{values:[42],position:0}])expect(restoreTrial(JSON.stringify({...saved,cursors:{root:entry}}),trialRun)?.cursors).toEqual({});
});

it('discloses frozen display residuals without changing exact totals',async()=>{
  api.mockImplementation(async(...args)=>{
    const result=await trialMock(...args);
    if(args[2].includes('/hierarchy?')){
      const page=result as {summary:object;items:{data:object}[]};
      return {...page,summary:{...page.summary,display_residual:{closing_debit:'0.0100'}},items:page.items.map(item=>({...item,data:{...item.data,display_residual:{closing_debit:'0.0100'}}}))};
    }
    return result;
  });
  renderWithFilters(<TrialBalanceWorkspace {...props}/>);await screen.findByText('Current assets');
  expect(screen.getByRole('note')).toHaveTextContent('closing debit 0.01 INR');
  expect(within(screen.getByRole('row',{name:/Grand total/})).getAllByText('260.00')).toHaveLength(2);
  expect(screen.getAllByTitle('Exact amount: 260.0000').length).toBeGreaterThan(0);
  fireEvent.click(screen.getByRole('radio',{name:'Opening and movement'}));
  expect(screen.getByRole('note')).toHaveTextContent('Exact balances remain reconciled.');
});

it('pages history to open older completed trial balances without preparing another report',async()=>{
  const older=uuid(94);
  api.mockImplementation(async(...args)=>{
    if(args[2].includes('/report-runs?'))return args[2].includes('cursor=older')?{items:[{id:older,code:'TRIAL_BALANCE',status:'COMPLETE',created_at:'2025-04-30T00:00:00Z'}],page:{next_cursor:null}}:{items:[],page:{next_cursor:'older'}};
    if(args[2].endsWith('/report-runs/'+older))return {...trialJob,id:older,version:5};
    return trialMock(...args);
  });
  renderWithFilters(<TrialBalanceWorkspace {...props}/>);await screen.findByText('Current assets');
  fireEvent.click(screen.getByText('Report history and source details'));fireEvent.click(screen.getByRole('button',{name:'Load history'}));
  fireEvent.click(await screen.findByRole('button',{name:'Older reports'}));
  fireEvent.click(await screen.findByRole('button',{name:/30 Apr 2025/}));await screen.findByText('Legacy result '+older);
  expect(api.mock.calls.filter(call=>call[1]==='POST')).toHaveLength(1);
});

it('cancels a pending branch when collapsed and can immediately expand it again',async()=>{
  let pendingSignal:AbortSignal|undefined,reads=0;
  api.mockImplementation(async(...args)=>{
    if(args[2].includes('parent='+encodeURIComponent(group))&&++reads===1){
      pendingSignal=args[5];return new Promise(()=>{});
    }
    return trialMock(...args);
  });
  renderWithFilters(<TrialBalanceWorkspace {...props}/>);await screen.findByText('Current assets');
  fireEvent.click(screen.getByRole('button',{name:'Expand Current assets'}));
  await waitFor(()=>expect(reads).toBe(1));
  fireEvent.click(screen.getByRole('button',{name:'Collapse Current assets'}));
  expect(pendingSignal?.aborted).toBe(true);
  fireEvent.click(screen.getByRole('button',{name:'Expand Current assets'}));
  await screen.findByText('Cash in hand');expect(reads).toBe(2);
});

it('pauses child reads while changing periods and loads only the new period afterwards',async()=>{
  let releaseRoot:((value:unknown)=>void)|undefined,oldReads=0;
  const pendingSignals:AbortSignal[]=[];
  api.mockImplementation(async(...args)=>{
    if(args[2].includes('/hierarchy?')){
      const query=new URLSearchParams(args[2].split('?')[1]);
      if(query.get('parent')===group&&query.get('period')==='CURRENT'){
        oldReads++;pendingSignals.push(args[5]!);return new Promise(()=>{});
      }
      const original=await trialMock(...args) as {items:{data:{row_kind:string;name:string}}[]};
      const page={...original,periods:['CURRENT','COMPARATIVE'],items:original.items.map(item=>item.data.row_kind==='ACCOUNT'?{...item,data:{...item.data,name:'Comparative cash'}}:item)};
      if(query.get('parent')==='root'&&query.get('period')==='COMPARATIVE')return new Promise(resolve=>{releaseRoot=resolve;});
      return page;
    }
    return trialMock(...args);
  });
  renderWithFilters(<TrialBalanceWorkspace {...props}/>);await screen.findByText('Current assets');
  fireEvent.click(screen.getByRole('button',{name:'Expand Current assets'}));await waitFor(()=>expect(oldReads).toBe(1));
  fireEvent.change(screen.getByLabelText('Statement period'),{target:{value:'COMPARATIVE'}});
  await act(async()=>{});
  expect(oldReads).toBe(1);expect(pendingSignals.every(signal=>signal.aborted)).toBe(true);
  expect(screen.getByLabelText('Expand hierarchy')).toBeDisabled();
  expect(screen.getByLabelText('Show zero rows')).toBeDisabled();
  expect(screen.getByRole('button',{name:'Collapse Current assets'})).toBeDisabled();
  const root=await trialMock('reports','GET','/hierarchy?parent=root') as object;
  await act(async()=>{releaseRoot!({...root,periods:['CURRENT','COMPARATIVE']});});
  await screen.findByText('Comparative cash');
  expect(api.mock.calls.filter(call=>call[1]==='POST')).toHaveLength(1);
});

it.each(['Closing balances','Opening and movement'])('keeps filters, nested disclosures and totals consistent in %s',async layout=>{
  api.mockImplementation(hierarchyMock as typeof productFieldRequest);
  renderWithFilters(<TrialBalanceWorkspace {...props}/>);await screen.findByText('Current assets');
  fireEvent.click(screen.getByRole('radio',{name:layout}));
  fireEvent.click(screen.getByLabelText('Show zero rows'));await waitFor(()=>expect(screen.getByLabelText('Show zero rows')).toBeChecked());
  const total=()=>within(screen.getByRole('row',{name:/Grand total/}));
  expect(total().getAllByText('33.00')).toHaveLength(2);
  fireEvent.change(screen.getByLabelText('Expand hierarchy'),{target:{value:'HEADS'}});
  expect(screen.queryByText('Current assets')).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Expand hierarchy'),{target:{value:'GROUPS'}});
  await screen.findByText('Current assets');expect(screen.queryByText('Wallet accounts')).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Expand hierarchy'),{target:{value:'ALL_GROUPS'}});
  await screen.findByText('Wallet accounts');expect(screen.queryByText('Cash account')).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Expand hierarchy'),{target:{value:'LEDGERS'}});
  await screen.findByText('Cash account');await screen.findByText('Supplier payable');
  expect(screen.getByText('Quiet account')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'Collapse Wallet accounts'}));
  expect(screen.queryByText('Cash account')).not.toBeInTheDocument();expect(screen.getByText('Bank ledger')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'Collapse Assets'}));
  expect(screen.queryByText('Wallet accounts')).not.toBeInTheDocument();expect(screen.getByText('Supplier payable')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'Expand Assets'}));await screen.findByText('Wallet accounts');
  expect(screen.queryByText('Cash account')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'Expand Wallet accounts'}));await screen.findByText('Cash account');
  fireEvent.click(screen.getByLabelText('Show zero rows'));await waitFor(()=>expect(screen.queryByText('Quiet account')).not.toBeInTheDocument());
  await screen.findByText('Moving clearing');
  expect(within(screen.getByRole('row',{name:/Moving clearing/})).getAllByRole('cell').slice(-2).map(cell=>cell.textContent)).toEqual(['0.00','0.00']);
  expect(total().getAllByText('33.00')).toHaveLength(2);
  fireEvent.change(screen.getByLabelText('Statement period'),{target:{value:'COMPARATIVE'}});
  await waitFor(()=>expect(total().getAllByText('66.00')).toHaveLength(2));await screen.findByText('Cash account');
  expect(screen.queryByText('Quiet account')).not.toBeInTheDocument();
  expect(within(screen.getByRole('row',{name:/Cash account/})).getAllByRole('cell').slice(-2).map(cell=>cell.textContent)).toEqual(['30.00','0.00']);
  chooseCsvExport();await screen.findByRole('link',{name:'Download CSV'});
  expect(api.mock.calls.find(call=>call[2].endsWith('/exports'))![3]).toMatchObject({view:layout==='Closing balances'?'default':'detailed',trial_balance:{period:'COMPARATIVE',show_zero:false,level:'LEDGERS',hierarchy:'CURRENT',expanded:expect.arrayContaining([hierarchyKeys.assets,hierarchyKeys.wallet])}});
  fireEvent.click(screen.getByLabelText('Show zero rows'));await screen.findByText('Quiet account');
  expect(total().getAllByText('66.00')).toHaveLength(2);
  expect(api.mock.calls.filter(call=>call[1]==='POST'&&call[2].endsWith('/report-runs'))).toHaveLength(1);
});

it.each(['Closing balances','Opening and movement'])('replaces sibling pages and retains disclosures and full totals in %s',async layout=>{
  api.mockImplementation(async(...args)=>{
    const result=await hierarchyMock(...args);
    if(args[2].includes('parent='+encodeURIComponent(hierarchyKeys.wallet))){
      const page=result as {items:unknown[]},second=args[2].includes('cursor=wallet-next');
      return {...page,items:second?page.items.slice(2):page.items.slice(0,2),page:{has_more:!second,next_cursor:second?null:'wallet-next',limit:50}};
    }
    return result;
  });
  renderWithFilters(<TrialBalanceWorkspace {...props}/>);await screen.findByText('Current assets');
  fireEvent.click(screen.getByRole('radio',{name:layout}));
  fireEvent.click(screen.getByLabelText('Show zero rows'));await waitFor(()=>expect(screen.getByLabelText('Show zero rows')).toBeChecked());
  fireEvent.change(screen.getByLabelText('Expand hierarchy'),{target:{value:'LEDGERS'}});
  await screen.findByText('Cash account');expect(screen.queryByText('Quiet account')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'Next accounts'}));await screen.findByText('Quiet account');
  expect(screen.queryByText('Cash account')).not.toBeInTheDocument();expect(screen.getByText('Bank ledger')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('radio',{name:layout==='Closing balances'?'Opening and movement':'Closing balances'}));
  expect(screen.getByText('Quiet account')).toBeInTheDocument();expect(screen.getByText('Page 2')).toBeInTheDocument();
  expect(within(screen.getByRole('row',{name:/Grand total/})).getAllByText('33.00')).toHaveLength(2);
  fireEvent.click(screen.getByRole('button',{name:'Previous accounts'}));await screen.findByText('Cash account');
  expect(screen.queryByText('Quiet account')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'Collapse Wallet accounts'}));expect(screen.queryByText('Cash account')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'Expand Wallet accounts'}));await screen.findByText('Cash account');
  expect(screen.getByText('Bank ledger')).toBeInTheDocument();expect(screen.getByText('Page 1')).toBeInTheDocument();
  expect(api.mock.calls.filter(call=>call[1]==='POST'&&call[2].endsWith('/report-runs'))).toHaveLength(1);
});
