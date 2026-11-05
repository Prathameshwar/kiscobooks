import {beforeEach,expect,it,vi} from 'vitest';
import {act,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {DEFAULT_DISPLAY_CONFIG,DisplayConfigProvider} from '@janso/ui';
import type {TaxReportCode,TaxSummary} from '../app/lib/tax-workspace';
import type {FiscalYearChoice} from '../app/lib/company-context';
import {TaxReportWorkspace} from '../app/components/TaxReportWorkspace';
import {TaxReportTotals} from '../app/components/TaxReportTotals';
import {productFieldRequest} from '../app/lib/product-fields';
vi.mock('../app/lib/product-fields',()=>({productFieldRequest:vi.fn()}));
const company='01990000-0000-7000-8000-000000000001',generation='01990000-0000-7000-8000-000000000002',identity='01990000-0000-7000-8000-000000000003';
const columns=['period','posting_date','event_date','bill_reference','account_name','tax_code','tax_purpose','invoice_kind','component_taxable_basis','tax_amount','recorded_tax','pending','eligible_unclaimed','claimed','suspended','blocked','action','event_amount','currency','side','amount','invoice_id'].map(key=>({key,title:key.replaceAll('_',' '),kind:key.endsWith('_date')?'DATE':['component_taxable_basis','tax_amount','recorded_tax','pending','eligible_unclaimed','claimed','suspended','blocked','event_amount','amount'].includes(key)?'MONEY':key.endsWith('_id')?'IDENTIFIER':'TEXT',currency_key:'currency'}));
let view='default',code='INVOICE_TAX_REGISTER',permissions=['report.read','report.export','report.definition.manage'];
const project=(keys:string[])=>columns.filter(column=>keys.includes(column.key));
const views=()=>code==='INVOICE_CREDIT_REGISTER'?[
 {key:'default',title:'Closing positions',columns:project(['period','bill_reference','account_name','tax_code','currency','recorded_tax','pending','eligible_unclaimed','claimed','suspended','blocked'])},
 {key:'events',title:'Period events',columns:project(['period','posting_date','event_date','bill_reference','account_name','tax_code','action','event_amount','currency'])},
 {key:'events_detail',title:'Event source details',columns:project(['period','posting_date','event_date','bill_reference','account_name','tax_code','action','event_amount','currency','invoice_id'])},
]:[{key:'default',title:'Business detail',columns:project(code==='TAX_GL_BRIDGE'?['period','posting_date','bill_reference','account_name','tax_code','side','amount','currency']:['period','posting_date','bill_reference','account_name','invoice_kind','tax_code','component_taxable_basis','tax_amount','currency'])},{key:'full',title:'Full recorded source details',columns}];
const definition=()=>({definition:{code,version:6,title:'Invoice Tax Register',views:views()},parameter_schema:{required:['date_from','date_to'],properties:{date_from:{type:'string',format:'date'},date_to:{type:'string',format:'date'},date_basis:{type:'string',enum:['POSTING','DOCUMENT','TAX_POINT'],default:'POSTING'},search:{type:'string',default:''},...(code==='TAX_GL_BRIDGE'?{tax_ledger_id:{anyOf:[{type:'string',format:'uuid'},{type:'null'}]},tax_purpose:{anyOf:[{type:'string'},{type:'null'}]}}:{})}},run_enabled:true,export_limits:['CSV','XLSX','HTML','PDF'].map(format=>({format,max_rows:1000,max_cells:10000})),package_limits:{max_rows:5000,max_parts:10}});
const job=()=>({id:identity,generation_id:generation,code,version:6,kind:'RUN',status:'COMPLETE',parameters:{date_from:'2026-04-01',date_to:'2026-04-30'},view,views:definition().definition.views,completed_rows:1,result:{evidence:{tax_summary:{code,row_count:1,invoice_count:1,component_count:1,ledger_count:1,verification:'VERIFIED_SOURCE_LINEAGE',...(code==='INVOICE_CREDIT_REGISTER'?{mode:view.startsWith('events')?'EVENTS':'POSITIONS',position_count:view.startsWith('events')?0:1,event_count:view.startsWith('events')?1:0,event_amounts:{INR:{VERIFY:'20'}},amounts:{INR:{recorded_tax:'20',pending:'20'}}}:code==='TAX_GL_BRIDGE'?{amounts:{INR:{debit:'0',credit:'20',net:'-20'}}}:{amounts:{INR:{taxable_value:'100',tax_amount:'18',outward_tax:'18'}}})}}}});
let detail=false;
const resultRow=()=>({ordinal:1,data:{period:'CURRENT',bill_reference:'INV-1',account_name:code==='TAX_GL_BRIDGE'?'Output IGST':'Customer',tax_code:'IGST',taxable_value:'100',component_taxable_basis:'100',tax_amount:'18',recorded_tax:'20',pending:'20',event_amount:'20',action:'VERIFY',side:'CREDIT',amount:'20',currency:'INR'},drilldowns:detail?[{key:'row_detail',title:'View retained row detail',method:'GET',token:'signed-test'},{key:'journal_entries',title:'View journal entries',method:'POST',token:'signed-journal'}]:[]});
beforeEach(()=>{detail=false;view='default';code='INVOICE_TAX_REGISTER';permissions=['report.read','report.export','report.definition.manage'];window.localStorage.clear();vi.mocked(productFieldRequest).mockReset();vi.mocked(productFieldRequest).mockImplementation(async(_service,method,path,body)=>{
 if(path.includes('/report-definitions/'))return definition();
 if(path.includes('/report-generations?'))return {items:[{id:generation,status:'READY'}],page:{next_cursor:null}};
 if(path.endsWith('/report-generations/'+generation))return {id:generation,status:'READY',manifest:{control:{coverage_start:'2026-04-01'}}};
 if(path.includes('/rows'))return path.includes('/rows/1?')?resultRow():{items:[resultRow()],page:{next_cursor:null}};
 if(method==='POST'&&path.endsWith('/report-runs')){view=(body as {view?:string})?.view??'default';return job();}
 if(path.includes('/report-runs?'))return {items:[],page:{next_cursor:null}};
 if(path.includes('/report-runs/'))return job();
 throw new Error('Unexpected tax request '+path);
});});
function mount(year?:FiscalYearChoice){return render(<DisplayConfigProvider config={DEFAULT_DISPLAY_CONFIG}><TaxReportWorkspace report={code as TaxReportCode} company={company} companyName="Example Traders" actor="actor" permissions={permissions} year={year}/></DisplayConfigProvider>);}
it('opens a dedicated tax workspace with calendar, totals and print',async()=>{mount();await waitFor(()=>expect(screen.getByRole('button',{name:'Print / PDF'})).toBeEnabled());expect(screen.getByRole('heading',{name:'Invoice Tax Register'})).toBeVisible();expect(screen.getByLabelText('From date')).toHaveAttribute('type','date');expect(screen.getByRole('region',{name:'Invoice Tax Register totals'})).toHaveTextContent('100.00');expect(screen.queryByRole('columnheader',{name:'invoice id'})).not.toBeInTheDocument();});
it('disables printing while full-result search is unapplied',async()=>{mount();await waitFor(()=>expect(screen.getByRole('button',{name:'Print / PDF'})).toBeEnabled());fireEvent.change(screen.getByLabelText('Search invoices and tax'),{target:{value:'INV-1'}});expect(screen.getByRole('button',{name:'Print / PDF'})).toBeDisabled();fireEvent.click(screen.getByRole('button',{name:'Apply'}));await waitFor(()=>expect(vi.mocked(productFieldRequest).mock.calls.some(call=>(call[3] as {parameters?:{search?:string}})?.parameters?.search==='INV-1')).toBe(true));});
it('keeps tax print and source refresh behind their permissions',async()=>{permissions=['report.read'];mount();await screen.findByRole('region',{name:'Invoice Tax Register rows'});expect(screen.queryByRole('button',{name:'Print / PDF'})).not.toBeInTheDocument();expect(screen.queryByRole('button',{name:'Refresh tax data'})).not.toBeInTheDocument();});

it('offers separate credit position and period event views with an as-of calendar',async()=>{code='INVOICE_CREDIT_REGISTER';mount();await waitFor(()=>expect(screen.getByRole('button',{name:'Print / PDF'})).toBeEnabled());expect(screen.getByLabelText('As of')).toHaveAttribute('type','date');expect(screen.getByRole('option',{name:'Closing positions'})).toBeInTheDocument();fireEvent.change(screen.getByLabelText('Report view'),{target:{value:'events'}});expect(screen.getByRole('button',{name:'Print / PDF'})).toBeDisabled();fireEvent.click(screen.getByRole('button',{name:'Apply'}));await waitFor(()=>expect(screen.getByRole('region',{name:'Input Tax Credit Register totals'})).toHaveTextContent('Period events'));});

it('shows bridge ledger movement, verification and an accessible ledger filter',async()=>{code='TAX_GL_BRIDGE';mount();await waitFor(()=>expect(screen.getByRole('button',{name:'Print / PDF'})).toBeEnabled());expect(screen.getByRole('heading',{name:'Tax to Ledger Reconciliation'})).toBeVisible();expect(screen.getByRole('region',{name:'Tax to Ledger Reconciliation totals'})).toHaveTextContent('-20.00');expect(screen.getByRole('region',{name:'Tax to Ledger Reconciliation totals'})).toHaveTextContent('Verified');expect(screen.getByRole('columnheader',{name:'Tax ledger'})).toBeVisible();expect(screen.getByRole('combobox',{name:'Tax ledger'})).toBeVisible();expect(screen.getByLabelText('Tax posting purpose')).toBeVisible();});
it('keeps populated tax row details in the kebab drawer',async()=>{code='TAX_GL_BRIDGE';detail=true;mount();await screen.findByRole('button',{name:'Actions for INV-1'});fireEvent.click(screen.getByRole('button',{name:'Actions for INV-1'}));fireEvent.click(screen.getByRole('menuitem',{name:'View retained row detail'}));const dialog=await screen.findByRole('dialog',{name:'View retained row detail'});await within(dialog).findByText('Output IGST');expect(screen.getByRole('region',{name:'Tax to Ledger Reconciliation rows'}).querySelector('tbody dl')).toBeNull();});

it('labels currency totals as current period when comparative rows are present',()=>{render(<DisplayConfigProvider config={DEFAULT_DISPLAY_CONFIG}><TaxReportTotals title="Tax comparison" summary={{code:'TAX_GL_BRIDGE',comparison_present:true,row_count:2,invoice_count:1,component_count:0,ledger_count:1,verification:'VERIFIED_SOURCE_LINEAGE',amounts:{INR:{debit:'0',credit:'20',net:'-20'}}}}/></DisplayConfigProvider>);expect(screen.getByRole('region',{name:'Tax comparison totals'})).toHaveTextContent('Current period amounts by currency');expect(screen.getByRole('region',{name:'Tax comparison totals'})).toHaveTextContent('-20.00');});

it('points an unprepared tax report to its actual refresh control',async()=>{const normal=vi.mocked(productFieldRequest).getMockImplementation()!;vi.mocked(productFieldRequest).mockImplementation(async(...args)=>args[2].includes('/report-generations?')?{items:[],page:{next_cursor:null}}:normal(...args));mount();const notice=await screen.findByText(/There is no prepared .*snapshot\./);expect(notice).toHaveTextContent('Select Refresh tax data');});

it('retains applied filters and view when the same fiscal year context is refreshed',async()=>{
 const year={id:identity,code:'FY2026-2027',startDate:'2026-04-01',endDate:'2027-03-31',current:true,open:true};const mounted=mount(year);
 await waitFor(()=>expect(screen.getByRole('button',{name:'Print / PDF'})).toBeEnabled());fireEvent.change(screen.getByLabelText('Report view'),{target:{value:'full'}});fireEvent.change(screen.getByLabelText('From date'),{target:{value:'2026-04-10'}});fireEvent.click(screen.getByRole('button',{name:'Apply'}));await waitFor(()=>expect(screen.getByRole('button',{name:'Print / PDF'})).toBeEnabled());
 mounted.rerender(<DisplayConfigProvider config={DEFAULT_DISPLAY_CONFIG}><TaxReportWorkspace report={code as TaxReportCode} company={company} companyName="Example Traders" actor="actor" permissions={permissions} year={{...year}}/></DisplayConfigProvider>);
 await waitFor(()=>expect(screen.getByRole('button',{name:'Apply'})).toBeEnabled());expect(screen.getByLabelText('From date')).toHaveValue('2026-04-10');expect(screen.getByLabelText('Report view')).toHaveValue('full');expect(screen.getByRole('button',{name:'Print / PDF'})).toBeEnabled();
});

it('waits for a selected tax ledger to be verified before allowing Apply',async()=>{
 code='TAX_GL_BRIDGE';const ledger='01990000-0000-7000-8000-000000000007';
 const normal=vi.mocked(productFieldRequest).getMockImplementation()!;let release!:(value:Record<string,string>)=>void;const pending=new Promise<Record<string,string>>(resolve=>{release=resolve;});
 vi.mocked(productFieldRequest).mockImplementation(async(...args)=>{
  if(args[0]==='accounting'&&args[2].includes('/accounts?'))return {items:[{id:ledger,company_id:company,name:'Tax ledger entry'}],page:{next_cursor:null}};
  if(args[0]==='accounting'&&args[2].endsWith('/accounts/'+ledger))return pending;
  return normal(...args);
 });
 mount();await waitFor(()=>expect(screen.getByRole('button',{name:'Apply'})).toBeEnabled());fireEvent.focus(screen.getByRole('combobox',{name:'Tax ledger'}));fireEvent.click(await screen.findByRole('option',{name:'Tax ledger entry'}));
 expect(screen.getByRole('button',{name:'Apply'})).toBeDisabled();await act(async()=>{release({id:ledger,company_id:company,name:'Tax ledger entry'});});await waitFor(()=>expect(screen.getByRole('button',{name:'Apply'})).toBeEnabled());
});

it('restores the credit event view and optional columns after journal navigation',async()=>{
 code='INVOICE_CREDIT_REGISTER';detail=true;
 const normal=vi.mocked(productFieldRequest).getMockImplementation()!,childId='01990000-0000-7000-8000-000000000005';
 vi.mocked(productFieldRequest).mockImplementation(async(...args)=>{
  const path=args[2];
  if(path.endsWith('/drilldowns'))return {...job(),id:childId,code:'DAY_BOOK',title:'Journal entries',view:'default',origin:{parent_id:identity},views:[{key:'default',title:'Journal',columns:[{key:'account_name',title:'Account',kind:'TEXT'}]}]};
  if(path.includes('/report-runs/'+childId+'/rows?'))return {items:[{ordinal:1,data:{account_name:'Journal ledger'},drilldowns:[]}],page:{next_cursor:null}};
  return normal(...args);
 });
 mount();await waitFor(()=>expect(screen.getByRole('button',{name:'Print / PDF'})).toBeEnabled());
 fireEvent.change(screen.getByLabelText('Report view'),{target:{value:'events_detail'}});fireEvent.click(screen.getByRole('button',{name:'Apply'}));
 await waitFor(()=>expect(screen.getByRole('button',{name:'Print / PDF'})).toBeEnabled());
 fireEvent.click(screen.getByRole('button',{name:'Columns'}));fireEvent.click(screen.getByRole('menuitemcheckbox',{name:'Invoice reference'}));fireEvent.keyDown(screen.getByRole('menu'),{key:'Escape'});
 fireEvent.click(screen.getByRole('button',{name:'Actions for INV-1'}));fireEvent.click(screen.getByRole('menuitem',{name:'View journal entries'}));await screen.findByText('Journal ledger');
 expect(screen.getByLabelText('Report view')).toHaveValue('events_detail');expect(screen.queryByText('Filters changed. Select Apply to update this report.')).not.toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'Back to Input Tax Credit Register'}));await screen.findByText('Customer');
 expect(screen.getByLabelText('Report view')).toHaveValue('events_detail');expect(screen.getByRole('columnheader',{name:'Invoice reference'})).toBeVisible();
});

