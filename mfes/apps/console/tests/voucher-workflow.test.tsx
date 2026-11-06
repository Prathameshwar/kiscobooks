import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {beforeEach,expect,it,vi} from 'vitest';
import {VoucherWorkflow} from '../app/components/VoucherWorkflow';
import {productFieldRequest} from '../app/lib/product-fields';
import {DisplayConfigProvider} from '@janso/ui';
vi.mock('../app/lib/product-fields',()=>({productFieldRequest:vi.fn()}));
const api=vi.mocked(productFieldRequest);
beforeEach(()=>{api.mockReset();});
it('uses the current version and preserves a failed submit identity',async()=>{
 let attempts=0;api.mockImplementation(async(_,method)=>{if(method==='GET')return {id:'voucher',company_id:'company',row_version:4,status:'DRAFT'};if(attempts++===0)throw new Error('Retry later');return {id:'voucher',company_id:'company',row_version:5,status:'SUBMITTED'};});
 render(<VoucherWorkflow company="company" voucherId="voucher" permissions={['vouchers.submit']}/>);
 fireEvent.click(screen.getByRole('button',{name:'Refresh voucher'}));await screen.findByText('Status: DRAFT');
 expect(screen.queryByRole('button',{name:'Cancel'})).not.toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'Submit'}));expect(await screen.findByRole('status')).toHaveTextContent('Retry later');
 fireEvent.click(screen.getByRole('button',{name:'Submit'}));await screen.findByText('Status: SUBMITTED');
 const calls=api.mock.calls.filter(call=>call[1]==='POST');expect(calls[0][3]).toEqual({expected_version:4,reason:''});expect(calls[1][4]).toBe(calls[0][4]);
});
it('pages history only for the permitted user and reports read errors',async()=>{
 api.mockImplementation(async(_,method,path)=>{if(path.includes('history'))return {items:[{id:path.includes('cursor')?'second':'first',action:'submit',from_status:'DRAFT',to_status:'SUBMITTED'}],page:{next_cursor:path.includes('cursor')?null:'next'}};throw new Error('Access changed');});
 render(<VoucherWorkflow company="company" voucherId="voucher" permissions={['vouchers.history.read']}/>);
 fireEvent.click(screen.getByRole('button',{name:'Load voucher history'}));await screen.findByText('submit: DRAFT → SUBMITTED');
 fireEvent.click(screen.getByRole('button',{name:'More history'}));await waitFor(()=>expect(screen.getAllByRole('listitem')).toHaveLength(2));
 fireEvent.click(screen.getByRole('button',{name:'Refresh voucher'}));expect(await screen.findByRole('status')).toHaveTextContent('Access changed');
});

it('can issue using the configured series without inventing a number',async()=>{
 api.mockImplementation(async(_,method)=>method==='GET'?{id:'voucher',company_id:'company',row_version:2,status:'APPROVED'}:{id:'voucher',company_id:'company',row_version:3,status:'ISSUED',issue_number:'DOC-2026/000001'});
 render(<VoucherWorkflow company="company" voucherId="voucher" permissions={['vouchers.issue']}/>);
 fireEvent.click(screen.getByRole('button',{name:'Refresh voucher'}));await screen.findByText('Status: APPROVED');
 fireEvent.click(screen.getByRole('button',{name:'Issue'}));await screen.findByText('Status: ISSUED · DOC-2026/000001');
 expect(api.mock.calls.find(call=>call[1]==='POST')?.[3]).toEqual({expected_version:2,reason:''});
});

