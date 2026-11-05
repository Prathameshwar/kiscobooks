import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { DEFAULT_DISPLAY_CONFIG, DisplayConfigProvider } from '@janso/ui';
import { StockSummaryWorkspace } from '../app/components/StockSummaryWorkspace';
import { productFieldRequest } from '../app/lib/product-fields';

vi.mock('../app/lib/product-fields', () => ({ productFieldRequest: vi.fn() }));
const company='01990000-0000-7000-8000-000000000001';
const generation='01990000-0000-7000-8000-000000000002';
const runId='01990000-0000-7000-8000-000000000003';
const columns=[{key:'item_code',title:'Item code',kind:'TEXT'},{key:'item_name',title:'Item name',kind:'TEXT'},{key:'owner',title:'Owner',kind:'TEXT'},{key:'currency',title:'Currency',kind:'TEXT'},{key:'eligible',title:'Eligible',kind:'DECIMAL'},{key:'reserved',title:'Reserved',kind:'DECIMAL'},{key:'unit',title:'Unit',kind:'TEXT'},{key:'quantity',title:'Quantity',kind:'DECIMAL'}];
const coverage={as_of:'2026-10-31',history_start:'2026-04-01',currency:'INR',complete_company:true,reservations_complete:false,valuation_complete:true};
const definition={definition:{code:'STOCK_SUMMARY',version:3,title:'Stock Summary',views:[{key:'default',title:'Stock Summary',columns}]},parameter_schema:{required:['as_of'],properties:{as_of:{type:'string',format:'date'},search:{type:'string',default:''},location_id:{anyOf:[{type:'string',format:'uuid'},{type:'null'}]},group_id:{anyOf:[{type:'string',format:'uuid'},{type:'null'}]},include_zero:{type:'boolean',default:true},include_inactive:{type:'boolean',default:true}}},run_enabled:true,export_limits:['PDF','CSV','XLSX'].map(format=>({format,max_rows:1000,max_cells:10000})),package_limits:{max_rows:5000,max_parts:10}};
const summary={item_count:2,row_count:3,currency:'INR',owned_value:'720.0000',unavailable_availability_rows:3,unavailable_value_rows:0,quantities:[{unit:'PCS',owner:'OWN',custody:'LOCAL',opening:'100',inward:'0',outward:'30',quantity:'70',eligible:'60',available:null},{unit:'KG',owner:'OWN',custody:'LOCAL',opening:'2',inward:'0',outward:'0',quantity:'2',eligible:'2',available:null}]};
const job={id:runId,generation_id:generation,code:'STOCK_SUMMARY',version:3,kind:'RUN',status:'COMPLETE',origin:null,parameters:{as_of:coverage.as_of},view:'default',views:definition.definition.views,completed_rows:3,result:{evidence:{inventory_coverage:coverage,stock_summary:summary}},title:'Stock Summary'};

beforeEach(()=>{
  localStorage.clear();vi.mocked(productFieldRequest).mockReset();
  vi.mocked(productFieldRequest).mockImplementation(async (_service,method,path,body)=>{
    if(path.includes('/report-definitions/'))return definition;
    if(path.includes('/report-generations?'))return {items:[{id:generation,status:'READY'}],page:{next_cursor:null}};
    if(path.endsWith('/report-generations/'+generation))return {id:generation,status:'READY',manifest:{control:{coverage_start:coverage.history_start,counts:{inventory_report_record:6}}}};
    if(path.includes('/inventory?'))return {generation_id:generation,coverage,items:[],next_cursor:null};
    if(path.endsWith('/report-runs')&&method==='POST')return {...job,parameters:(body as {parameters:object}).parameters};
    if(path.includes('/rows?'))return {items:[{ordinal:1,data:{item_code:'Copper',item_name:'Copper',unit:'PCS',quantity:'70'},drilldowns:[]}],page:{next_cursor:null}};
    if(path.includes('/report-runs?code=STOCK_SUMMARY'))return {items:[],page:{next_cursor:null}};
    if(path.endsWith('/report-generations')&&method==='POST')return {id:generation,status:'READY'};
    throw new Error('Unexpected '+method+' '+path);
  });
});
function mount(permissions=['report.read','report.export','report.definition.manage']){
  return render(<DisplayConfigProvider config={DEFAULT_DISPLAY_CONFIG}><StockSummaryWorkspace company={company} companyName="Example Traders" actor="actor-1" permissions={permissions}/></DisplayConfigProvider>);
}

