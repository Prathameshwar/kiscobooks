import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { ProductFields } from '../app/components/ProductFields';
import { ProductFieldError, productFieldRequest } from '../app/lib/product-fields';
vi.mock('../app/lib/product-fields',async original => ({...await original<typeof import('../app/lib/product-fields')>(),productFieldRequest:vi.fn()}));
vi.mock('@janso/ui',async original => ({...await original<typeof import('@janso/ui')>(),SearchSelect:({label,onChange}:{label:string;onChange:(id:string)=>void}) => <button onClick={() => onChange('item-1')}>{label}</button>}));
const api=vi.mocked(productFieldRequest);
const metadata={fields:[{key:'cf_note',source:'custom',label:'Note',visible:true,required:false,writable:true,custom:{key:'cf_note',data_type:'text',is_active:true,is_immutable_after_create:false,validation:{required:false,max_length:512},choices:[]}}]};
const owner={id:'item-1',name:'Product',row_version:1,custom_fields:{cf_note:'old'}};
beforeEach(() => {api.mockReset();api.mockImplementation(async (service,method,path) => {
  if(path.includes('field-set')) return metadata;
  if(path.includes('custom-field-contract')) return {option_sources:{'catalog.brands':{}}};
  if(path.includes('custom-field-definitions')) return {items:[],page:{next_cursor:null,has_more:false}};
  if(path.endsWith('/preview')) return {eligible:true,owner_count:1,preview_token:'signed',definitions:[],source_definition_digests:{},issues:[]};
  if(path.endsWith('/custom-field-adoption')) return {version:2,owner_count:1};
  if(method === 'PATCH') return {...owner,row_version:2,custom_fields:{cf_note:'new'}};
  return owner;
});});
it('uses page spacing and a shared card footer for editing custom values', async () => {
  const { container } = render(<ProductFields company="company" currencies={['INR']} canManage={false}/>);
  expect(container.querySelector('.janso-custom-manager')).toBeNull();
  fireEvent.click(screen.getByRole('button',{name:'Load fields'}));
  fireEvent.click(await screen.findByRole('button',{name:'Find a product'}));
  const save = await screen.findByRole('button',{name:'Save product values'});
  expect(save.closest('.janso-card__footer')).not.toBeNull();
  expect(save.closest('form')).toHaveAccessibleName('Product custom values');
});
it('loads an owner and saves only changed custom values with a version',async () => {
  render(<ProductFields company="company" currencies={['INR']} canManage={false}/>);
  fireEvent.click(screen.getByRole('button',{name:'Load fields'}));fireEvent.click(await screen.findByRole('button',{name:'Find a product'}));
  fireEvent.change(await screen.findByLabelText('Note'),{target:{value:'new'}});
  fireEvent.click(screen.getByRole('button',{name:'Save product values'}));
  expect(await screen.findByRole('status')).toHaveTextContent('saved');
  expect(api).toHaveBeenCalledWith('catalog','PATCH','/v1/companies/company/items/item-1',{expected_version:1,custom_fields:{cf_note:'new'}},expect.any(String));
  expect(screen.queryByText('Manage definitions')).not.toBeInTheDocument();
});
it('keeps the idempotency key for a failed save retry and shows field errors',async () => {
  const fallback=api.getMockImplementation()!;let fails=true;
  api.mockImplementation(async (...args) => {if(args[1] === 'PATCH' && fails) {fails=false;throw new ProductFieldError('Try again',{'custom_fields.cf_note':'Check note'});}return fallback(...args);});
  render(<ProductFields company="company" currencies={['INR']} canManage={false}/>);
  fireEvent.click(screen.getByRole('button',{name:'Load fields'}));fireEvent.click(await screen.findByRole('button',{name:'Find a product'}));
  fireEvent.change(await screen.findByLabelText('Note'),{target:{value:'new'}});fireEvent.click(screen.getByRole('button',{name:'Save product values'}));
  expect(await screen.findByRole('status')).toHaveTextContent('Try again');expect(screen.getByRole('alert')).toHaveTextContent('Check note');
  fireEvent.click(screen.getByRole('button',{name:'Save product values'}));await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('saved'));
  const saves=api.mock.calls.filter(call => call[1] === 'PATCH');expect(saves[0]?.[4]).toBe(saves[1]?.[4]);
});
it('reviews before adopting and resets owner values afterwards',async () => {
  render(<ProductFields company="company" currencies={['INR']} canManage/>);
  fireEvent.click(screen.getByRole('button',{name:'Load fields'}));fireEvent.click(await screen.findByRole('button',{name:'Review pending changes'}));
  expect(await screen.findByText('1 existing products checked.')).toBeInTheDocument();fireEvent.click(screen.getByRole('button',{name:'Adopt reviewed definitions'}));
  expect(await screen.findByRole('status')).toHaveTextContent('adopted');
  expect(api).toHaveBeenCalledWith('catalog','POST','/v1/companies/company/entities/catalog.item/custom-field-adoption',{preview_token:'signed'},expect.any(String));
});
it('creates a candidate and clears loaded state when the owner type changes',async () => {
  render(<ProductFields company="company" currencies={['INR']} canManage/>);
  fireEvent.click(screen.getByRole('button',{name:'Load fields'}));fireEvent.click(await screen.findByRole('button',{name:'Add field'}));
  fireEvent.change(screen.getByLabelText('Field label'),{target:{value:'Note'}});fireEvent.change(screen.getByLabelText('Stable field key'),{target:{value:'cf_note'}});
  fireEvent.submit(screen.getByRole('button',{name:'Save candidate'}).closest('form')!);
  expect(await screen.findByRole('status')).toHaveTextContent('Candidate saved');
  fireEvent.change(screen.getByLabelText('Field owner'),{target:{value:'catalog.product_family'}});expect(screen.queryByRole('button',{name:'Find a product'})).not.toBeInTheDocument();
});

it('refuses adoption review until Identity definitions reach Catalog',async () => {
  const fallback=api.getMockImplementation()!;
  api.mockImplementation(async (...args) => {
    if(args[2].includes('custom-field-definitions')) return {items:[{id:'definition',digest:'new'}],page:{next_cursor:null,has_more:false}};
    if(args[2].endsWith('/preview')) return {eligible:true,owner_count:0,preview_token:'signed',definitions:[],source_definition_digests:{definition:'old'},issues:[]};
    return fallback(...args);
  });
  render(<ProductFields company="company" currencies={['INR']} canManage/>);
  fireEvent.click(screen.getByRole('button',{name:'Load fields'}));fireEvent.click(await screen.findByRole('button',{name:'Review pending changes'}));
  expect(await screen.findByRole('status')).toHaveTextContent('synchronizing');
  expect(screen.queryByRole('button',{name:'Adopt reviewed definitions'})).not.toBeInTheDocument();
});