it('restores saved source-view columns after switching to the business view',async()=>{
 mount();await waitFor(()=>expect(screen.getByRole('button',{name:'Print / PDF'})).toBeEnabled());
 fireEvent.change(screen.getByLabelText('Report view'),{target:{value:'full'}});fireEvent.click(screen.getByRole('button',{name:'Apply'}));
 await waitFor(()=>expect(screen.getByRole('button',{name:'Print / PDF'})).toBeEnabled());
 fireEvent.click(screen.getByRole('button',{name:'Columns'}));fireEvent.click(screen.getByRole('menuitemcheckbox',{name:'Invoice reference'}));fireEvent.click(screen.getByRole('menuitemcheckbox',{name:'tax code'}));fireEvent.keyDown(screen.getByRole('menu'),{key:'Escape'});
 fireEvent.click(screen.getByRole('button',{name:'Saved views'}));fireEvent.change(screen.getByLabelText('New view name'),{target:{value:'Invoice evidence'}});fireEvent.click(screen.getByRole('button',{name:'Save current view'}));fireEvent.click(screen.getByRole('button',{name:'Done'}));
 fireEvent.change(screen.getByLabelText('Report view'),{target:{value:'default'}});fireEvent.click(screen.getByRole('button',{name:'Apply'}));
 await waitFor(()=>expect(screen.getByRole('button',{name:'Print / PDF'})).toBeEnabled());expect(screen.queryByRole('columnheader',{name:'Invoice reference'})).not.toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'Saved views'}));const option=screen.getByRole('option',{name:'Invoice evidence'}) as HTMLOptionElement;fireEvent.change(screen.getByLabelText('Choose saved view'),{target:{value:option.value}});
 await waitFor(()=>expect(screen.getByRole('button',{name:'Print / PDF'})).toBeEnabled());expect(screen.getByLabelText('Report view')).toHaveValue('full');expect(screen.getByRole('columnheader',{name:'Invoice reference'})).toBeVisible();expect(screen.queryByRole('columnheader',{name:'tax code'})).not.toBeInTheDocument();
});