it('uses the verified snapshot date and shows full-result totals separated by unit',async()=>{
  mount();await screen.findByText('Copper');
  expect(screen.getByRole('heading',{name:'Stock Summary'})).toBeVisible();
  expect(screen.getByLabelText('As of')).toHaveValue(coverage.as_of);
  expect(screen.getByLabelText('As of')).toHaveAttribute('type','date');
  expect(screen.getByRole('button',{name:'Refresh'}).parentElement).toBe(screen.getByRole('button',{name:'Print / PDF'}).parentElement);
  expect(screen.getByRole('button',{name:'Refresh stock data'}).parentElement).toBe(screen.getByRole('button',{name:'Print / PDF'}).parentElement);
  expect(screen.getByText('Owned stock value')).toBeVisible();
  expect(screen.getByRole('region',{name:'Quantity totals by unit'})).toHaveTextContent('PCS');
  expect(screen.getByRole('region',{name:'Quantity totals by unit'})).toHaveTextContent('KG');
  await waitFor(()=>expect(screen.getByRole('button',{name:'Print / PDF'})).toBeEnabled());
  expect(productFieldRequest).toHaveBeenCalledWith('reports','POST',expect.stringContaining('/report-runs'),expect.objectContaining({code:'STOCK_SUMMARY',version:3,parameters:expect.objectContaining({as_of:coverage.as_of})}),expect.any(String),expect.any(AbortSignal));
});

it('explains a verified empty stock selection without calling it a transaction list',async()=>{
  const normal=vi.mocked(productFieldRequest).getMockImplementation()!;
  vi.mocked(productFieldRequest).mockImplementation(async (...args)=>{
    if(args[2].includes('/rows?'))return {items:[],page:{next_cursor:null}};
    if(args[2].endsWith('/report-runs')&&args[1]==='POST')return {...job,completed_rows:0,result:{evidence:{inventory_coverage:coverage,stock_summary:{...summary,item_count:0,row_count:0,owned_value:'0.0000',quantities:[]}}}};
    return normal(...args);
  });
  mount();
  expect(await screen.findByRole('heading',{name:'No matching stock records'})).toBeVisible();
  expect(screen.getByText('No stock items match the applied filters.')).toBeVisible();
  expect(screen.queryByText('No transactions found')).not.toBeInTheDocument();
});

it('keeps applied results and blocks export while search is unapplied',async()=>{
  mount();await screen.findByText('Copper');
  fireEvent.change(screen.getByLabelText('Search items'),{target:{value:'wire'}});
  expect(screen.getByText('Copper')).toBeVisible();
  expect(screen.getByRole('button',{name:'Print / PDF'})).toBeDisabled();
  fireEvent.click(screen.getByRole('button',{name:'Apply'}));
  await waitFor(()=>expect(vi.mocked(productFieldRequest).mock.calls.findLast(call=>call[1]==='POST')?.[3]).toMatchObject({parameters:{search:'wire'}}));
});

