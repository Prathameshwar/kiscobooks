import {beforeEach,expect,it,vi} from 'vitest';
import {fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {DEFAULT_DISPLAY_CONFIG,DisplayConfigProvider} from '@janso/ui';
import {AnalyticsReportWorkspace} from '../app/components/AnalyticsReportWorkspace';
import {AnalyticsInsights} from '../app/components/AnalyticsInsights';
import {productFieldRequest} from '../app/lib/product-fields';
import {analyticsCodes,analyticsWorkspaces,type AnalyticsCode,type AnalyticsSummary} from '../app/lib/analytics-workspace';
vi.mock('../app/lib/product-fields',()=>({productFieldRequest:vi.fn()}));
const company='01990000-0000-7000-8000-000000000001',generation='01990000-0000-7000-8000-000000000002',identity='01990000-0000-7000-8000-000000000003';
const columns=['period','label','net_sales','invoice_count','returns','average_invoice','contribution_percent','currency','party_id'].map(key=>({key,title:key.replaceAll('_',' '),kind:key.endsWith('_id')?'IDENTIFIER':['net_sales','returns','average_invoice'].includes(key)?'MONEY':key==='invoice_count'?'INTEGER':'TEXT',currency_key:'currency'}));
let view='default',code:AnalyticsCode='SALES_PERFORMANCE';
const definition=()=>({definition:{code,version:1,title:analyticsWorkspaces[code].title,views:[{key:'default',title:'Customers',columns},{key:'products',title:'Products',columns}]},parameter_schema:{required:['date_from','date_to'],properties:{date_from:{type:'string',format:'date'},date_to:{type:'string',format:'date'},search:{type:'string',default:''},currency:{anyOf:[{type:'string'},{type:'null'}]},grain:{type:'string',enum:['DAY','MONTH'],default:'MONTH'},comparative_from:{type:'string',format:'date'},comparative_to:{type:'string',format:'date'}}},run_enabled:true,export_limits:['CSV','XLSX','PDF'].map(format=>({format,max_rows:1000,max_cells:10000})),package_limits:{max_rows:5000,max_parts:10}});
const summary=():AnalyticsSummary=>({code,calculation_version:1,date_from:'2026-04-01',date_to:'2026-04-30',comparison_present:false,amounts:{CURRENT:{INR:{net_sales:'800',posted_income:'1000',gross_profit:'600',operating_expenses:'100',net_profit:'500',gross_margin_percent:'60',invoice_count:1,returns:'200',average_invoice:'1000',discounts:'100'}}},trends:[{period:'CURRENT',currency:'INR',date:'2026-04-01',net_sales:'800'}],notices:['Commercial sales exclude GST.']});
const job=()=>({id:identity,generation_id:generation,code,version:1,title:analyticsWorkspaces[code].title,kind:'RUN',status:'COMPLETE',parameters:{date_from:'2026-04-01',date_to:'2026-04-30'},view,views:definition().definition.views,completed_rows:1,result:{evidence:{analytics:summary()}}});
beforeEach(()=>{code='SALES_PERFORMANCE';view='default';window.localStorage.clear();vi.mocked(productFieldRequest).mockReset();vi.mocked(productFieldRequest).mockImplementation(async(_service,method,path,body)=>{
 if(path.includes('/report-definitions/'))return definition();
 if(path.includes('/report-generations?'))return {items:[{id:generation,status:'READY'}],page:{next_cursor:null}};
 if(path.endsWith('/report-generations/'+generation))return {id:generation,status:'READY',manifest:{control:{coverage_start:'2026-04-01'}}};
 if(method==='POST'&&path.endsWith('/report-runs')){view=(body as {view:string}).view;return job();}
 if(path.includes('/rows?'))return {items:[{ordinal:1,data:{period:'CURRENT',label:'Buyer',net_sales:'800',invoice_count:1,returns:'200',currency:'INR'},drilldowns:[{key:'row_detail',title:'Frozen row details',method:'GET',token:'signed-test'}]}],page:{next_cursor:null}};
 if(path.includes('/rows/1?'))return {data:{label:'Buyer',net_sales:'800'}};
 if(path.endsWith('/exports'))return {id:identity,kind:'EXPORT',status:'COMPLETE',format:(body as {format:string}).format,delivery:'SINGLE',views:[]};
 if(path.endsWith('/report-runs/'+identity))return job();
 throw new Error('Unexpected test request '+path);
});});
const mount=(permissions=['report.read','report.export','report.definition.manage'])=>render(<DisplayConfigProvider config={DEFAULT_DISPLAY_CONFIG}><AnalyticsReportWorkspace report={code} company={company} companyName="Example Traders" actor="actor" permissions={permissions}/></DisplayConfigProvider>);
it('opens sales insights with date fields, meaningful columns and shared actions',async()=>{mount();await screen.findByText('Buyer');expect(screen.getByRole('heading',{name:'Sales performance'})).toBeVisible();expect(screen.getByLabelText('From date')).toHaveAttribute('type','date');expect(screen.getByRole('region',{name:'Business insights'})).toHaveTextContent('800.00');expect(screen.getByRole('link',{name:'Analytics'})).toHaveAttribute('href','/reports/analytics');expect(screen.queryByRole('columnheader',{name:/party id/i})).toBeNull();expect(screen.getByRole('button',{name:'Refresh accounting data'})).toBeVisible();});
it('changes breakdown view without changing the report identity',async()=>{mount();await screen.findByText('Buyer');fireEvent.change(screen.getByLabelText('Report view'),{target:{value:'products'}});fireEvent.click(screen.getByRole('button',{name:'Apply'}));await waitFor(()=>expect(screen.getByRole('button',{name:'Print / PDF'})).toBeEnabled());const calls=vi.mocked(productFieldRequest).mock.calls.filter(call=>call[1]==='POST'&&call[2].endsWith('/report-runs'));expect(calls.at(-1)?.[3]).toMatchObject({code:'SALES_PERFORMANCE',view:'products'});});
it('uses the kebab drawer without inserting details into the row',async()=>{mount();await screen.findByText('Buyer');fireEvent.click(screen.getByRole('button',{name:/Actions for/}));fireEvent.click(screen.getByRole('menuitem',{name:'Frozen row details'}));const drawer=await screen.findByRole('dialog',{name:'Frozen row details'});await within(drawer).findByText('Buyer');expect(screen.getByRole('region',{name:'Sales performance rows'}).querySelector('tbody dl')).toBeNull();});
it('hides export actions without the export grant',async()=>{mount(['report.read']);await screen.findByText('Buyer');expect(screen.queryByRole('button',{name:'Print / PDF'})).toBeNull();expect(screen.queryByRole('button',{name:'Export'})).toBeNull();});
it('prevents exports until changed filters are applied',async()=>{mount();await screen.findByText('Buyer');fireEvent.change(screen.getByLabelText('Search report rows and references'),{target:{value:'Other'}});expect(screen.getByRole('button',{name:'Print / PDF'})).toBeDisabled();});
it('shows retry when definition discovery fails',async()=>{vi.mocked(productFieldRequest).mockRejectedValueOnce(new Error('Analytics unavailable'));mount();await screen.findByText('Analytics unavailable');expect(screen.getByRole('button',{name:'Retry loading book'})).toBeVisible();});
it('keeps currency totals separate and undefined comparison values visible',()=>{const data=summary();data.comparison_present=true;data.amounts.CURRENT.USD={net_sales:'50'};render(<DisplayConfigProvider config={DEFAULT_DISPLAY_CONFIG}><AnalyticsInsights summary={data}/></DisplayConfigProvider>);expect(screen.getByRole('region',{name:'INR insights'})).toHaveTextContent('800.00');expect(screen.getByRole('region',{name:'USD insights'})).toHaveTextContent('50.00');expect(screen.getByRole('region',{name:'USD insights'})).toHaveTextContent('Comparison: Unavailable');});

it.each(analyticsCodes)('renders the implemented %s workspace with its own insights',async report=>{code=report;mount();await screen.findByText('Buyer');expect(screen.getByRole('heading',{name:analyticsWorkspaces[report].title})).toBeVisible();expect(screen.getByRole('region',{name:'Business insights'})).toBeVisible();await waitFor(()=>expect(screen.getByRole('button',{name:'Print / PDF'})).toBeEnabled());});

it('shows opening cash and adjustments so the cash balance can be reconciled',()=>{
 const data=summary();data.code='CASH_WORKING_CAPITAL';data.amounts.CURRENT.INR={opening_cash:'1000',cash_receipts:'500',cash_payments:'0',cash_adjustments:'75',closing_cash:'1575',overdue_receivables:'0',supplier_dues:'0',stock_tied_up:null};
 render(<DisplayConfigProvider config={DEFAULT_DISPLAY_CONFIG}><AnalyticsInsights summary={data}/></DisplayConfigProvider>);
 expect(screen.getByText('Opening cash and bank balance')).toBeVisible();
 expect(screen.getByText('Opening adjustments')).toBeVisible();
 expect(screen.getByRole('region',{name:'INR insights'})).toHaveTextContent('75.00');
});

it('shows incomplete evidence and imported-balance limits without expanding calculation notes',()=>{
 const data=summary();data.notices=['Product costs are unavailable without complete movement evidence.','Company totals include verified imported YTD.'];
 render(<AnalyticsInsights summary={data}/>);
 for(const note of data.notices)expect(screen.getByText(note).closest('details')).toBeNull();
});

it('keeps credit direction, bill references and slow-stock status visible by default',async()=>{
 code='CASH_WORKING_CAPITAL';const initial=columns.length;
 columns.push(...['reference','direction','stock_status','quantity','unit','net_movement'].map(key=>({key,title:key.replaceAll('_',' '),kind:'TEXT',currency_key:'currency'})));
 try{mount();await screen.findByText('Buyer');for(const key of ['reference','direction','stock status','quantity','unit','net movement'])expect(screen.getByRole('columnheader',{name:new RegExp(key,'i')})).toBeVisible();}
 finally{columns.splice(initial);}
});

it('does not promise a period-trend view that customer reports do not provide',()=>{
 const data=summary();data.code='CUSTOMER_INSIGHTS';data.trends=Array.from({length:25},(_,index)=>({period:'CURRENT',currency:'INR',date:'2026-04-'+String(index+1).padStart(2,'0'),net_sales:'10'}));
 render(<DisplayConfigProvider config={DEFAULT_DISPLAY_CONFIG}><AnalyticsInsights summary={data}/></DisplayConfigProvider>);
 expect(screen.getByText(/Chart shows the latest 24 intervals/)).toBeVisible();
 expect(screen.queryByText(/The Period trend view includes all intervals/)).not.toBeInTheDocument();
});

it.each([
 ['SALES_PERFORMANCE','Net sales trend'],['CUSTOMER_INSIGHTS','Net sales trend'],
 ['PROFIT_MARGIN_ANALYSIS','Net profit trend'],['EXPENSE_PROFIT_LEAKAGE','Expense trend'],
 ['CASH_WORKING_CAPITAL','Net cash movement trend'],
] as const)('names the plotted metric accurately for %s',(report,title)=>{
 const data=summary();data.code=report;data.trends=[{period:'CURRENT',currency:'INR',date:'2026-04-01',net_sales:'800',amount:'500'}];
 render(<DisplayConfigProvider config={DEFAULT_DISPLAY_CONFIG}><AnalyticsInsights summary={data}/></DisplayConfigProvider>);
 expect(screen.getByRole('heading',{name:title})).toBeVisible();
 expect(screen.getByRole('img',{name:'INR '+title.toLowerCase()})).toBeVisible();
});

it('prepares Sales data automatically when no ready snapshot exists',async()=>{
 const original=vi.mocked(productFieldRequest).getMockImplementation()!;
 vi.mocked(productFieldRequest).mockImplementation(async(service,method,path,body,...rest)=>{
  if(path.includes('/report-generations?'))return {items:[],page:{next_cursor:null}};
  if(method==='POST'&&path.endsWith('/report-generations'))return {id:generation,status:'READY',strategy:'FRESH'};
  return original(service,method,path,body,...rest);
 });
 mount();await screen.findByText('Buyer');
 expect(vi.mocked(productFieldRequest).mock.calls.some(call=>call[1]==='POST'&&call[2].endsWith('/report-generations'))).toBe(true);
});

it('preserves the full fiscal year for Profit analytics with imported YTD',async()=>{
 code='PROFIT_MARGIN_ANALYSIS';const original=vi.mocked(productFieldRequest).getMockImplementation()!;
 vi.mocked(productFieldRequest).mockImplementation(async(service,method,path,body,...rest)=>{
  if(path.endsWith('/report-generations/'+generation))return {id:generation,status:'READY',manifest:{control:{coverage_start:'2026-10-31'}}};
  return original(service,method,path,body,...rest);
 });
 render(<AnalyticsReportWorkspace report={code} company={company} companyName="Example" actor="actor" permissions={['report.read']} year={{id:'year',code:'FY26',startDate:'2026-04-01',endDate:'2027-03-31',current:true,open:true}}/>);
 await screen.findByText('Buyer');
 expect(vi.mocked(productFieldRequest).mock.calls.find(call=>call[1]==='POST'&&call[2].endsWith('/report-runs'))?.[3]).toMatchObject({parameters:{date_from:'2026-04-01'}});
});

it('opens retained Customer insights before new-run source availability',async()=>{
 code='CUSTOMER_INSIGHTS';const original=vi.mocked(productFieldRequest).getMockImplementation()!;
 vi.mocked(productFieldRequest).mockImplementation(async(service,method,path,body,...rest)=>{
  if(path.includes('/report-definitions/'))return {...definition(),run_enabled:false};
  if(path.includes('/report-generations?'))throw new Error('New source is unavailable');
  return original(service,method,path,body,...rest);
 });
 render(<AnalyticsReportWorkspace report={code} company={company} companyName="Example" actor="actor" permissions={['report.read']} initialRun={identity}/>);
 await screen.findByText('Buyer');
 expect(vi.mocked(productFieldRequest).mock.calls.some(call=>call[1]==='POST')).toBe(false);
});

it('recovers Expense verification once without asking for a manual refresh',async()=>{
 code='EXPENSE_PROFIT_LEAKAGE';const original=vi.mocked(productFieldRequest).getMockImplementation()!;let attempts=0;
 vi.mocked(productFieldRequest).mockImplementation(async(service,method,path,body,...rest)=>{
  if(method==='POST'&&path.endsWith('/report-runs')&&attempts++===0)return {...job(),status:'BLOCKED',failure_code:'REPORT_VERIFICATION_FAILED'};
  if(method==='POST'&&path.endsWith('/report-generations'))return {id:generation,status:'READY',strategy:'REFRESH'};
  return original(service,method,path,body,...rest);
 });
 mount();await screen.findByText('Buyer');expect(attempts).toBe(2);
});

it('offers a Stop control while Cash analytics waits for its worker',async()=>{
 code='CASH_WORKING_CAPITAL';const original=vi.mocked(productFieldRequest).getMockImplementation()!;
 vi.mocked(productFieldRequest).mockImplementation(async(service,method,path,body,...rest)=>{
  if(method==='POST'&&path.endsWith('/report-runs'))return {...job(),status:'QUEUED'};
  if(path.endsWith('/cancel'))return {...job(),status:'CANCELLED'};
  return original(service,method,path,body,...rest);
 });
 mount();fireEvent.click(await screen.findByRole('button',{name:'Stop report'}));
 await screen.findByText('Report stopped. Apply filters to run it again.');
});

it('removes retained analytics amounts when the server revokes access',async()=>{
 mount();await screen.findByText('Buyer');
 vi.mocked(productFieldRequest).mockRejectedValueOnce(Object.assign(new Error('Access revoked'),{status:403}));
 fireEvent.click(screen.getByRole('button',{name:'Refresh'}));
 await screen.findByRole('alert');
 expect(screen.queryByText('Buyer')).toBeNull();
 expect(screen.queryByRole('region',{name:'Business insights'})).toBeNull();
});

it('shows debit and credit amounts when Analytics drills into an account ledger',async()=>{
 code='PROFIT_MARGIN_ANALYSIS';const original=vi.mocked(productFieldRequest).getMockImplementation()!;let child=false;
 const ledgerColumns=[{key:'account_name',title:'Account',kind:'TEXT'},{key:'debit',title:'Debit',kind:'MONEY',currency_key:'currency'},{key:'credit',title:'Credit',kind:'MONEY',currency_key:'currency'}];
 const ledger={...job(),code:'ACCOUNT_LEDGER',title:'Account ledger',origin:{parent_id:identity},views:[{key:'default',title:'Ledger entries',columns:ledgerColumns}]};
 vi.mocked(productFieldRequest).mockImplementation(async(service,method,path,body,...rest)=>{
  if(path.endsWith('/drilldowns')){child=true;return ledger;}
  if(path.endsWith('/report-definitions/ACCOUNT_LEDGER'))return {...definition(),definition:{...definition().definition,code:'ACCOUNT_LEDGER',views:ledger.views}};
  if(path.includes('/rows?'))return {items:[{ordinal:1,data:child?{account_name:'Cash',debit:'125',credit:'0',currency:'INR'}:{label:'Income'},drilldowns:child?[]:[{key:'account_entries',title:'Account ledger',method:'POST',token:'scoped'}]}],page:{next_cursor:null}};
  return original(service,method,path,body,...rest);
 });
 mount();await screen.findByText('Income');fireEvent.click(screen.getByRole('button',{name:/Actions for/}));fireEvent.click(screen.getByRole('menuitem',{name:'Account ledger'}));
 await screen.findByText('Cash');expect(screen.getByRole('columnheader',{name:'Debit'})).toBeVisible();expect(screen.getByText('125.00')).toBeVisible();
});

