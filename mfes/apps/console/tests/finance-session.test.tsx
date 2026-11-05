import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {beforeEach,expect,it,vi} from 'vitest';
import {FinanceSessionReference} from '../app/components/FinanceSessionReference';
import {productFieldRequest} from '../app/lib/product-fields';
import {allowedProductRequest} from '../app/lib/product-request-policy';
import {uuid} from './trial-balance-fixture';
vi.mock('../app/lib/product-fields',()=>({productFieldRequest:vi.fn()}));
const api=vi.mocked(productFieldRequest),company=uuid(1),account=uuid(2),session=uuid(3);
const row={id:session,company_id:company,account_id:account,currency:'INR',period_from:'2026-04-01',period_to:'2026-04-30',status:'FINALIZED'};
beforeEach(()=>api.mockReset());
it('offers labelled finalised sessions and excludes drafts',async()=>{
 api.mockResolvedValue([row,{...row,id:uuid(4),status:'DRAFT'}]);const change=vi.fn();
 render(<FinanceSessionReference company={company} account={account} value="" disabled={false} onChange={change} onReady={()=>{}}/>);
 fireEvent.focus(screen.getByRole('combobox'));const option=await screen.findByRole('option',{name:/Apr 2026/});fireEvent.click(option);
 expect(change).toHaveBeenCalledWith(session);expect(api.mock.calls[0][2]).toContain('account_id='+account);
});
it('does not load sessions until a bank account is selected',()=>{
 render(<FinanceSessionReference company={company} account="" value="" disabled={false} onChange={()=>{}} onReady={()=>{}}/>);
 expect(screen.getByRole('combobox')).toBeDisabled();expect(api).not.toHaveBeenCalled();
});
it('provides verified session dates and currency to the report',async()=>{
 api.mockResolvedValue(row);const scope=vi.fn();
 render(<FinanceSessionReference company={company} account={account} value={session} disabled={false} onChange={()=>{}} onReady={()=>{}} onScope={scope}/>);
 await waitFor(()=>expect(scope).toHaveBeenCalledWith(row));
});
it('rejects a retained session from another company',async()=>{
 api.mockResolvedValue({...row,company_id:uuid(99)});const ready=vi.fn();
 render(<FinanceSessionReference company={company} account={account} value={session} disabled={false} onChange={()=>{}} onReady={ready}/>);
 await screen.findByText(/different account/);expect(ready).not.toHaveBeenCalledWith(true);
});
it('allows only scoped read-only session endpoints',()=>{
 const base='/v1/companies/'+company+'/bank-reconciliation/sessions';
 expect(allowedProductRequest('accounting','GET',base+'?account_id='+account+'&limit=50')).toBe(true);
 expect(allowedProductRequest('accounting','GET',base+'/'+session)).toBe(true);
 expect(allowedProductRequest('accounting','POST',base)).toBe(false);
 expect(allowedProductRequest('accounting','GET',base+'?account_id='+account+'&limit=500')).toBe(false);
 expect(allowedProductRequest('accounting','GET',base+'?account_id='+account+'&account_id='+uuid(99))).toBe(false);
 expect(allowedProductRequest('accounting','POST',base+'/'+session+'/finalize')).toBe(false);
});