it('allows a saved stock view to be selected again after its filters are changed',async()=>{
  mount();await screen.findByText('Copper');
  fireEvent.change(screen.getByLabelText('Search items'),{target:{value:'wire'}});
  fireEvent.click(screen.getByRole('button',{name:'Saved views'}));
  fireEvent.change(screen.getByLabelText('New view name'),{target:{value:'Wire stock'}});
  fireEvent.click(screen.getByRole('button',{name:'Save current view'}));
  fireEvent.click(within(screen.getByRole('dialog',{name:'Saved views'})).getByRole('button',{name:'Done'}));
  fireEvent.change(screen.getByLabelText('Search items'),{target:{value:''}});
  fireEvent.click(screen.getByRole('button',{name:'Saved views'}));
  expect(screen.getByLabelText('Choose saved view')).toHaveValue('');
  const identity=Array.from(screen.getByLabelText('Choose saved view').querySelectorAll('option')).find(option=>option.textContent==='Wire stock')!.value;
  fireEvent.change(screen.getByLabelText('Choose saved view'),{target:{value:identity}});
  expect(screen.getByLabelText('Search items')).toHaveValue('wire');
  expect(screen.queryByRole('dialog',{name:'Saved views'})).not.toBeInTheDocument();
});

it('refreshes a complete source with FRESH and opens Stock Summary-only history',async()=>{
  mount();await screen.findByText('Copper');
  fireEvent.click(screen.getByRole('button',{name:'Refresh stock data'}));
  await waitFor(()=>expect(productFieldRequest).toHaveBeenCalledWith('reports','POST',expect.stringContaining('/report-generations'),{strategy:'FRESH'},expect.any(String),expect.any(AbortSignal)));
  await waitFor(()=>expect(screen.getByRole('button',{name:'Stock Summary history'})).toBeEnabled());
  fireEvent.click(screen.getByRole('button',{name:'Stock Summary history'}));
  expect(await screen.findByText('No previous Stock Summary reports.')).toBeVisible();
  expect(productFieldRequest).toHaveBeenCalledWith('reports','GET',expect.stringContaining('code=STOCK_SUMMARY'),undefined,undefined,expect.any(AbortSignal));
});

it('hides export and stock refresh without their respective permissions',async()=>{
  mount(['report.read']);await screen.findByText('Copper');
  expect(screen.queryByRole('button',{name:'Print / PDF'})).not.toBeInTheDocument();
  expect(screen.queryByRole('button',{name:'Refresh stock data'})).not.toBeInTheDocument();
});

it('waits for a pending source to become ready before preparing fresh results',async()=>{
  mount();await screen.findByText('Copper');
  const normal=vi.mocked(productFieldRequest).getMockImplementation()!;
  let sourceReads=0;
  vi.mocked(productFieldRequest).mockImplementation(async (...args)=>{
    const [,method,path]=args;
    if(path.endsWith('/report-generations')&&method==='POST')return {id:generation,status:'PENDING'};
    if(path.endsWith('/report-generations/'+generation)&&sourceReads++===0)return {id:generation,status:'RUNNING'};
    return normal(...args);
  });
  const initialRuns=vi.mocked(productFieldRequest).mock.calls.filter(call=>call[1]==='POST'&&call[2].endsWith('/report-runs')).length;
  fireEvent.click(screen.getByRole('button',{name:'Refresh stock data'}));
  expect(screen.getByRole('button',{name:'Print / PDF'})).toBeDisabled();
  expect(screen.getByText('Copper')).toBeVisible();
  await waitFor(()=>expect(screen.getByRole('button',{name:'Print / PDF'})).toBeEnabled(),{timeout:5000});
  expect(sourceReads).toBeGreaterThanOrEqual(2);
  expect(vi.mocked(productFieldRequest).mock.calls.filter(call=>call[1]==='POST'&&call[2].endsWith('/report-runs'))).toHaveLength(initialRuns+1);
});