it('identifies comparative credit-event amounts as current-period totals',()=>{
 const summary:TaxSummary={code:'INVOICE_CREDIT_REGISTER',mode:'EVENTS',comparison_present:true,row_count:2,invoice_count:1,component_count:0,event_count:1,verification:'VERIFIED_SOURCE_LINEAGE',amounts:{},event_amounts:{INR:{VERIFY:'20'}}};
 render(<DisplayConfigProvider config={DEFAULT_DISPLAY_CONFIG}><TaxReportTotals title="Credit comparison" summary={summary}/></DisplayConfigProvider>);
 expect(screen.getByRole('table',{name:'Current period events by action and currency'})).toBeVisible();
});

it('keeps retained tax columns intact until the selected view succeeds',async()=>{
 mount();await waitFor(()=>expect(screen.getByRole('button',{name:'Print / PDF'})).toBeEnabled());
 fireEvent.change(screen.getByLabelText('Report view'),{target:{value:'full'}});fireEvent.click(screen.getByRole('button',{name:'Apply'}));await waitFor(()=>expect(screen.getByRole('button',{name:'Print / PDF'})).toBeEnabled());
 const headers=()=>within(screen.getByRole('region',{name:'Invoice Tax Register rows'})).getAllByRole('columnheader').map(header=>header.textContent);
 const retained=headers();expect(retained).not.toContain('Invoice reference');
 fireEvent.change(screen.getByLabelText('Report view'),{target:{value:'default'}});expect(headers()).toEqual(retained);expect(screen.getByRole('button',{name:'Print / PDF'})).toBeDisabled();
 const normal=vi.mocked(productFieldRequest).getMockImplementation()!;vi.mocked(productFieldRequest).mockImplementation(async(...args)=>{if(args[1]==='POST'&&args[2].endsWith('/report-runs'))throw new Error('Report service unavailable');return normal(...args);});
 fireEvent.click(screen.getByRole('button',{name:'Apply'}));await screen.findByText('Report service unavailable');expect(headers()).toEqual(retained);
});

