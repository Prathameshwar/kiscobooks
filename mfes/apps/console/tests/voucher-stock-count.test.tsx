import {act,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {beforeEach,expect,it,vi} from 'vitest';
import {VoucherStockCount} from '../app/components/VoucherStockCount';
import {productFieldRequest as request} from '../app/lib/product-fields';
import {allowedStockRequest} from '../app/lib/stock-policy';
vi.mock('../app/lib/product-fields',()=>({productFieldRequest:vi.fn()}));
const id=(n:number)=>'10000000-0000-7000-8000-'+String(n).padStart(12,'0');
const detail=(observed:string|null)=>({id:id(observed===null?7:8),root_id:id(7),revision:observed===null?1:2,
  item_id:id(2),warehouse_id:id(3),bin_id:null,lot_id:null,stock_date:'2026-10-31',
  cutoff_at:'2026-10-31T08:00:00Z',cutoff_generation:12,book_quantity:'2.0000',
  observed_quantity:observed,difference:observed===null?null:'-2.0000',later_quantity:'1.0000',current_quantity:'3.0000',
  status:observed===null?'UNCOUNTED':'OBSERVED',cost_review_required:false,quantity_entry:null,
  reviewed_unit_cost:null,cost_review_reason:null,reason:'Count stock'});
beforeEach(()=>vi.clearAllMocks());
function mount(){const apply=vi.fn(),pending=vi.fn();return {...render(<VoucherStockCount company={id(1)} item={id(2)} warehouse={id(3)} date="2026-10-31" reason="Count stock" quantity="0" index={0} disabled={false} canReview onPending={pending} onApply={apply}/>),apply,pending};}
async function start(){vi.mocked(request).mockResolvedValueOnce(detail(null) as never);fireEvent.click(screen.getByRole('button',{name:'Start count 1'}));await screen.findByText('Uncounted');}
it('separates uncounted from explicit zero and records a native revision without direct balance writes',async()=>{
  const {apply}=mount();await start();expect(apply).toHaveBeenCalledWith(null);
  expect(screen.getByRole('button',{name:'Record count observation 1'})).toBeDisabled();
  fireEvent.click(screen.getByRole('checkbox'));
  vi.mocked(request).mockResolvedValueOnce(detail('0.0000') as never);
  fireEvent.click(screen.getByRole('button',{name:'Record count observation 1'}));
  await waitFor(()=>expect(apply).toHaveBeenCalledWith({observation_id:id(8),expected_revision:2}));
  expect(vi.mocked(request).mock.calls[1]?.[3]).toMatchObject({expected_revision:1,observed_quantity:'0'});
  expect(vi.mocked(request).mock.calls[1]?.[2]).toContain('/counts/'+id(7)+'/observations');
});
it('holds an ambiguous surplus for explicit authorized cost review',async()=>{
  const {apply,rerender}=mount();await start();rerender(<VoucherStockCount company={id(1)} item={id(2)} warehouse={id(3)} date="2026-10-31" reason="Count stock" quantity="3" index={0} disabled={false} canReview onPending={vi.fn()} onApply={apply}/>);
  fireEvent.click(screen.getByRole('checkbox'));vi.mocked(request).mockResolvedValueOnce({...detail('3.0000'),cost_review_required:true} as never);
  fireEvent.click(screen.getByRole('button',{name:'Record count observation 1'}));await screen.findByText(/Record an authorized cost review/);
  expect(apply).not.toHaveBeenCalledWith({observation_id:id(8),expected_revision:2});
  fireEvent.change(screen.getByLabelText('Reviewed base-unit cost 1'),{target:{value:'7.50'}});
  fireEvent.change(screen.getByLabelText('Cost review reason 1'),{target:{value:'Verified reviewed cost'}});
  fireEvent.click(screen.getByRole('checkbox'));vi.mocked(request).mockResolvedValueOnce({...detail('3.0000'),revision:3} as never);
  fireEvent.click(screen.getByRole('button',{name:'Record count observation 1'}));await waitFor(()=>expect(apply).toHaveBeenCalledWith({observation_id:id(8),expected_revision:3}));
  expect(vi.mocked(request).mock.calls[2]?.[3]).toMatchObject({reviewed_unit_cost:'7.50',cost_review_reason:'Verified reviewed cost',expected_revision:2});
});
it('ignores a late count response after the physical scope is unmounted',async()=>{
  const {apply,unmount}=mount();let finish:(value:unknown)=>void=()=>{};
  vi.mocked(request).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;}) as never);
  fireEvent.click(screen.getByRole('button',{name:'Start count 1'}));unmount();
  await act(async()=>finish(detail(null)));expect(apply).not.toHaveBeenCalled();
});
it('retains the same key on an uncertain retry and rejects another product response',async()=>{
  const {apply}=mount();vi.mocked(request).mockRejectedValueOnce(new Error('Network unavailable'));
  fireEvent.click(screen.getByRole('button',{name:'Start count 1'}));await screen.findByRole('alert');
  const key=vi.mocked(request).mock.calls[0]?.[4];vi.mocked(request).mockResolvedValueOnce({...detail(null),item_id:id(99)} as never);
  fireEvent.click(screen.getByRole('button',{name:'Start count 1'}));await screen.findByText(/could not be verified/);
  expect(vi.mocked(request).mock.calls[1]?.[4]).toBe(key);expect(apply).not.toHaveBeenCalled();
});
it('allows only count observations and refuses direct adjustments or query/path variants',()=>{
  const base='/v1/companies/'+id(1)+'/stock/counts';
  expect(allowedStockRequest('POST',base)).toBe(true);
  expect(allowedStockRequest('GET',base+'/'+id(2))).toBe(true);
  expect(allowedStockRequest('POST',base+'/'+id(2)+'/observations')).toBe(true);
  expect(allowedStockRequest('POST',base+'/'+id(2)+'/post')).toBe(false);
  expect(allowedStockRequest('PATCH',base+'/'+id(2))).toBe(false);
  expect(allowedStockRequest('POST',base+'?company_id='+id(3))).toBe(false);
});