it('keeps row actions in a kebab menu and opens details outside the table',async()=>{
  const normal=vi.mocked(productFieldRequest).getMockImplementation()!;
  const data={item_code:'Copper',item_name:'Copper wire',unit:'PCS',quantity:'70'};
  vi.mocked(productFieldRequest).mockImplementation(async (...args)=>{
    const path=args[2];
    if(path.includes('/rows?'))return {items:[{ordinal:1,data,drilldowns:[{key:'stock_item_locations',title:'Warehouse breakdown',method:'POST',token:'warehouse-token'},{key:'frozen_row',title:'Stock details',method:'GET',token:'detail-token'}]}],page:{next_cursor:null}};
    if(path.includes('/rows/1?token=detail-token'))return {ordinal:1,data,drilldowns:[]};
    return normal(...args);
  });
  mount();await screen.findByText('Copper wire');
  expect(screen.queryByRole('menuitem',{name:'Stock details'})).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'Actions for Copper wire'}));
  expect(screen.getByRole('menuitem',{name:'Warehouse breakdown'})).toBeVisible();
  fireEvent.click(screen.getByRole('menuitem',{name:'Stock details'}));
  expect(await screen.findByRole('dialog',{name:'Stock details'})).toHaveTextContent('Copper wire');
  expect(screen.getByRole('region',{name:'Stock Summary rows'}).querySelectorAll('tbody tr')).toHaveLength(1);
  expect(screen.queryByRole('button',{name:'Hide detail'})).not.toBeInTheDocument();
});

it('formats stock detail dates, values and ownership using the company configuration',async()=>{
  const normal=vi.mocked(productFieldRequest).getMockImplementation()!;
  const detailColumns=[...columns,{key:'carrying_value',title:'Carrying value',kind:'MONEY'},{key:'as_of',title:'As of',kind:'DATE'},{key:'custody',title:'Custody',kind:'TEXT'}];
  const detailViews=[{key:'default',title:'Stock Summary',columns:detailColumns}];
  const data={item_name:'Copper',quantity:'70.0000',carrying_value:'12.5000',as_of:coverage.as_of,owner:'OWN',custody:'LOCAL'};
  vi.mocked(productFieldRequest).mockImplementation(async (...args)=>{
    const [,method,path]=args;
    if(path.includes('/report-definitions/'))return {...definition,definition:{...definition.definition,views:detailViews}};
    if(path.endsWith('/report-runs')&&method==='POST')return {...job,views:detailViews};
    if(path.includes('/rows?'))return {items:[{ordinal:1,data,drilldowns:[{key:'frozen_row',title:'Stock details',method:'GET',token:'detail-token'}]}],page:{next_cursor:null}};
    if(path.includes('/rows/1?token=detail-token'))return {ordinal:1,data,drilldowns:[]};
    return normal(...args);
  });
  render(<DisplayConfigProvider config={{...DEFAULT_DISPLAY_CONFIG,dateFormat:'dd/MM/yyyy',amountPrecision:2,quantityPrecision:3}}><StockSummaryWorkspace company={company} companyName="Example Traders" actor="actor-1" permissions={['report.read','report.export']}/></DisplayConfigProvider>);
  await screen.findByText('Copper');
  fireEvent.click(screen.getByRole('button',{name:'Actions for Copper'}));
  fireEvent.click(screen.getByRole('menuitem',{name:'Stock details'}));
  const drawer=await screen.findByRole('dialog',{name:'Stock details'});
  await waitFor(()=>expect(drawer).toHaveTextContent('31/10/2026'));
  expect(within(drawer).getByText('12.50',{exact:true})).toBeVisible();
  expect(within(drawer).getByText('70.000',{exact:true})).toBeVisible();
  expect(drawer).toHaveTextContent('Closing stock');
  expect(drawer).toHaveTextContent('Stock value');
  expect(drawer).toHaveTextContent('Company owned');
  expect(drawer).toHaveTextContent('In warehouse');
});

it('starts with essential stock columns and lets the user select optional columns',async()=>{
  mount();await screen.findByText('Copper');
  const table=within(screen.getByRole('region',{name:'Stock Summary rows'}));
  expect(table.getByRole('columnheader',{name:'Item name'})).toBeVisible();
  expect(table.getByRole('columnheader',{name:'Closing stock'})).toBeVisible();
  for(const name of ['Item code','Owner','Currency','Reserved','Eligible'])expect(table.queryByRole('columnheader',{name})).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'Columns'}));
  fireEvent.click(screen.getByRole('menuitemcheckbox',{name:'Item code'}));
  expect(table.getByRole('columnheader',{name:'Item code'})).toBeVisible();
  fireEvent.click(screen.getByRole('menuitemcheckbox',{name:'Item code'}));
  expect(table.queryByRole('columnheader',{name:'Item code'})).not.toBeInTheDocument();
});