it.each([0,2,4])('formats preview with configured precision %s and explicit currency',async precision=>{
 const draft={id:'voucher',company_id:'company',row_version:2,status:'DRAFT',revision_id:'revision',posting_date:'2026-04-02',currency:'INR',invoice:{supplies:[]}};
 api.mockImplementation(async(_,method)=>method==='GET'?draft:{calculation_hash:'b'.repeat(64),payable:'900.1250',commercial_total:'900.1250',tax_total:'0.0000'});
 render(<DisplayConfigProvider config={{currency:'INR',amountPrecision:precision,decimalSeparator:',',groupSeparator:'.'}}><VoucherWorkflow company="company" voucherId="voucher" permissions={['vouchers.read']}/></DisplayConfigProvider>);
 fireEvent.click(screen.getByRole('button',{name:'Refresh voucher'}));await screen.findByText('Status: DRAFT');
 fireEvent.click(screen.getByRole('button',{name:'Preview invoice'}));
 const expected=precision===0?'900':precision===2?'900,13':'900,1250';
 expect(await screen.findByText(/Invoice total:/)).toHaveTextContent('Invoice total: '+expected+' INR');
});
it('offers issued order decisions only with their permission and a decline reason',async()=>{
 api.mockImplementation(async(_,method)=>method==='GET'?{id:'voucher',company_id:'company',kind:'SALES_ORDER',profile:'QUOTATION',row_version:4,status:'ISSUED'}:{id:'voucher',company_id:'company',kind:'SALES_ORDER',profile:'QUOTATION',row_version:5,status:'DECLINED'});
 render(<VoucherWorkflow company="company" voucherId="voucher" permissions={['vouchers.decline']}/>);
 fireEvent.click(screen.getByRole('button',{name:'Refresh voucher'}));await screen.findByText('Status: ISSUED');
 expect(screen.queryByRole('button',{name:'Accept'})).not.toBeInTheDocument();
 expect(screen.queryByRole('button',{name:'Expire'})).not.toBeInTheDocument();
 expect(screen.getByRole('button',{name:'Decline'})).toBeDisabled();
 fireEvent.change(screen.getByLabelText('Reason'),{target:{value:'Buyer withdrew'}});
 fireEvent.click(screen.getByRole('button',{name:'Decline'}));await screen.findByText('Status: DECLINED');
 expect(api.mock.calls.find(row=>row[1]==='POST')?.[3]).toEqual({expected_version:4,reason:'Buyer withdrew'});
});
it('accepts an owner calculation into a new draft revision before approval',async()=>{
 const draft={id:'voucher',company_id:'company',row_version:2,revision_id:'revision',status:'DRAFT',type_revision_id:'type',class_id:null,document_date:'2026-04-02',posting_date:'2026-04-02',stock_date:null,statutory_date:null,credit_terms_date:null,mode:'ACCOUNTS',currency:'INR',narration:'Service',lines:[],parties:[],references:[],attachments:[],links:[],custom_fields:{},invoice:{accepted_calculation_hash:null,supplies:[]}};
 api.mockImplementation(async(_,method,path)=>{
   if(method==='GET'&&path.includes('/vouchers/voucher'))return draft;
   if(method==='POST'&&path.includes('invoice-preview'))return {calculation_hash:'b'.repeat(64),payable:'900.00',commercial_total:'900.00',tax_total:'0.00'};
   if(method==='POST'&&path.includes('invoice-acceptance'))return {...draft,row_version:3,revision_id:'accepted',invoice:{...draft.invoice,accepted_calculation_hash:'b'.repeat(64)}};
   throw new Error('Unexpected request');
 });
 render(<VoucherWorkflow company="company" voucherId="voucher" permissions={['vouchers.read','vouchers.edit']}/>);
 fireEvent.click(screen.getByRole('button',{name:'Refresh voucher'}));await screen.findByText('Status: DRAFT');
 fireEvent.click(screen.getByRole('button',{name:'Preview invoice'}));await screen.findByText(/Invoice total: 900.00/);
 fireEvent.click(screen.getByRole('button',{name:'Accept calculation'}));
 await screen.findByText('Invoice calculation accepted in a new revision');
 const call=api.mock.calls.find(row=>row[2].includes('invoice-acceptance'));
 expect(call?.[3]).toEqual({expected_version:2,calculation_hash:'b'.repeat(64)});
 expect(screen.queryByRole('button',{name:'Accept calculation'})).not.toBeInTheDocument();
});

it.each(['DRAFT','POSTED','CANCELLED'])('shows a %s Purchase print link on the voucher review page when print access is held',async status=>{
 const id='10000000-0000-7000-8000-000000000001',revision='10000000-0000-7000-8000-000000000002';
 api.mockResolvedValue({id,company_id:id,kind:'PURCHASE',profile:'STANDARD',status,row_version:8,revision_id:revision} as never);
 const permissions=['vouchers.read','vouchers.artifact.create','vouchers.artifact.read','accounting.account.read'];
 const view=render(<VoucherWorkflow company={id} voucherId={id} permissions={permissions}/>);
 expect(await screen.findByRole('link',{name:'Preview / print Purchase'})).toHaveAttribute('href',`/vouchers/${id}/print?revision=${revision}&version=8`);
 view.rerender(<VoucherWorkflow company={id} voucherId={id} permissions={permissions.filter(key=>key!=='vouchers.artifact.read')}/>);
 expect(screen.queryByRole('link',{name:'Preview / print Purchase'})).not.toBeInTheDocument();
});

it('confirms Purchase cancellation on the generic review route before sending a command',async()=>{
 const draft={id:'voucher',company_id:'company',kind:'PURCHASE',profile:'STANDARD',status:'DRAFT',row_version:4,revision_id:'revision'};
 api.mockImplementation(async(_,method)=>method==='GET'?draft:{...draft,status:'CANCELLED',row_version:5});
 render(<VoucherWorkflow company="company" voucherId="voucher" permissions={['vouchers.read','vouchers.cancel']}/>);
 await screen.findByText('Status: DRAFT');
 fireEvent.change(screen.getByLabelText('Reason'),{target:{value:'Duplicate supplier bill'}});
 fireEvent.click(screen.getByRole('button',{name:'Cancel'}));
 expect(screen.getByRole('dialog',{name:'Cancel this voucher?'})).toBeVisible();
 expect(api.mock.calls.filter(call=>call[1]==='POST')).toHaveLength(0);
 fireEvent.click(screen.getByRole('button',{name:'Keep voucher'}));
 expect(api.mock.calls.filter(call=>call[1]==='POST')).toHaveLength(0);
 fireEvent.click(screen.getByRole('button',{name:'Cancel'}));
 fireEvent.click(screen.getByRole('button',{name:'Cancel voucher'}));
 await screen.findByText('Status: CANCELLED');
 expect(api.mock.calls.filter(call=>call[1]==='POST')).toHaveLength(1);
 expect(api.mock.calls.find(call=>call[1]==='POST')?.[3]).toEqual({expected_version:4,reason:'Duplicate supplier bill'});
});
