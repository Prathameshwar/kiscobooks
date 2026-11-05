import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {DisplayConfigProvider} from '@janso/ui';
import {FinancialReports} from '../app/components/FinancialReports';
import {productFieldRequest} from '../app/lib/product-fields';
vi.mock('../app/lib/product-fields',()=>({productFieldRequest:vi.fn()}));
vi.mock('@janso/ui',async original=>({...await original<typeof import('@janso/ui')>(),SearchSelect:({label,onChange,disabled}:{label:string;onChange:(id:string)=>void;disabled:boolean})=><button type="button" disabled={disabled} onClick={()=>onChange('selected')}>{label}</button>}));
const api=vi.mocked(productFieldRequest);
const codes=['ACCOUNT_LEDGER','TRIAL_BALANCE','ACCOUNT_SUMMARY','BANK_RECONCILIATION','SOURCE_RECONCILIATION','INVOICE_TAX_REGISTER','SALES_REGISTER'];
const properties=Object.fromEntries(['date_from','date_to','account_id','group_id','party_id','role','basis','currency','grain','comparative_from','comparative_to','statement_balance'].map(key=>[key,{}]));
beforeEach(()=>{
 sessionStorage.clear();
 api.mockReset();api.mockImplementation(async(_,method,path)=>{
  if(path.endsWith('/report-definitions'))return codes.map(code=>({code,financial_statement:code==='TRIAL_BALANCE'}));
  if(path.includes('field-set'))return {native:{properties}};
  if(path.includes('report-generations'))return method==='POST'?{id:'generation',status:'PENDING'}:{items:[{id:'generation',status:'READY'},{id:'pending',status:'PENDING'}]};
  if(method==='POST')return {id:'run',status:'PENDING'};
  if(path.includes('/rows'))return {items:[{id:path.includes('cursor')?'second':'first',data:{amount:'1234.5000',currency:'INR',date:'2026-04-02',optional:null,metadata:{reviewed:true}}}],page:{next_cursor:path.includes('cursor')?null:'next'}};
  return {id:'run',status:'COMPLETE',download_token:'signed'};
 });
});
it('defaults the classic API dates to the selected year and preserves explicit custom dates on year switching',async()=>{
 const selected={id:'new',code:'FY2027',startDate:'2027-04-01',endDate:'2028-03-31',current:true,open:true},previous={id:'old',code:'FY2026',startDate:'2026-04-01',endDate:'2027-03-31',current:false,open:true};
 const result=render(<FinancialReports company="company" permissions={['report.read']} year={selected} years={[previous,selected]}/>);
 fireEvent.click(screen.getByText('Load reports'));await screen.findByRole('option',{name:'ACCOUNT LEDGER'});
 fireEvent.change(screen.getByLabelText('Report'),{target:{value:'TRIAL_BALANCE'}});fireEvent.click(screen.getByText('Load report fields'));
 fireEvent.change(screen.getByLabelText('Source snapshot'),{target:{value:'generation'}});
 await screen.findByLabelText('From date');expect(screen.getByLabelText('From date')).toHaveValue(selected.startDate);
 expect(screen.getByLabelText('To date')).toHaveValue(selected.endDate);
 fireEvent.change(screen.getByLabelText('From date'),{target:{value:'2027-05-01'}});
 result.rerender(<FinancialReports company="company" permissions={['report.read']} year={previous} years={[previous,selected]}/>);
 expect(screen.getByLabelText('From date')).toHaveValue('2027-05-01');expect(screen.getByLabelText('To date')).toHaveValue(selected.endDate);
 fireEvent.click(screen.getByText('Create report'));await screen.findByText('Report: PENDING');
 expect(api.mock.calls.find(call=>call[1]==='POST')?.[3]).toMatchObject({date_from:'2027-05-01',date_to:selected.endDate});
});
afterEach(()=>{vi.unstubAllGlobals();vi.restoreAllMocks();});
it('uses native invoice date choices and clears the choice when changing reports',async()=>{
 const base=api.getMockImplementation()!;
 api.mockImplementation(async(...args)=>args[2].includes('INVOICE_TAX_REGISTER/field-set')?{native:{properties:{...properties,date_basis:{enum:['POSTING','DOCUMENT','TAX_POINT']}}}}:args[2].includes('SALES_REGISTER/field-set')?{native:{properties:{...properties,date_basis:{enum:['POSTING','DOCUMENT']}}}}:base(...args));
 view();await choose('INVOICE_TAX_REGISTER');
 fireEvent.change(screen.getByLabelText('Date basis'),{target:{value:'TAX_POINT'}});
 fireEvent.click(screen.getByText('Create report'));await screen.findByText('Report: PENDING');
 expect(api.mock.calls.filter(call=>call[1]==='POST').at(-1)?.[3]).toMatchObject({code:'INVOICE_TAX_REGISTER',date_basis:'TAX_POINT'});
 fireEvent.change(screen.getByLabelText('Report'),{target:{value:'SALES_REGISTER'}});fireEvent.click(screen.getByText('Load report fields'));await screen.findByLabelText('Date basis');
 expect(screen.getByLabelText('Date basis')).toHaveValue('POSTING');expect(screen.queryByRole('option',{name:'Tax event date'})).not.toBeInTheDocument();
 fireEvent.change(screen.getByLabelText('Date basis'),{target:{value:'DOCUMENT'}});fireEvent.click(screen.getByText('Create report'));await screen.findByText('Report: PENDING');
 expect(api.mock.calls.filter(call=>call[1]==='POST').at(-1)?.[3]).toMatchObject({code:'SALES_REGISTER',date_basis:'DOCUMENT'});
});
function view(permissions=['report.read']){render(<DisplayConfigProvider config={{locale:'hi-IN',currency:'INR',amountPrecision:2,dateFormat:'dd/MM/yyyy'}}><FinancialReports company="company" permissions={permissions}/></DisplayConfigProvider>);}
async function choose(code:string){
 fireEvent.click(screen.getByText('Load reports'));await screen.findByRole('option',{name:'ACCOUNT LEDGER'});
 fireEvent.change(screen.getByLabelText('Report'),{target:{value:code}});
 fireEvent.change(screen.getByLabelText('Source snapshot'),{target:{value:'generation'}});
 fireEvent.click(screen.getByText('Load report fields'));
 if(code!=='SOURCE_RECONCILIATION'){
  await screen.findByLabelText('From date');fireEvent.change(screen.getByLabelText('From date'),{target:{value:'2026-04-01'}});fireEvent.change(screen.getByLabelText('To date'),{target:{value:'2026-04-30'}});
 }else await waitFor(()=>expect(screen.getByText('Create report')).toBeEnabled());
}
it('submits selected filters, preserves failed request identity, waits for completion and pages formatted rows',async()=>{
 const base=api.getMockImplementation()!;let attempts=0;
 api.mockImplementation(async(...args)=>args[1]==='POST'&&attempts++===0?Promise.reject(new Error('Offline')):base(...args));
 view();await choose('ACCOUNT_SUMMARY');
 fireEvent.click(screen.getByText('Ledger account'));fireEvent.click(screen.getByText('Account group'));fireEvent.click(screen.getByText('Party'));
 fireEvent.change(screen.getByLabelText('Party role'),{target:{value:'CUSTOMER'}});
 fireEvent.change(screen.getByLabelText('Amount basis'),{target:{value:'TRANSACTION'}});
 fireEvent.change(screen.getByLabelText('Transaction currency'),{target:{value:'USD'}});
 fireEvent.change(screen.getByLabelText('Summary period'),{target:{value:'MONTH'}});
 fireEvent.change(screen.getByLabelText('Comparative from date'),{target:{value:'2025-04-01'}});
 expect(screen.getByLabelText('Comparative to date')).toBeRequired();
 fireEvent.change(screen.getByLabelText('Comparative to date'),{target:{value:'2025-04-30'}});
 fireEvent.click(screen.getByText('Create report'));expect(await screen.findByRole('alert')).toHaveTextContent('Offline');
 fireEvent.click(screen.getByText('Create report'));await screen.findByText('Report: PENDING');
 expect(screen.queryByRole('table')).not.toBeInTheDocument();
 const calls=api.mock.calls.filter(call=>call[1]==='POST');expect(calls[0][4]).toBe(calls[1][4]);
 expect(calls[1][3]).toMatchObject({basis:'TRANSACTION',currency:'USD',account_id:'selected',group_id:'selected',party_id:'selected',role:'CUSTOMER',grain:'MONTH',comparative_from:'2025-04-01'});
 fireEvent.click(screen.getByText('Refresh report'));await screen.findByText('1,234.50 INR');await screen.findByText('02/04/2026');
 fireEvent.click(screen.getByText('More report rows'));await waitFor(()=>expect(screen.getAllByText('1,234.50 INR')).toHaveLength(2));
 expect(screen.queryByText('Download CSV')).not.toBeInTheDocument();
});
it('requires a statement balance and bank account and omits statement-only filters from financial statements',async()=>{
 view();await choose('BANK_RECONCILIATION');expect(screen.getByText('Create report')).toBeDisabled();
 expect(screen.queryByLabelText('Comparative from date')).not.toBeInTheDocument();
 expect(screen.queryByText('Account group')).not.toBeInTheDocument();
 expect(screen.queryByText('Party')).not.toBeInTheDocument();
 expect(screen.queryByLabelText('Party role')).not.toBeInTheDocument();
 fireEvent.click(screen.getByText('Ledger account'));fireEvent.change(screen.getByLabelText('Statement closing balance'),{target:{value:'-120.2500'}});
 fireEvent.click(screen.getByText('Create report'));await screen.findByText('Report: PENDING');
 expect(api.mock.calls.find(call=>call[1]==='POST')?.[3]).toMatchObject({account_id:'selected',statement_balance:'-120.2500'});
 fireEvent.change(screen.getByLabelText('Report'),{target:{value:'TRIAL_BALANCE'}});fireEvent.click(screen.getByText('Load report fields'));await screen.findByLabelText('From date');
 expect(screen.queryByText('Ledger account')).not.toBeInTheDocument();expect(screen.queryByLabelText('Amount basis')).not.toBeInTheDocument();
 fireEvent.click(screen.getByText('Create report'));await screen.findByText('Report: PENDING');
 expect(api.mock.calls.filter(call=>call[1]==='POST').at(-1)?.[3]).toEqual({code:'TRIAL_BALANCE',generation_id:'generation',date_from:'2026-04-01',date_to:'2026-04-30'});
});
it('requests a source refresh only with permission and downloads a completed signed CSV',async()=>{
 view(['report.read','report.definition.manage','report.export']);
 fireEvent.click(screen.getByText('Refresh report sources'));await screen.findByText('Report source refresh requested: generation');
 await choose('SOURCE_RECONCILIATION');expect(screen.queryByLabelText('From date')).not.toBeInTheDocument();
 fireEvent.click(screen.getByText('Create report'));await screen.findByText('Report: PENDING');fireEvent.click(screen.getByText('Refresh report'));await screen.findByText('Download CSV');
 const fetch=vi.fn().mockResolvedValue(new Response('amount\n1.00',{headers:{'content-type':'text/csv'}}));vi.stubGlobal('fetch',fetch);
 const create=vi.fn().mockReturnValue('blob:test'),revoke=vi.fn();vi.stubGlobal('URL',class extends URL {static createObjectURL=create;static revokeObjectURL=revoke;});
 vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(()=>{});
 fireEvent.click(screen.getByText('Download CSV'));await waitFor(()=>expect(revoke).toHaveBeenCalledWith('blob:test'));
 expect(JSON.parse(fetch.mock.calls[0][1].body).path).toContain('/run/download?token=signed');
});
it.each(['401 Session expired','403 Access denied','422 Invalid date','500 Temporarily unavailable'])('shows %s without a blank screen',async error=>{
 api.mockRejectedValue(new Error(error));view();fireEvent.click(screen.getByText('Load reports'));expect(await screen.findByRole('alert')).toHaveTextContent(error);expect(screen.getByText('Load reports')).toBeEnabled();
});
it('explains a blocked calculation without showing partial output',async()=>{
 const base=api.getMockImplementation()!;
 api.mockImplementation(async(...args)=>args[1]==='GET'&&args[2].endsWith('/report-runs/run')?{id:'run',status:'BLOCKED',download_token:null}:base(...args));
 view();await choose('ACCOUNT_LEDGER');fireEvent.click(screen.getByText('Create report'));await screen.findByText('Report: PENDING');
 fireEvent.click(screen.getByText('Refresh report'));expect(await screen.findByRole('alert')).toHaveTextContent('Check the report parameters');
 expect(screen.queryByRole('table')).not.toBeInTheDocument();expect(screen.queryByText('Download CSV')).not.toBeInTheDocument();
});
