import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {beforeEach,expect,it,vi} from 'vitest';
import {ReportReference} from '../app/components/ReportReference';
import {reportLookup,reportReference} from '../app/lib/report-references';
import {productFieldRequest} from '../app/lib/product-fields';
vi.mock('../app/lib/product-fields',()=>({productFieldRequest:vi.fn()}));
const api=vi.mocked(productFieldRequest),id='01800000-0000-7000-8000-000000000001',company='01800000-0000-7000-8000-000000000002';
beforeEach(()=>{api.mockReset();});
const query=(q='')=>({q,cursor:null,signal:new AbortController().signal});
it('uses Catalog item groups, bounded cursor paging and historical masters',async()=>{
  api.mockResolvedValue({items:[{id,name:'Historical item group',is_active:false}],page:{next_cursor:'signed-next'}});
  const result=await reportLookup(company,'item-groups')({q:'  old  ',cursor:'signed-prior',signal:new AbortController().signal});
  expect(api).toHaveBeenCalledWith('catalog','GET',expect.stringContaining('/item-groups?'),undefined,undefined,expect.any(AbortSignal));
  const query=new URLSearchParams(api.mock.calls[0][2].split('?')[1]);
  expect(Object.fromEntries(query)).toEqual({limit:'50',q:'old',cursor:'signed-prior'});
  expect(result).toMatchObject({items:[{id,label:'Historical item group'}],nextCursor:'signed-next'});
});
it('uses the native Accounting batch resource and omits an absent optional product filter',async()=>{
  api.mockResolvedValue({items:[],page:{next_cursor:null}});
  await reportLookup(company,'batches')(query());
  expect(api.mock.calls[0].slice(0,3)).toEqual(['accounting','GET','/v1/companies/'+company+'/stock-tracking/batches?limit=50']);
  await reportLookup(company,'batches',id)(query());
  expect(api.mock.calls[1][2]).toContain('item_id='+id);
});
it('loads historical voucher types from Vouchers without an active-only filter',async()=>{
  api.mockResolvedValue({items:[{id,company_id:company,name:'Former purchase type',code:'PUR_OLD',status:'INACTIVE'}],page:{next_cursor:null}});
  expect(await reportLookup(company,'voucher-types')(query('PUR'))).toMatchObject({items:[{id,label:'Former purchase type',meta:'PUR_OLD'}]});
  expect(api.mock.calls[0].slice(0,3)).toEqual(['vouchers','GET','/v1/companies/'+company+'/voucher-types?limit=50&q=PUR']);
});
it('rejects malformed and foreign-company choices before displaying them',async()=>{
  api.mockResolvedValue({items:[{id:'invalid',name:'Wrong'}],page:{next_cursor:null}});
  await expect(reportLookup(company,'warehouses')(query())).rejects.toThrow(/ownership/);
  api.mockResolvedValue({items:[{id,company_id:'another-company'}],page:{next_cursor:null}});
  await expect(reportLookup(company,'items')(query())).rejects.toThrow(/ownership/);
});
it('hydrates only the requested same-company retained reference',async()=>{
  api.mockResolvedValue({id,company_id:company,name:'Retained account'});
  expect(await reportReference(company,'accounts',id,new AbortController().signal)).toMatchObject({id,label:'Retained account'});
  api.mockResolvedValue({id,company_id:'other'});
  await expect(reportReference(company,'accounts',id,new AbortController().signal)).rejects.toThrow(/ownership/);
});
it('bounds search text and refuses invalid batch parent IDs before an API read',async()=>{
  await expect(reportLookup(company,'items')(query('x'.repeat(201)))).rejects.toThrow(/200/);
  await expect(reportLookup(company,'batches','invalid')(query())).rejects.toThrow(/valid product/);
  expect(api).not.toHaveBeenCalled();
});
it('refuses responses that exceed the page bound or omit native cursor metadata',async()=>{
  api.mockResolvedValue({items:Array.from({length:51},()=>({id,name:'Group'})),page:{next_cursor:null}});
  await expect(reportLookup(company,'item-groups')(query())).rejects.toThrow(/could not be loaded/);
  api.mockResolvedValue({items:[],page:{}});
  await expect(reportLookup(company,'items')(query())).rejects.toThrow(/could not be loaded/);
});
it('shows a retained human-readable option and lets the user choose a new scoped reference',async()=>{
  api.mockImplementation(async(_,__,path)=>path.includes('?')?{items:[{id,name:'New group'}],page:{next_cursor:null}}:{id,company_id:company,name:'Retained group'});
  const change=vi.fn();
  render(<ReportReference company={company} code="STOCK_SUMMARY" source="item-groups" label="Item group" value={id} onChange={change} disabled={false} required={false}/>);
  const control=await screen.findByRole('combobox',{name:'Item group'});
  await waitFor(()=>expect(control).toHaveValue('Retained group'));
  fireEvent.focus(control);fireEvent.change(control,{target:{value:'New'}});
  fireEvent.click(await screen.findByRole('option',{name:'New group'}));expect(change).toHaveBeenCalledWith(id);
});
it('displays scope failures and aborts old hydration when the company changes',async()=>{
  let signal:AbortSignal|undefined;
  api.mockImplementation(async(...args)=>{signal=args[5];throw new Error('Report reference ownership could not be verified.');});
  const props={code:'STOCK_SUMMARY',source:'item-groups' as const,label:'Item group',value:id,onChange:vi.fn(),disabled:false,required:false};
  const rendered=render(<ReportReference {...props} company={company}/>);
  expect(await screen.findByText(/ownership could not be verified/)).toBeVisible();
  const prior=signal;rendered.rerender(<ReportReference {...props} company="other"/>);
  expect(prior?.aborted).toBe(true);
  await waitFor(()=>expect(api).toHaveBeenCalledTimes(2));
  expect(await screen.findByText(/ownership could not be verified/)).toBeVisible();
});
it('keeps a refused retained reference unavailable for execution',async()=>{
  api.mockRejectedValue(new Error('Report reference ownership could not be verified.'));
  const state=vi.fn();
  render(<ReportReference company={company} code="PARTY_LEDGER" source="parties" label="Party" value={id} onChange={vi.fn()} disabled={false} required onStateChange={state}/>);
  await screen.findByText(/ownership could not be verified/);
  expect(state).toHaveBeenLastCalledWith(false);
});
