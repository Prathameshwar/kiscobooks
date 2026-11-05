import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {beforeEach,expect,it,vi} from 'vitest';
import {useState} from 'react';
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {VoucherMoney,type MoneyInput} from '../app/components/VoucherMoney';
import type {FieldSet} from '../app/lib/voucher-fields';
import {productFieldRequest} from '../app/lib/product-fields';
vi.mock('../app/lib/product-fields',()=>({productFieldRequest:vi.fn()}));
vi.mock('@janso/ui',async original=>({...await original<typeof import('@janso/ui')>(),SearchSelect:({label,loadOptions,onChange,disabled}:{label:string;loadOptions:import('@janso/ui').SearchSelectLoader;onChange:(id:string)=>void;disabled:boolean})=><button type="button" disabled={disabled} onClick={async()=>{const page=await loadOptions({q:'',cursor:null,signal:new AbortController().signal});if(page.items[0]&&!page.items[0].disabled)onChange(page.items[0].id);}}>{label}</button>}));
const api=vi.mocked(productFieldRequest);
const metadata={native:{properties:{financial:{}}},custom:[],configuration:{kind:'JOURNAL',profile:'STANDARD',type_revision_id:'type',policy:{financial:{max_account_entries:2,foreign_currency_allowed:true,settlement_adjustments_allowed:true},forbidden_sections:[]}}} as unknown as FieldSet;
function Form({meta=metadata,disabled=false}:{meta?:FieldSet;disabled?:boolean}){
 const [value,setValue]=useState<MoneyInput|null>(null);
 return <><VoucherMoney company="company" currency="INR" metadata={meta} value={value} onChange={setValue} disabled={disabled}/><output data-testid="value">{JSON.stringify(value)}</output></>;
}
const value=()=>JSON.parse(screen.getByTestId('value').textContent!);
beforeEach(()=>api.mockReset());
it('uses the shared borderless account grouping rather than browser-default fieldset chrome', () => {
 const style=document.createElement('style');style.textContent=readFileSync(resolve(process.cwd(),'../../packages/ui/src/styles/janso-ui.css'),'utf8');document.head.append(style);
 try {
  render(<Form/>);fireEvent.click(screen.getByRole('button',{name:'Add account entry'}));
  const group=screen.getByRole('group',{name:'Account entry 1'});
  expect(getComputedStyle(group).borderTopWidth).toBe('0px');
  expect(group).toContainElement(screen.getByLabelText('Amount 1'));
 } finally { style.remove(); }
});
it('records exact amounts and account versions, bank details and tracked bill targets',async()=>{
 api.mockResolvedValue({items:[{id:'bank',name:'Main Bank',kind:'BANK',row_version:4}],page:{next_cursor:null}});
 render(<Form/>);fireEvent.click(screen.getByText('Add account entry'));
 fireEvent.click(screen.getByText('Account 1'));await waitFor(()=>expect(value().accounts[0].source_version).toBe(4));
 const key=value().accounts[0].line_key;
 fireEvent.change(screen.getByLabelText('Amount 1'),{target:{value:'900719925474.1234'}});
 fireEvent.change(screen.getByLabelText('Currency 1'),{target:{value:'USD'}});
 fireEvent.change(screen.getByLabelText('Exchange rate 1'),{target:{value:'83.12345678'}});
 fireEvent.change(screen.getByLabelText('Entry description 1'),{target:{value:'Bank settlement'}});
 fireEvent.change(screen.getByLabelText('Amount purpose 1'),{target:{value:'PRINCIPAL'}});
 fireEvent.click(screen.getByText('Add payment detail 1'));
 fireEvent.change(screen.getByLabelText('Payment mode 1'),{target:{value:'CHEQUE'}});
 expect(screen.getByLabelText('Payment reference 1')).not.toBeRequired();
 fireEvent.change(screen.getByLabelText('Payment reference 1'),{target:{value:'CHQ-001'}});
 fireEvent.change(screen.getByLabelText('Instrument date 1'),{target:{value:'2026-04-12'}});
 fireEvent.change(screen.getByLabelText('Recognition 1'),{target:{value:'MATURITY_DATE'}});
 expect(value().tenders[0]).toMatchObject({line_key:key,amount:'900719925474.1234',currency:'USD',reference:'CHQ-001',recognition:'MATURITY_DATE'});
 fireEvent.click(screen.getByText('Add account entry'));expect(screen.getByText('Add account entry')).toBeDisabled();
 fireEvent.change(screen.getByLabelText('Bill tracking 2'),{target:{value:'NEW_REF'}});
 expect(screen.getByLabelText('Bill reference 2')).toBeRequired();
 // Optional: Accounting dates a new bill on the voucher date when no due date is given.
 expect(screen.getByLabelText('Due date 2')).not.toBeRequired();
 fireEvent.change(screen.getByLabelText('Bill reference 2'),{target:{value:'BILL-001'}});
 fireEvent.change(screen.getByLabelText('Due date 2'),{target:{value:'2026-05-01'}});
 fireEvent.click(screen.getByText('Add bill adjustment'));
 fireEvent.change(screen.getByLabelText('Allocation currency 1'),{target:{value:'USD'}});
 fireEvent.change(screen.getByLabelText('debt target 1'),{target:{value:value().accounts[1].line_key}});
 fireEvent.change(screen.getByLabelText('Allocation amount 1'),{target:{value:'42.1234'}});
 expect(value().allocations[0].amount).toBe('42.1234');
 fireEvent.click(screen.getByText('Remove account 2'));expect(value().allocations).toEqual([]);
 fireEvent.click(screen.getByText('Remove account 1'));expect(value().tenders).toEqual([]);
});
it('supports pure bill adjustments with matching currency and direction lookups',async()=>{
 api.mockResolvedValue({items:[{id:'bill',reference:'REF',currency:'INR'}],page:{next_cursor:null}});
 render(<Form/>);
 fireEvent.change(screen.getByLabelText('Transaction purpose'),{target:{value:'BILL_ADJUSTMENT'}});
 expect(screen.queryByText('Add account entry')).not.toBeInTheDocument();
 fireEvent.click(screen.getByText('Add bill adjustment'));fireEvent.click(screen.getByText('debt bill 1'));
 await waitFor(()=>expect(value().allocations[0].debt.item_id).toBe('bill'));
 expect(api.mock.calls.at(-1)?.[2]).toContain('direction=DEBT');
 fireEvent.click(screen.getByText('credit bill 1'));await waitFor(()=>expect(value().allocations[0].credit.item_id).toBe('bill'));
 fireEvent.click(screen.getByText('Remove bill adjustment 1'));expect(value().allocations).toEqual([]);
});
it.each(['SALES','CONTRA','PAYMENT'])('honors metadata and profile controls for %s',kind=>{
 render(<Form meta={{...metadata,configuration:{...metadata.configuration,kind,profile:kind==='PAYMENT'?'ADVANCE':'STANDARD',policy:{...metadata.configuration.policy,forbidden_sections:['ACCOUNTS','TENDERS','BILL_ALLOCATIONS']}}}}/>);
 expect(screen.queryByText('Add account entry')).not.toBeInTheDocument();expect(screen.queryByText('Add bill adjustment')).not.toBeInTheDocument();
 if(kind==='SALES')expect(screen.queryByText('Accounts and settlement')).not.toBeInTheDocument();
 else expect(screen.getByLabelText('Transaction purpose')).toHaveValue(kind==='CONTRA'?'TRANSFER':'ADVANCE');
});
it('honors whole-section read restrictions and pending form state',()=>{
 const view=render(<Form meta={{...metadata,native:{properties:{financial:{readOnly:true}}}}}/>);
 expect(screen.queryByText('Accounts and settlement')).not.toBeInTheDocument();
 view.rerender(<Form disabled/>);expect(screen.getByText('Add account entry')).toBeDisabled();
});
it('applies typed money configuration to purpose, tender choices and tender count',async()=>{
 api.mockResolvedValue({items:[{id:'bank',name:'Main Bank',kind:'BANK',row_version:4}],page:{next_cursor:null}});
 render(<Form meta={{...metadata,configuration:{...metadata.configuration,kind:'PAYMENT',policy:{...metadata.configuration.policy,money:{allowed_purposes:['GENERAL'],allowed_tender_modes:['NEFT'],max_tenders:1}}}}}/>);
 expect(screen.getAllByRole('option').map(option=>option.textContent)).not.toContain('REFUND');
 fireEvent.click(screen.getByText('Add account entry'));fireEvent.click(screen.getByText('Account 1'));
 await waitFor(()=>expect(value().accounts[0].source_version).toBe(4));
 fireEvent.change(screen.getByLabelText('Amount 1'),{target:{value:'42.1234'}});
 fireEvent.click(screen.getByText('Add payment detail 1'));
 expect(value().tenders[0].mode).toBe('NEFT');
 expect(screen.getByLabelText('Payment mode 1').querySelectorAll('option')).toHaveLength(1);
 expect(screen.getByText('Add payment detail 1')).toBeDisabled();
});
