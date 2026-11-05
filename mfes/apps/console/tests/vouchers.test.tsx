import {fireEvent,render,screen} from '@testing-library/react';
import {beforeEach,expect,it,vi} from 'vitest';
import {VoucherEntry} from '../app/components/VoucherEntry';
import {productFieldRequest} from '../app/lib/product-fields';
import {allowedVoucherRequest} from '../app/lib/voucher-request-policy';
import {serviceCall} from '../app/lib/service-call';
vi.mock('../app/lib/service-call',async original=>({...await original<typeof import('../app/lib/service-call')>(),serviceCall:vi.fn()}));
vi.mock('../app/lib/product-fields',()=>({productFieldRequest:vi.fn()}));
vi.mock('@janso/ui',async original=>({...await original<typeof import('@janso/ui')>(),Select:({label,onChange,options}:{label:string;onChange:(value:string)=>void;options:{value:string;label:string}[]})=><select aria-label={label} onChange={event=>onChange(event.target.value)}><option value=""/>{options.map(option=><option key={option.value} value={option.value}>{option.label}</option>)}</select>}));
const api=vi.mocked(productFieldRequest);
const SAVED='01990000-0000-7000-8000-000000000002';
beforeEach(()=>{vi.mocked(serviceCall).mockImplementation(async(_endpoint,request)=>api('vouchers',request.method??'GET',request.path,request.body,request.key) as never);api.mockReset();api.mockImplementation(async(_,method,path)=>{
  if(path.includes('field-set'))return {native:{properties:{narration:{}}},custom:[],configuration:{type_revision_id:'revision',policy:{default_narration:'Configured'}}};
  if(method==='POST')return {id:SAVED,company_id:'company'};
  return {items:[{id:'type',name:'Memo'}]};
});});
async function load(){fireEvent.click(screen.getByRole('button',{name:'Load voucher types'}));await screen.findByRole('option',{name:'Memo'});fireEvent.change(screen.getByLabelText('Voucher type'),{target:{value:'type'}});fireEvent.change(screen.getByLabelText('Document date'),{target:{value:'2026-04-01'}});fireEvent.click(screen.getByRole('button',{name:'Load entry fields'}));await screen.findByLabelText('Narration');}
it('loads configured fields and saves a typed draft',async()=>{
  render(<VoucherEntry company="company" currency="INR" canCreate/>);await load();
  expect(screen.getByLabelText('Narration')).toHaveValue('Configured');
  fireEvent.click(screen.getByRole('button',{name:'Save draft'}));
  expect(await screen.findByRole('status')).toHaveTextContent('Draft saved: '+SAVED);
  expect(api).toHaveBeenCalledWith('vouchers','POST','/v1/companies/company/vouchers',{type_revision_id:'revision',document_date:'2026-04-01',currency:'INR',narration:'Configured',custom_fields:{}},expect.any(String));
});
it('retains retry identity and displays failure',async()=>{
  const fallback=api.getMockImplementation()!;let failed=false;
  api.mockImplementation(async(...args)=>{if(args[1]==='POST'&&!failed){failed=true;throw {status:503,message:'Temporarily unavailable'};}return fallback(...args);});
  render(<VoucherEntry company="company" currency="INR" canCreate/>);await load();
  fireEvent.click(screen.getByRole('button',{name:'Save draft'}));expect(await screen.findByText(/Temporarily unavailable/)).toBeVisible();
  fireEvent.click(screen.getByRole('button',{name:'Retry the same save'}));expect(await screen.findByRole('status')).toHaveTextContent('Draft saved');
  const saves=api.mock.calls.filter(call=>call[1]==='POST');expect(saves[0][4]).toBe(saves[1][4]);
});
it('sends native quotation terms and planned units without a posting date',async()=>{
 api.mockImplementation(async(_,method,path)=>{
   if(path.includes('field-set'))return {native:{properties:{narration:{},mode:{},posting_date:{},fulfillment_terms:{},lines:{items:{properties:{description:{},item:{properties:{planned_quantity:{}}}}}}}},custom:[],configuration:{kind:'SALES_ORDER',profile:'QUOTATION',type_revision_id:'revision',policy:{default_narration:'Quote',max_lines:5,forbidden_sections:[]}}};
   if(method==='POST')return {id:SAVED,company_id:'company'};
   return {items:[{id:'type',name:'Memo'}]};
 });
 render(<VoucherEntry company="company" currency="INR" canCreate/>);await load();
 expect(screen.queryByLabelText('Posting date')).not.toBeInTheDocument();
 fireEvent.change(screen.getByLabelText('Quote valid until'),{target:{value:'2026-04-30'}});
 fireEvent.click(screen.getByRole('button',{name:'Add item'}));
 fireEvent.change(screen.getByLabelText('Planned quantity 1'),{target:{value:'10'}});
 fireEvent.click(screen.getByRole('button',{name:'Save draft'}));await screen.findByText('Draft saved: '+SAVED);
 const body=api.mock.calls.find(row=>row[1]==='POST')?.[3] as Record<string,unknown>;
 expect(body).toMatchObject({mode:'ITEMS',fulfillment_terms:{purpose:'QUOTE',valid_until:'2026-04-30'},lines:[{item:{actual_quantity:'0',billed_quantity:'0',planned_quantity:'10'}}]});
 expect(body).not.toHaveProperty('posting_date');
});
it('does not grant create access or expose read-denied narration',async()=>{
  api.mockImplementation(async(_,method,path)=>path.includes('field-set')?{native:{properties:{}},custom:[],configuration:{type_revision_id:'revision',policy:{}}}:{items:[{id:'type',name:'Memo'}]});
  render(<VoucherEntry company="company" currency="INR" canCreate={false}/>);
  fireEvent.click(screen.getByRole('button',{name:'Load voucher types'}));await screen.findByRole('option',{name:'Memo'});fireEvent.change(screen.getByLabelText('Voucher type'),{target:{value:'type'}});fireEvent.change(screen.getByLabelText('Document date'),{target:{value:'2026-04-01'}});fireEvent.click(screen.getByRole('button',{name:'Load entry fields'}));
  expect(await screen.findByRole('button',{name:'Save draft'})).toBeDisabled();expect(screen.queryByLabelText('Narration')).not.toBeInTheDocument();
});
it('restricts the proxy to common entry routes',()=>{
  const root='/v1/companies/01900000-0000-7000-8000-000000000001';
  expect(allowedVoucherRequest('POST',root+'/vouchers')).toBe(true);
  expect(allowedVoucherRequest('POST',root+'/vouchers/01900000-0000-7000-8000-000000000002/accept')).toBe(true);
  for(const path of ['/internal/v1/sources',root+'/vouchers/../post',root+'/voucher-types%2fhidden'])expect(allowedVoucherRequest('POST',path)).toBe(false);
  expect(allowedVoucherRequest('DELETE',root+'/vouchers')).toBe(false);
});
