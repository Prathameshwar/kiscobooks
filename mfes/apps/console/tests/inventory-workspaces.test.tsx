import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { DEFAULT_DISPLAY_CONFIG, DisplayConfigProvider } from '@janso/ui';
import { InventoryReportWorkspace } from '../app/components/InventoryReportWorkspace';
import { productFieldRequest } from '../app/lib/product-fields';
import { inventoryWorkspaces, type InventoryReportCode } from '../app/lib/inventory-workspace';

vi.mock('../app/lib/product-fields',()=>({productFieldRequest:vi.fn()}));
const company='01990000-0000-7000-8000-000000000001',generation='01990000-0000-7000-8000-000000000002',runId='01990000-0000-7000-8000-000000000003',item='01990000-0000-7000-8000-000000000004';
const coverage={as_of:'2026-10-31',history_start:'2026-04-01',currency:'INR',complete_company:true,reservations_complete:false,valuation_complete:true,movements_complete:true,origins_complete:true};
const ledgerColumns=[{key:'date',title:'Date',kind:'DATE'},{key:'item_name',title:'Item name',kind:'TEXT'},{key:'voucher_number',title:'Voucher number',kind:'TEXT'},{key:'action',title:'Action',kind:'TEXT'},{key:'unit',title:'Unit',kind:'TEXT'},{key:'inward',title:'Inward',kind:'DECIMAL'},{key:'outward',title:'Outward',kind:'DECIMAL'},{key:'balance',title:'Balance',kind:'DECIMAL'},{key:'value_balance',title:'Value balance',kind:'MONEY'},{key:'position_id',title:'Position Id',kind:'IDENTIFIER'}];
const ledgerMetrics={code:'ITEM_LEDGER',row_count:1,item_count:1,entry_count:1,owned_value:'1437.5000',currency:'INR',quantities:[{unit:'PCS',owner:'OWN',custody:'LOCAL',opening:'75.0000',inward:'40.0000',outward:'0.0000',quantity:'115.0000'}]};
let code:InventoryReportCode,definition:Record<string,any>,job:Record<string,any>, resultRows:Record<string,any>[];
beforeEach(()=>{
  localStorage.clear();code='ITEM_LEDGER';
  definition={definition:{code,version:4,title:'Item Stock Ledger',views:[{key:'default',title:'Ledger',columns:ledgerColumns}]},parameter_schema:{required:['as_of','item_id','date_from'],properties:{as_of:{type:'string',format:'date'},date_from:{type:'string',format:'date'},item_id:{type:'string',format:'uuid'},lot_id:{anyOf:[{type:'string',format:'uuid'},{type:'null'}]}}},run_enabled:true,export_limits:['PDF','CSV','XLSX'].map(format=>({format,max_rows:1000,max_cells:10000})),package_limits:{max_rows:5000,max_parts:10}};
  job={id:runId,generation_id:generation,code,version:4,kind:'RUN',status:'COMPLETE',origin:null,parameters:{as_of:coverage.as_of,date_from:coverage.history_start,item_id:item},view:'default',views:definition.definition.views,completed_rows:1,result:{evidence:{inventory_coverage:coverage,inventory_metrics:ledgerMetrics}},title:'Item Stock Ledger'};
  resultRows=[{ordinal:1,data:{item_name:'Copper',date:'2026-10-15',voucher_number:'PUR-001',action:'RECEIPT',unit:'PCS',inward:'40.0000',outward:'0.0000',balance:'115.0000',value_balance:'1437.5000'},drilldowns:[]}];
  vi.mocked(productFieldRequest).mockReset();vi.mocked(productFieldRequest).mockImplementation(async(_service,method,path,body)=>{
    if(path.includes('/report-definitions/'))return definition;
    if(path.includes('/report-generations?'))return {items:[{id:generation,status:'READY'}],page:{next_cursor:null}};
    if(path.endsWith('/report-generations/'+generation))return {id:generation,status:'READY',manifest:{control:{coverage_start:coverage.history_start,counts:{inventory_report_record:6}}}};
    if(path.includes('/inventory?'))return {generation_id:generation,coverage,items:[{id:item,code:'CU-01',name:'Copper'}],next_cursor:null};
    if(path.endsWith('/report-runs')&&method==='POST')return {...job,parameters:(body as {parameters:object}).parameters};
    if(path.includes('/report-runs?'))return {items:[],page:{next_cursor:null}};
    if(path.includes('/rows?'))return {items:resultRows,page:{next_cursor:null}};
    throw new Error('Unexpected '+method+' '+path);
  });
});
function mount(report:InventoryReportCode=code){return render(<DisplayConfigProvider config={{...DEFAULT_DISPLAY_CONFIG,dateFormat:'dd/MM/yyyy',quantityPrecision:3}}><InventoryReportWorkspace report={report} company={company} companyName="Example Traders" actor="actor-1" permissions={['report.read','report.export','report.definition.manage']}/></DisplayConfigProvider>);}
async function selectItem(){fireEvent.click(await screen.findByRole('combobox',{name:'Stock item'}));fireEvent.click(await screen.findByRole('option',{name:/Copper/}));}