it('retains results and prevents running an unsupported calendar date',async()=>{
  mount();await screen.findByText('Copper');
  fireEvent.change(screen.getByLabelText('As of'),{target:{value:'2026-10-01'}});
  expect(screen.getByText(/No verified snapshot for this date/)).toBeVisible();
  expect(screen.getByRole('button',{name:'Apply'})).toBeDisabled();
  expect(screen.getByRole('button',{name:'Print / PDF'})).toBeDisabled();
  expect(screen.getByText('Copper')).toBeVisible();
  fireEvent.change(screen.getByLabelText('As of'),{target:{value:coverage.as_of}});
  expect(screen.getByRole('button',{name:'Apply'})).toBeEnabled();
});

it('ends a quarantined stock refresh and leaves the previous report available',async()=>{
  mount();await screen.findByText('Copper');
  const normal=vi.mocked(productFieldRequest).getMockImplementation()!;
  vi.mocked(productFieldRequest).mockImplementation(async (...args)=>args[1]==='POST'&&args[2].endsWith('/report-generations')?{id:generation,status:'QUARANTINED',failure_code:'SOURCE_VERIFICATION_FAILED'}:normal(...args));
  fireEvent.click(screen.getByRole('button',{name:'Refresh stock data'}));
  await waitFor(()=>expect(screen.getByRole('button',{name:'Refresh stock data'})).toBeEnabled(),{timeout:2500});
  expect(screen.getByText(/inventory snapshot could not be prepared/)).toBeVisible();
  expect(screen.getByText('Copper')).toBeVisible();
});

it('refreshes the latest usable stock cut when a newer financial snapshot has no inventory',async()=>{
  mount();await screen.findByText('Copper');
  const normal=vi.mocked(productFieldRequest).getMockImplementation()!;
  const incomplete='01990000-0000-7000-8000-000000000004';
  vi.mocked(productFieldRequest).mockImplementation(async (...args)=>{
    if(args[2].includes('/report-generations?'))return {items:[{id:incomplete,status:'READY'},{id:generation,status:'READY'}],page:{next_cursor:null}};
    if(args[2].endsWith('/report-generations/'+incomplete))return {id:incomplete,status:'READY',manifest:{control:{counts:{inventory_report_record:0}}}};
    return normal(...args);
  });
  const initial=vi.mocked(productFieldRequest).mock.calls.filter(call=>call[1]==='POST'&&call[2].endsWith('/report-runs')).length;
  fireEvent.click(screen.getByRole('button',{name:'Refresh'}));
  await waitFor(()=>expect(screen.getByRole('button',{name:'Refresh'})).toBeEnabled());
  expect(vi.mocked(productFieldRequest).mock.calls.filter(call=>call[1]==='POST'&&call[2].endsWith('/report-runs'))).toHaveLength(initial+1);
  expect(screen.getByRole('button',{name:'Print / PDF'})).toBeEnabled();
  expect(screen.getByLabelText('As of')).toHaveValue(coverage.as_of);
});

