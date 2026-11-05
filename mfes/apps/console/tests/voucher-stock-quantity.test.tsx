import {act,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {beforeEach,expect,it,vi} from 'vitest';
import {VoucherStockQuantity} from '../app/components/VoucherStockQuantity';
import {productFieldRequest as request} from '../app/lib/product-fields';
vi.mock('../app/lib/product-fields',()=>({productFieldRequest:vi.fn()}));
vi.mock('@janso/ui',async original=>({...await original<typeof import('@janso/ui')>(),SearchSelect:({label,loadOptions,onChange,disabled}:{label:string;loadOptions:(q:{q:string})=>Promise<{items:{id:string}[]}>;onChange:(id:string)=>void;disabled:boolean})=><button disabled={disabled} onClick={()=>void loadOptions({q:''}).then(page=>onChange(page.items[0]!.id))}>{label}</button>}));
const id=(n:number)=>'01990000-0000-7000-8000-'+String(n).padStart(12,'0');
let mode:'FIXED'|'MEASURED'='FIXED';
beforeEach(()=>{mode='FIXED';vi.mocked(request).mockReset().mockImplementation(async(_owner,_method,path)=>{
 if(path.includes('/unit-bindings?'))return {items:[{id:id(4),unit_id:id(5),code:'PACK'}],page:{has_more:false,next_cursor:null}} as never;
 if(path.includes('/revisions?'))return {items:[{id:id(6),conversion_mode:mode,valid_from:'2026-01-01',valid_to:null}],page:{has_more:false,next_cursor:null}} as never;
 return {item_id:id(2),base_unit_id:id(3),base_quantity:'24.0000'} as never;
});});
function mount(){const apply=vi.fn(),pending=vi.fn();const view=render(<VoucherStockQuantity company={id(1)} item={id(2)} baseUnit={id(3)} date="2026-10-31" index={0} onApply={apply} onPending={pending} disabled={false}/>);return {...view,apply,pending};}
async function choose(){fireEvent.click(screen.getByRole('button',{name:'Enter in another product unit 1'}));fireEvent.click(screen.getByRole('button',{name:'Entered product unit 1'}));await waitFor(()=>expect(screen.getByRole('button',{name:'Validate and apply quantity 1'})).toBeEnabled());fireEvent.change(screen.getByLabelText('Entered quantity 1'),{target:{value:'2'}});}
it('retains exact fixed entry and validates it through the native preview',async()=>{
 const {apply,pending}=mount();await choose();fireEvent.click(screen.getByRole('button',{name:'Validate and apply quantity 1'}));await screen.findByText(/Applied 24.0000/);
 expect(pending).toHaveBeenCalled();expect(apply).toHaveBeenCalledWith({entered_unit_id:id(5),unit_revision_id:id(6),entered_quantity:'2'},'24.0000');
 expect(vi.mocked(request).mock.calls.find(call=>call[2].includes('/unit-bindings?'))![2]).not.toContain('as_of');expect(vi.mocked(request).mock.calls.find(call=>call[2].includes('/revisions?'))![2]).toContain('as_of=2026-10-31');
});
it('requires actual measured base quantity and never uses a nominal ratio',async()=>{
 mode='MEASURED';const {apply}=mount();await choose();fireEvent.click(screen.getByRole('button',{name:'Validate and apply quantity 1'}));await screen.findByRole('alert');expect(apply).not.toHaveBeenCalled();
 fireEvent.change(screen.getByLabelText('Actual measured base quantity 1'),{target:{value:'24'}});fireEvent.click(screen.getByRole('button',{name:'Validate and apply quantity 1'}));await screen.findByText(/Applied 24.0000/);
 expect(apply).toHaveBeenCalledWith({entered_unit_id:id(5),unit_revision_id:id(6),entered_quantity:'2',measured_base_quantity:'24'},'24.0000');
 expect(vi.mocked(request).mock.calls.at(-1)![3]).toEqual({as_of:'2026-10-31',components:[{unit_revision_id:id(6),quantity:'2',measured_base_quantity:'24'}]});
});
it('rejects a preview from another item and explicitly clears an unfinished entry',async()=>{
 const {apply}=mount();await choose();vi.mocked(request).mockResolvedValueOnce({item_id:id(99),base_unit_id:id(3),base_quantity:'24'} as never);fireEvent.click(screen.getByRole('button',{name:'Validate and apply quantity 1'}));await screen.findByText(/preview could not be verified/);expect(apply).not.toHaveBeenCalled();fireEvent.click(screen.getByRole('button',{name:'Use base quantity 1'}));expect(apply).toHaveBeenCalledWith(null);
});
it('discards a late preview after the stock-date scope is unmounted',async()=>{
 const {apply,unmount}=mount();await choose();let finish:(v:unknown)=>void=()=>{};vi.mocked(request).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;}) as never);fireEvent.click(screen.getByRole('button',{name:'Validate and apply quantity 1'}));unmount();await act(async()=>{finish({item_id:id(2),base_unit_id:id(3),base_quantity:'24.0000'});});expect(apply).not.toHaveBeenCalled();
});