function reportFixture(report:InventoryReportCode, extra:Record<string,any>={}) {
  code=report;const config=inventoryWorkspaces[report];
  const columns=config.columns.map(key=>({key,title:key.replaceAll('_',' '),kind:['quantity','opening','inward','outward','eligible','available','projected_available','shortage','suggested_quantity','reorder_level','target_level'].includes(key)?'DECIMAL':key.includes('value')?'MONEY':key.endsWith('date')?'DATE':'TEXT'}));
  definition.definition={...definition.definition,code,title:config.title,views:[{key:'default',title:config.title,columns}]};
  definition.parameter_schema={required:['as_of'],properties:{as_of:{type:'string',format:'date'},search:{type:'string',default:''},...extra}};
  job={...job,code,title:config.title,parameters:{as_of:coverage.as_of},views:definition.definition.views,result:{evidence:{inventory_coverage:coverage,inventory_metrics:{...ledgerMetrics,code,entry_count:undefined,location_count:1}}}};
  resultRows=[{ordinal:1,data:Object.fromEntries(config.columns.map(key=>[key,key==='item_name'?'Copper':key==='unit'?'PCS':key==='location_name'?'Main warehouse':columns.find(c=>c.key===key)?.kind==='DECIMAL'?'115.0000':columns.find(c=>c.key===key)?.kind==='MONEY'?'1437.5000':columns.find(c=>c.key===key)?.kind==='DATE'?'2026-10-15':key.replaceAll('_',' ')])),drilldowns:[]}];
}

it('LOCATION_STOCK uses the inventory workspace, essential columns, calendar and full-result search',async()=>{
  reportFixture('LOCATION_STOCK',{location_id:{anyOf:[{type:'string',format:'uuid'},{type:'null'}]}});mount();
  expect(await screen.findByRole('heading',{name:'Warehouse Stock'})).toBeVisible();
  await waitFor(()=>expect(screen.getByRole('button',{name:'Print / PDF'})).toBeEnabled());
  expect(screen.getByRole('region',{name:'Warehouse Stock rows'})).toHaveTextContent('Main warehouse');
  expect(screen.getByLabelText('As of')).toHaveAttribute('type','date');
  fireEvent.change(screen.getByLabelText('Search items'),{target:{value:'Copper'}});
  expect(screen.getByRole('button',{name:'Print / PDF'})).toBeDisabled();
  fireEvent.click(screen.getByRole('button',{name:'Apply'}));
  await waitFor(()=>expect(vi.mocked(productFieldRequest).mock.calls.some(c=>c[1]==='POST'&&(c[3] as {code?:string;parameters?:{search?:string}})?.code==='LOCATION_STOCK'&&(c[3] as {parameters:{search:string}}).parameters.search==='Copper')).toBe(true));
});

it('STOCK_VALUATION presents recorded costs separately from audit detail and permits printing',async()=>{
  reportFixture('STOCK_VALUATION',{include_cost_details:{type:'boolean',default:false}});mount();
  await waitFor(()=>expect(screen.getByRole('button',{name:'Print / PDF'})).toBeEnabled());
  expect(screen.getByRole('region',{name:'Stock Valuation rows'})).toHaveTextContent('1,437.50');
  expect(screen.getByText(/Detail and control rows are separate evidence/)).toBeVisible();
  fireEvent.click(screen.getByRole('button',{name:'More filters'}));
  expect(screen.getByLabelText('Include cost details')).not.toBeChecked();
});

