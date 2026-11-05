import {fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {VoucherImport,download,fileBase64} from '../app/components/VoucherImport';
import {productFieldRequest} from '../app/lib/product-fields';
import {allowedVoucherRequest} from '../app/lib/voucher-request-policy';
import {renderWithProviders} from './helpers';
vi.mock('../app/lib/product-fields',()=>({productFieldRequest:vi.fn()}));
const api=vi.mocked(productFieldRequest);
const company='01a13a95-ff92-740d-9adf-685007e8aa7a',job='01a13a95-ff92-740d-9adf-685007e8aa7b';
const all=['vouchers.import.read','vouchers.import.manage','vouchers.import.commit','vouchers.create'];
const base={id:job,row_version:1,kind:'PURCHASE',source_format:'CSV',voucher_count:2,valid_count:0,warning_count:0,invalid_count:0,created_count:0,failed_count:0,own:true,company_id:company,type_id:'t',type_revision_id:'r',on_error:'STOP',duplicate_rule:'DATE_NUMBER_PARTY',input_sha256:'a'.repeat(64),selection_digest:null,created_at:'2026-10-14T00:00:00Z',expires_at:'2026-10-21T00:00:00Z'};
const results=[{id:'r1',import_key:'A',ordinal:1,state:'VALID',error_count:0,currency:'INR',declared_total:'1234.5000',computed_payable:'1234.5000',supplier_difference:'0.0000',voucher_id:null,row_version:2},
 {id:'r2',import_key:'B',ordinal:2,state:'INVALID',error_count:1,currency:null,declared_total:null,computed_payable:null,supplier_difference:null,voucher_id:null,row_version:2}];
beforeEach(()=>{api.mockReset();});
afterEach(()=>{vi.unstubAllGlobals();});
function flow(){
  let state:Record<string,unknown>={...base,state:'STAGED'};
  api.mockImplementation(async(_service,method,path)=>{
    if(path.includes('/voucher-types'))return {items:[{id:'type',name:'Purchase',kind:'PURCHASE'},{id:'memo',name:'Memo',kind:'MEMORANDUM'}]};
    if(method==='POST'&&path.endsWith('/voucher-imports'))return state;
    if(path.endsWith('/validate')){state={...state,state:'VALIDATING',row_version:2};return state;}
    if(path.endsWith('/run')){state=state.state==='VALIDATING'?{...state,state:'READY',row_version:3,valid_count:1,invalid_count:1,selection_digest:'d'.repeat(64)}:{...state,state:'SUCCEEDED',row_version:5,created_count:1};return state;}
    if(path.endsWith('/commit')){state={...state,state:'COMMITTING',row_version:4};return state;}
    if(path.endsWith('/cancel')){state={...state,state:'CANCELLED'};return state;}
    if(path.includes('/vouchers/B'))return {...results[1],errors:[{sheet:'CSV',row:4,column:'amount',code:'invalid_decimal',message:'use a plain decimal',layer:'L2'}],source_rows:[['CSV',4]],computed_tax_total:null};
    if(path.includes('/vouchers?'))return {items:state.state==='STAGED'?[]:results,next_cursor:null};
    throw new Error('unexpected '+method+' '+path);
  });
}
async function staged(display?:Record<string,unknown>){
  await renderWithProviders(<VoucherImport company={company} permissions={all}/>,display?{display:display as never}:{});
  fireEvent.click(screen.getByText('Load voucher types'));
  await screen.findByRole('option',{name:'Purchase (Purchase)'});
  fireEvent.change(screen.getByLabelText('Voucher type'),{target:{value:'type'}});
  fireEvent.change(screen.getByLabelText('File format'),{target:{value:'CSV'}});
  if(display===undefined)fireEvent.change(screen.getByLabelText('Treat as duplicate'),{target:{value:'DATE_NUMBER'}});
  const file=new File(['_voucher_schema_version,1\n'],'bills.csv',{type:'text/csv'});
  fireEvent.change(screen.getByLabelText('Import file'),{target:{files:[file]}});
  fireEvent.click(screen.getByText('Upload file'));
  await screen.findByText(/Job STAGED/);
}
it('renders nothing without import read permission',()=>{
  const view=render(<VoucherImport company={company} permissions={['vouchers.read']}/>);
  expect(view.container).toBeEmptyDOMElement();
});
it('reads results without manage or commit controls',async()=>{
  api.mockResolvedValue({items:[]});
  await renderWithProviders(<VoucherImport company={company} permissions={['vouchers.import.read']}/>);
  expect(screen.queryByText('Upload file')).not.toBeInTheDocument();
  expect(screen.queryByText('Download template')).not.toBeInTheDocument();
  expect(screen.getByText('Load voucher types')).toBeInTheDocument();
});
it('stages, validates, reviews and creates drafts with stable idempotency keys',async()=>{
  flow();await staged();
  const upload=api.mock.calls.find(call=>call[1]==='POST'&&call[2].endsWith('/voucher-imports'));
  expect(upload?.[3]).toEqual({voucher_type_id:'type',format:'CSV',duplicate_rule:'DATE_NUMBER',content_base64:btoa('_voucher_schema_version,1\n')});
  expect(screen.getByText('Duplicate check: Same bill number, date and supplier')).toBeInTheDocument();
  fireEvent.click(screen.getByText('Validate'));
  await screen.findByText(/Job READY/);
  const table=screen.getByRole('table',{name:'Import results'});
  expect(within(table).getByText('VALID')).toBeInTheDocument();
  expect(within(table).getAllByText(/1,234\.50/).length).toBeGreaterThan(0);
  fireEvent.click(screen.getByText('Details for B'));
  expect(await screen.findByText(/use a plain decimal \(invalid_decimal\)/)).toBeInTheDocument();
  expect(screen.getByText('Create drafts')).toBeDisabled();
  fireEvent.click(screen.getByLabelText(/I reviewed the results/));
  fireEvent.change(screen.getByLabelText('If a draft fails'),{target:{value:'CONTINUE_INDEPENDENT'}});
  fireEvent.click(screen.getByText('Create drafts'));
  await screen.findByText(/Job SUCCEEDED/);
  const commit=api.mock.calls.find(call=>call[2].endsWith('/commit'));
  expect(commit?.[3]).toEqual({expected_version:3,selection_digest:'d'.repeat(64),on_error:'CONTINUE_INDEPENDENT'});
  expect(typeof commit?.[4]).toBe('string');
  expect(screen.queryByText('Cancel import')).not.toBeInTheDocument();
  expect(screen.getByText('Download result report')).toBeInTheDocument();
});
it.each(['Session expired','Access denied','Invalid file','Service unavailable'])('shows %s and retries the upload with the same key',async(message)=>{
  let attempts=0;
  api.mockImplementation(async(_service,method,path)=>{
    if(path.includes('/voucher-types'))return {items:[{id:'type',name:'Purchase',kind:'PURCHASE'},{id:'memo',name:'Memo',kind:'MEMORANDUM'}]};
    if(method==='POST'&&attempts++===0)throw new Error(message);
    if(method==='POST')return {...base,state:'STAGED'};
    return {items:[],next_cursor:null};
  });
  await renderWithProviders(<VoucherImport company={company} permissions={all}/>);
  fireEvent.click(screen.getByText('Load voucher types'));
  await screen.findByRole('option',{name:'Purchase (Purchase)'});
  fireEvent.change(screen.getByLabelText('Voucher type'),{target:{value:'type'}});
  fireEvent.change(screen.getByLabelText('Import file'),{target:{files:[new File(['x'],'b.xlsx')]}});
  fireEvent.click(screen.getByText('Upload file'));
  expect(await screen.findByRole('alert')).toHaveTextContent(message);
  fireEvent.click(screen.getByText('Upload file'));
  await screen.findByText(/Job STAGED/);
  const posts=api.mock.calls.filter(call=>call[1]==='POST');
  expect(posts[0][4]).toBe(posts[1][4]);
});
it('cancels a staged job and explains when nothing is valid',async()=>{
  flow();await staged();
  fireEvent.click(screen.getByText('Cancel import'));
  await screen.findByText(/Job CANCELLED/);
  api.mockImplementation(async(_s,_m,path)=>path.includes('/vouchers?')?{items:[],next_cursor:null}:{...base,state:'READY',invalid_count:2});
  fireEvent.click(screen.getByText('Download result report'));
  await waitFor(()=>expect(screen.getByRole('alert')).toBeInTheDocument());
});
it('warns when validation left no importable voucher',async()=>{
  let state:Record<string,unknown>={...base,state:'STAGED'};
  api.mockImplementation(async(_s,method,path)=>{
    if(path.includes('/voucher-types'))return {items:[{id:'type',name:'Purchase',kind:'PURCHASE'},{id:'memo',name:'Memo',kind:'MEMORANDUM'}]};
    if(path.endsWith('/validate')){state={...state,state:'READY',invalid_count:2,selection_digest:'d'.repeat(64)};return state;}
    if(method==='POST')return state;
    return {items:[],next_cursor:null};
  });
  await staged();
  fireEvent.click(screen.getByText('Validate'));
  expect(await screen.findByText('No voucher passed validation. Correct the file and upload it again.')).toBeInTheDocument();
  expect(screen.queryByText('Create drafts')).not.toBeInTheDocument();
});
it('downloads through the proxy and reports failures',async()=>{
  const click=vi.fn();
  vi.stubGlobal('URL',Object.assign(URL,{createObjectURL:vi.fn(()=>'blob:x'),revokeObjectURL:vi.fn()}));
  vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(click);
  const fetcher=vi.fn(async()=>new Response('csv',{status:200}));
  vi.stubGlobal('fetch',fetcher);
  await download('/v1/companies/x/voucher-import-templates?format=CSV','t.csv');
  expect(click).toHaveBeenCalled();
  expect(JSON.parse((fetcher.mock.calls[0] as unknown as [string,{body:string}])[1].body)).toEqual({service:'vouchers',method:'GET',path:'/v1/companies/x/voucher-import-templates?format=CSV'});
  vi.stubGlobal('fetch',vi.fn(async()=>Response.json({error:{message:'Access denied'}},{status:403})));
  await expect(download('/x','t.csv')).rejects.toThrow('Access denied');
  vi.stubGlobal('fetch',vi.fn(async()=>new Response('oops',{status:500})));
  await expect(download('/x','t.csv')).rejects.toThrow('Unable to download the file');
  expect(await fileBase64(new Blob(['hello']))).toBe(btoa('hello'));
});
it('allows only the import routes the screen uses',()=>{
  const prefix='/v1/companies/'+company;
  expect(allowedVoucherRequest('GET',prefix+'/voucher-import-templates?format=CSV')).toBe(true);
  expect(allowedVoucherRequest('POST',prefix+'/voucher-imports')).toBe(true);
  expect(allowedVoucherRequest('GET',prefix+'/voucher-imports/'+job+'/vouchers/PB-0001')).toBe(true);
  expect(allowedVoucherRequest('GET',prefix+'/voucher-imports/'+job+'/report?token=x')).toBe(true);
  expect(allowedVoucherRequest('POST',prefix+'/voucher-imports/'+job+'/run')).toBe(true);
  expect(allowedVoucherRequest('DELETE',prefix+'/voucher-imports/'+job)).toBe(false);
  expect(allowedVoucherRequest('POST',prefix+'/voucher-imports/'+job+'/report')).toBe(false);
  expect(allowedVoucherRequest('GET',prefix+'/voucher-imports/'+job+'/vouchers/../x')).toBe(false);
});
it('formats imported money with a non-en display configuration',async()=>{
  flow();
  await staged({currency:'EUR',currencySymbol:'€',amountPrecision:2,quantityPrecision:3,roundingMode:'half_up',dateFormat:'dd.MM.yyyy',datetimeFormat:'dd.MM.yyyy HH:mm',digitGrouping:'western',currencyDisplay:'symbol',timezone:'Europe/Berlin',locale:'de-DE'});
  fireEvent.click(screen.getByText('Validate'));
  const table=await screen.findByRole('table',{name:'Import results'});
  expect(within(table).getAllByText(/1[., ]?234[.,]50/).length).toBeGreaterThan(0);
});
it('reviews every page of results and can resume a working job',async()=>{
  let state:Record<string,unknown>={...base,state:'STAGED'};
  api.mockImplementation(async(_s,method,path)=>{
    if(path.includes('/voucher-types'))return {items:[{id:'type',name:'Purchase',kind:'PURCHASE'},{id:'memo',name:'Memo',kind:'MEMORANDUM'}]};
    if(path.endsWith('/validate')){state={...state,state:'VALIDATING'};return state;}
    if(path.endsWith('/run'))throw new Error('import rate limit exceeded');
    if(method==='POST')return state;
    if(path.includes('cursor=next'))return {items:[results[1]],next_cursor:null};
    if(path.includes('/vouchers?'))return {items:state.state==='STAGED'?[]:[results[0]],next_cursor:state.state==='STAGED'?null:'next'};
    return state;
  });
  await staged();
  fireEvent.click(screen.getByText('Validate'));
  expect(await screen.findByRole('alert')).toHaveTextContent('import rate limit exceeded');
  api.mockImplementation(async(_s,method,path)=>{
    if(path.endsWith('/run')){state={...state,state:'READY',valid_count:1,invalid_count:1,selection_digest:'d'.repeat(64)};return state;}
    if(path.includes('cursor=next'))return {items:[results[1]],next_cursor:null};
    if(path.includes('/vouchers?'))return {items:[results[0]],next_cursor:'next'};
    return state;
  });
  fireEvent.click(screen.getByText('Continue'));
  await screen.findByText(/Job READY/);
  const table=screen.getByRole('table',{name:'Import results'});
  expect(within(table).getByText('A')).toBeInTheDocument();
  expect(within(table).getByText('B')).toBeInTheDocument();
});
it('offers supported kinds only and hides the purchase duplicate rule for others',async()=>{
  api.mockImplementation(async(_s,_m,path)=>path.includes('/voucher-types')?{items:[{id:'pay',name:'Bank payment',kind:'PAYMENT'},{id:'memo',name:'Memo',kind:'MEMORANDUM'}]}:{items:[]});
  await renderWithProviders(<VoucherImport company={company} permissions={all}/>);
  fireEvent.click(screen.getByText('Load voucher types'));
  await screen.findByRole('option',{name:'Bank payment (Payment)'});
  expect(screen.queryByRole('option',{name:/Memo/})).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Voucher type'),{target:{value:'pay'}});
  expect(screen.queryByLabelText('Treat as duplicate')).not.toBeInTheDocument();
});