it('saves the selected tax view defaults when the new view has not yet been applied',async()=>{
 mount();await waitFor(()=>expect(screen.getByRole('button',{name:'Print / PDF'})).toBeEnabled());
 fireEvent.click(screen.getByRole('button',{name:'Columns'}));fireEvent.click(screen.getByRole('menuitemcheckbox',{name:'tax code'}));fireEvent.keyDown(screen.getByRole('menu'),{key:'Escape'});
 fireEvent.change(screen.getByLabelText('Report view'),{target:{value:'full'}});fireEvent.click(screen.getByRole('button',{name:'Saved views'}));fireEvent.change(screen.getByLabelText('New view name'),{target:{value:'Unapplied source view'}});fireEvent.click(screen.getByRole('button',{name:'Save current view'}));fireEvent.click(screen.getByRole('button',{name:'Done'}));
 fireEvent.change(screen.getByLabelText('Report view'),{target:{value:'default'}});fireEvent.click(screen.getByRole('button',{name:'Apply'}));await waitFor(()=>expect(screen.getByRole('button',{name:'Print / PDF'})).toBeEnabled());
 fireEvent.click(screen.getByRole('button',{name:'Saved views'}));const option=screen.getByRole('option',{name:'Unapplied source view'}) as HTMLOptionElement;fireEvent.change(screen.getByLabelText('Choose saved view'),{target:{value:option.value}});
 await waitFor(()=>expect(screen.getByRole('button',{name:'Print / PDF'})).toBeEnabled());expect(screen.getByLabelText('Report view')).toHaveValue('full');expect(screen.getByRole('region',{name:'Invoice Tax Register rows'})).toContainElement(screen.getByRole('columnheader',{name:'tax code'}));
});