it('BATCH_SUMMARY separates current balances from history and uses frozen lot selection',async()=>{
  reportFixture('BATCH_SUMMARY',{lot_id:{anyOf:[{type:'string',format:'uuid'},{type:'null'}]},include_history:{type:'boolean',default:false},serial:{anyOf:[{type:'string'},{type:'null'}]}});mount();
  await waitFor(()=>expect(screen.getByRole('button',{name:'Print / PDF'})).toBeEnabled());
  expect(screen.getByText(/History rows do not add to physical stock/)).toBeVisible();
  fireEvent.click(screen.getByRole('combobox',{name:'Batch or lot'}));
  await screen.findByRole('option',{name:/Copper/});
  expect(vi.mocked(productFieldRequest).mock.calls.some(c=>c[0]==='reports'&&c[2].includes('kind=LOT'))).toBe(true);
});

it('STOCK_EXPIRY shows exception statuses and accepts a bounded days-ahead filter',async()=>{
  reportFixture('STOCK_EXPIRY',{days_ahead:{type:'integer',default:90,minimum:0,maximum:3650},include_expired:{type:'boolean',default:true}});
  resultRows[0].data.status='NEAR_EXPIRY';mount();
  await waitFor(()=>expect(screen.getByRole('button',{name:'Print / PDF'})).toBeEnabled());
  expect(screen.getByRole('region',{name:'Stock Expiry rows'})).toHaveTextContent('Near expiry');
  expect(screen.getByLabelText('Expiry within (days)')).toHaveAttribute('type','number');
  expect(screen.getByLabelText('Expiry within (days)')).toHaveAttribute('max','3650');
});

it('STOCK_REORDER starts with an explicit eligible-stock basis and refuses unsupported availability',async()=>{
  reportFixture('STOCK_REORDER',{quantity_basis:{type:'string',enum:['AVAILABLE','ELIGIBLE'],default:'AVAILABLE'},include_orders:{type:'boolean',default:false}});mount();
  await waitFor(()=>expect(screen.getByRole('button',{name:'Print / PDF'})).toBeEnabled());
  expect(screen.getByLabelText('Stock quantity basis')).toHaveValue('ELIGIBLE');
  expect(screen.getByText(/Reservations are not deducted/)).toBeVisible();
  fireEvent.change(screen.getByLabelText('Stock quantity basis'),{target:{value:'AVAILABLE'}});
  expect(screen.getByText(/Available stock needs verified reservations/)).toBeVisible();
  expect(screen.getByRole('button',{name:'Apply'})).toBeDisabled();
});

it('STOCK_REORDER explains missing configuration without inventing replenishment suggestions',async()=>{
  reportFixture('STOCK_REORDER',{quantity_basis:{type:'string',enum:['AVAILABLE','ELIGIBLE'],default:'AVAILABLE'}});
  job.result.evidence.inventory_metrics.configured_count=0;
  job.completed_rows=0;resultRows=[];mount();
  await waitFor(()=>expect(screen.getByRole('button',{name:'Print / PDF'})).toBeEnabled());
  expect(screen.getByText(/No reorder levels are configured for this selection/)).toBeVisible();
  expect(screen.getByText(/Configure replenishment settings/)).toBeVisible();
});

it('STOCK_AGEING has ordered age bands, a date basis and readable provenance',async()=>{
  reportFixture('STOCK_AGEING',{age_basis:{type:'string',enum:['RECEIPT','MANUFACTURE'],default:'RECEIPT'},buckets:{type:'array',items:{type:'integer'},default:[30,60,90,180],minItems:1,maxItems:8}});
  resultRows[0].data.provenance='UNKNOWN';mount();
  await waitFor(()=>expect(screen.getByRole('button',{name:'Print / PDF'})).toBeEnabled());
  expect(screen.getByLabelText('Age bands (days)')).toHaveValue('30, 60, 90, 180');
  expect(screen.getByRole('region',{name:'Stock Ageing rows'})).toHaveTextContent('Unknown');
  fireEvent.change(screen.getByLabelText('Age bands (days)'),{target:{value:'30,60'}});
  fireEvent.click(screen.getByRole('button',{name:'Apply'}));
  await waitFor(()=>expect(vi.mocked(productFieldRequest).mock.calls.some(c=>(c[3] as {parameters?:{buckets?:number[]}})?.parameters?.buckets?.join(',')==='30,60')).toBe(true));
});

