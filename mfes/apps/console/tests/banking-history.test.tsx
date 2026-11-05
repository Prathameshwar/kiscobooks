import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {beforeEach,expect,it,vi} from 'vitest';
import {BankingHistory} from '../app/components/BankingHistory';
import {productFieldRequest} from '../app/lib/product-fields';
vi.mock('../app/lib/product-fields',()=>({productFieldRequest:vi.fn()}));
const api=vi.mocked(productFieldRequest),permissions=['accounting.bank.read','accounting.bank.manage'];
beforeEach(()=>{
 api.mockReset();api.mockImplementation(async(_,method,path)=>{
  if(path.includes('field-sets'))return {fields:['expected_event_id','action','event_date','reason','reference'].map(key=>({key,writable:true,readable:true,definition:key==='action'?{enum:['CLEARED','RECONCILED']}:{}}))};
  if(method==='POST')return {id:'clear',action:'CLEARED',event_date:'2026-04-03'};
  if(path.includes('/events'))return {items:[{id:'book',action:'BOOKED',event_date:'2026-04-02'}],page:{next_cursor:null}};
  return {items:[{id:'instrument',mode:'CHEQUE',booking_date:'2026-04-02',amount:'100.2500',currency:'INR'}],page:{next_cursor:null}};
 });
});
async function select(){fireEvent.click(screen.getByText('Load payment instruments'));fireEvent.click(await screen.findByRole('button',{name:/CHEQUE/}));await screen.findByText('Instrument: instrument');}
it('hides history without owner permission and prevents read-only users from writing',async()=>{
 const view=render(<BankingHistory company="company" permissions={[]}/>);expect(screen.queryByRole('button')).not.toBeInTheDocument();
 view.rerender(<BankingHistory company="company" permissions={['accounting.bank.read']}/>);await select();expect(screen.queryByText('Record bank event')).not.toBeInTheDocument();
 fireEvent.click(screen.getByText('Refresh instrument history'));await waitFor(()=>expect(api.mock.calls.filter(call=>call[2].includes('/events'))).toHaveLength(2));
});
it('records dated evidence against the last event, preserving a failed request key',async()=>{
 const base=api.getMockImplementation()!;let attempts=0;
 api.mockImplementation(async(...args)=>args[1]==='POST'&&attempts++===0?Promise.reject(new Error('Offline')):base(...args));
 render(<BankingHistory company="company" permissions={permissions}/>);await select();expect(screen.getByText('Record bank event')).toBeDisabled();
 fireEvent.change(screen.getByLabelText('Bank action'),{target:{value:'CLEARED'}});
 fireEvent.change(screen.getByLabelText('Bank event date'),{target:{value:'2026-04-03'}});
 fireEvent.change(screen.getByLabelText('Bank evidence reference'),{target:{value:'BANK-REF'}});
 fireEvent.change(screen.getByLabelText('Bank event reason'),{target:{value:'Statement reviewed'}});
 fireEvent.click(screen.getByText('Record bank event'));expect(await screen.findByRole('status')).toHaveTextContent('Offline');
 fireEvent.click(screen.getByText('Record bank event'));await screen.findByText('Bank history recorded.');
 const calls=api.mock.calls.filter(call=>call[1]==='POST');expect(calls[0][4]).toBe(calls[1][4]);
 expect(calls[1][3]).toEqual({expected_event_id:'book',action:'CLEARED',event_date:'2026-04-03',reference:'BANK-REF',reason:'Statement reviewed'});
 expect(screen.getAllByRole('listitem')).toHaveLength(3);
});
it('does not append from an incomplete history or denied required fields',async()=>{
 const base=api.getMockImplementation()!;
 api.mockImplementation(async(...args)=>args[2].includes('/events')?{items:[{id:args[2].includes('cursor')?'presented':'book',action:'BOOKED'}],page:{next_cursor:args[2].includes('cursor')?null:'next'}}:args[2].includes('field-sets')?{fields:[{key:'action',writable:false,readable:true,definition:{}}]}:base(...args));
 render(<BankingHistory company="company" permissions={permissions}/>);await select();
 expect(screen.getByText('Record bank event')).toBeDisabled();expect(screen.queryByLabelText('Bank action')).not.toBeInTheDocument();
 fireEvent.click(screen.getByText('More instrument history'));await waitFor(()=>expect(screen.queryByText('More instrument history')).not.toBeInTheDocument());
 expect(screen.getByText('Record bank event')).toBeDisabled();
});
it('reports read failures and remains retryable',async()=>{api.mockRejectedValue(new Error('Access revoked'));render(<BankingHistory company="company" permissions={permissions}/>);fireEvent.click(screen.getByText('Load payment instruments'));expect(await screen.findByRole('status')).toHaveTextContent('Access revoked');expect(screen.getByText('Load payment instruments')).toBeEnabled();});