it('preserves tax acronyms in ledger purposes and credit-event headings',async()=>{
 code='TAX_GL_BRIDGE';const normal=vi.mocked(productFieldRequest).getMockImplementation()!;
 vi.mocked(productFieldRequest).mockImplementation(async(...args)=>args[2].includes('/rows?')?{items:[{...resultRow(),data:{...resultRow().data,account_name:'Tax payable',tax_purpose:'OUTPUT_IGST'}}],page:{next_cursor:null}}:normal(...args));
 mount();await waitFor(()=>expect(screen.getByRole('button',{name:'Print / PDF'})).toBeEnabled());fireEvent.change(screen.getByLabelText('Report view'),{target:{value:'full'}});fireEvent.click(screen.getByRole('button',{name:'Apply'}));await waitFor(()=>expect(screen.getByRole('button',{name:'Print / PDF'})).toBeEnabled());
 expect(screen.getByRole('cell',{name:'Output IGST'})).toBeVisible();
 const summary:TaxSummary={code:'INVOICE_CREDIT_REGISTER',mode:'EVENTS',row_count:1,invoice_count:1,component_count:0,event_count:1,verification:'VERIFIED_SOURCE_LINEAGE',amounts:{},event_amounts:{INR:{RCM_DISCHARGE:'20'}}};
 render(<DisplayConfigProvider config={DEFAULT_DISPLAY_CONFIG}><TaxReportTotals title="RCM events" summary={summary}/></DisplayConfigProvider>);
 expect(screen.getByRole('columnheader',{name:'RCM discharge'})).toBeVisible();
});