it('STOCK_MOVEMENT has period filters and readable nonmoving status',async()=>{
  reportFixture('STOCK_MOVEMENT',{date_from:{type:'string',format:'date'},nonmoving_days:{type:'integer',default:90},only_nonmoving:{type:'boolean',default:false}});
  definition.parameter_schema.required.push('date_from');
  definition.definition.views[0].columns.find((c:{key:string})=>c.key==='nonmoving').kind='BOOLEAN';
  resultRows[0].data.nonmoving=true;mount();
  await waitFor(()=>expect(screen.getByRole('button',{name:'Print / PDF'})).toBeEnabled());
  expect(screen.getByRole('region',{name:'Stock Movement rows'})).toHaveTextContent('Yes');
  expect(screen.getByLabelText('From date')).toHaveAttribute('max',coverage.as_of);
  expect(screen.getByText(/Transfers are separate from consumption/)).toBeVisible();
});

it('STOCK_GROUP_SUMMARY explains overlapping groups and retains company-scoped group filters',async()=>{
  reportFixture('STOCK_GROUP_SUMMARY',{group_id:{anyOf:[{type:'string',format:'uuid'},{type:'null'}]}});mount();
  await waitFor(()=>expect(screen.getByRole('button',{name:'Print / PDF'})).toBeEnabled());
  expect(screen.getByText(/Group rows must not be added together/)).toBeVisible();
  expect(screen.getByLabelText('Search groups')).toBeVisible();
  fireEvent.click(screen.getByRole('combobox',{name:'Item group'}));
  await screen.findByRole('option',{name:/Copper/});
  expect(vi.mocked(productFieldRequest).mock.calls.some(c=>c[2].includes('kind=GROUP'))).toBe(true);
});

it('ITEM_LEDGER requires a verified item and prepares the selected period with readable balances',async()=>{
  mount();await screen.findByText(/Choose Stock item/);
  expect(screen.getByRole('button',{name:'Print / PDF'})).toBeDisabled();
  await selectItem();
  await screen.findByText('PUR-001');
  expect(screen.getByRole('heading',{name:'Item Stock Ledger'})).toBeVisible();
  expect(screen.getByLabelText('As of')).toHaveValue(coverage.as_of);
  expect(screen.getByLabelText('From date')).toHaveValue('2026-10-01');
  expect(screen.getByRole('region',{name:'Item Stock Ledger rows'})).toHaveTextContent('1,437.50');
  expect(screen.getByRole('region',{name:'Item Stock Ledger rows'})).toHaveTextContent('15/10/2026');
  expect(screen.getByRole('button',{name:'Print / PDF'})).toBeEnabled();
  expect(screen.getByRole('region',{name:'Quantity totals by unit'})).toHaveTextContent('115.000');
  expect(screen.getByText('Stock transactions')).toBeVisible();
});

it('ITEM_LEDGER history requests and accepts only its own report code',async()=>{
  mount();await screen.findByRole('button',{name:'Item Stock Ledger history'});
  await waitFor(()=>expect(screen.getByRole('button',{name:'Item Stock Ledger history'})).toBeEnabled());
  fireEvent.click(screen.getByRole('button',{name:'Item Stock Ledger history'}));
  expect(await screen.findByText('No previous Item Stock Ledger reports.')).toBeVisible();
  expect(productFieldRequest).toHaveBeenCalledWith('reports','GET',expect.stringContaining('code=ITEM_LEDGER'),undefined,undefined,expect.any(AbortSignal));
});

it('ITEM_LEDGER rejects a From date before the retained source history',async()=>{
  mount();await screen.findByRole('combobox',{name:'Stock item'});
  fireEvent.change(screen.getByLabelText('From date'),{target:{value:'2026-03-01'}});
  await selectItem();
  expect(await screen.findByText('Choose a From date within the retained stock history.')).toBeVisible();
  expect(vi.mocked(productFieldRequest).mock.calls.filter(call=>call[1]==='POST'&&call[2].endsWith('/report-runs'))).toHaveLength(0);
});