it('restores the stock page and optional columns after a warehouse drill-down',async()=>{
  const normal=vi.mocked(productFieldRequest).getMockImplementation()!;
  const childId='01990000-0000-7000-8000-000000000005';
  const child={...job,id:childId,code:'LOCATION_STOCK',title:'Warehouse stock',origin:{parent_id:runId},views:[{key:'default',title:'Warehouses',columns:[{key:'location_name',title:'Warehouse',kind:'TEXT'}]}]};
  vi.mocked(productFieldRequest).mockImplementation(async (...args)=>{
    const path=args[2];
    if(path.endsWith('/drilldowns'))return child;
    if(path.endsWith('/report-runs/'+runId))return job;
    if(path.includes('/report-runs/'+childId+'/rows?'))return {items:[{ordinal:1,data:{location_name:'Main warehouse'},drilldowns:[]}],page:{next_cursor:null}};
    if(path.includes('/rows?'))return {items:[{ordinal:path.includes('cursor=second')?51:1,data:{item_code:'CU-02',item_name:path.includes('cursor=second')?'Copper page two':'Copper',unit:'PCS',quantity:'70'},drilldowns:[{key:'stock_item_locations',title:'Warehouse breakdown',method:'POST',token:'warehouse-token'}]}],page:{next_cursor:path.includes('cursor=second')?null:'second'}};
    return normal(...args);
  });
  mount();await screen.findByText('Copper');
  fireEvent.click(screen.getByRole('button',{name:'Columns'}));
  fireEvent.click(screen.getByRole('menuitemcheckbox',{name:'Item code'}));
  fireEvent.keyDown(screen.getByRole('menu'),{key:'Escape'});
  fireEvent.click(screen.getByRole('button',{name:'Next'}));
  await screen.findByText('Copper page two');
  fireEvent.click(screen.getByRole('button',{name:'Actions for Copper page two'}));
  fireEvent.click(screen.getByRole('menuitem',{name:'Warehouse breakdown'}));
  await screen.findByText('Main warehouse');
  expect(screen.queryByText('Filters changed. Select Apply to update this report.')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'Back to Stock Summary'}));
  await screen.findByText('Copper page two');
  expect(within(screen.getByRole('region',{name:'Stock Summary rows'})).getByRole('columnheader',{name:'Item code'})).toBeVisible();
  expect(screen.getByRole('button',{name:'Previous'})).toBeEnabled();
});

it('keeps the selected Stock Summary view when applying filters from a warehouse drill-down',async()=>{
  const normal=vi.mocked(productFieldRequest).getMockImplementation()!;
  const childId='01990000-0000-7000-8000-000000000005';
  const views=[...definition.definition.views,{key:'provenance',title:'Source details',columns}];
  const child={...job,id:childId,code:'LOCATION_STOCK',title:'Warehouse stock',origin:{parent_id:runId},view:'default',views:[{key:'default',title:'Warehouses',columns:[{key:'location_name',title:'Warehouse',kind:'TEXT'}]}]};
  vi.mocked(productFieldRequest).mockImplementation(async (...args)=>{
    const [,method,path,body]=args;
    if(path.includes('/report-definitions/'))return {...definition,definition:{...definition.definition,views}};
    if(path.endsWith('/report-runs')&&method==='POST')return {...job,views,view:(body as {view:string}).view};
    if(path.endsWith('/drilldowns'))return child;
    if(path.includes('/report-runs/'+childId+'/rows?'))return {items:[{ordinal:1,data:{location_name:'Main warehouse'},drilldowns:[]}],page:{next_cursor:null}};
    if(path.includes('/rows?'))return {items:[{ordinal:1,data:{item_name:'Copper',unit:'PCS',quantity:'70'},drilldowns:[{key:'stock_item_locations',title:'Warehouse breakdown',method:'POST',token:'warehouse-token'}]}],page:{next_cursor:null}};
    return normal(...args);
  });
  mount();await screen.findByText('Copper');
  fireEvent.change(screen.getByLabelText('Report view'),{target:{value:'provenance'}});
  fireEvent.click(screen.getByRole('button',{name:'Apply'}));
  await waitFor(()=>expect(screen.getByRole('button',{name:'Print / PDF'})).toBeEnabled());
  fireEvent.click(screen.getByRole('button',{name:'Actions for Copper'}));
  fireEvent.click(screen.getByRole('menuitem',{name:'Warehouse breakdown'}));
  await screen.findByText('Main warehouse');
  expect(screen.getByLabelText('Report view')).toHaveValue('provenance');
  expect(screen.queryByText('Filters changed. Select Apply to update this report.')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'Apply'}));
  await screen.findByText('Copper');
  expect(vi.mocked(productFieldRequest).mock.calls.findLast(call=>call[1]==='POST'&&call[2].endsWith('/report-runs'))?.[3]).toMatchObject({code:'STOCK_SUMMARY',view:'provenance'});
});
