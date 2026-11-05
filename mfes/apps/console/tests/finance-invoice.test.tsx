import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {beforeEach,expect,it,vi} from 'vitest';
import {FinanceInvoiceReference} from '../app/components/FinanceInvoiceReference';
import {productFieldRequest} from '../app/lib/product-fields';
import {allowedProductRequest} from '../app/lib/product-request-policy';
import {uuid} from './trial-balance-fixture';
vi.mock('../app/lib/product-fields',()=>({productFieldRequest:vi.fn()}));
const api=vi.mocked(productFieldRequest),company=uuid(1),invoice=uuid(2);
const row={id:invoice,company_id:company,bill_reference:'SALE-2026-42',kind:'SALES',currency:'INR',posting_date:'2026-04-03'};
beforeEach(()=>api.mockReset());
it('selects a posted invoice by its reference and scopes the list by posting period',async()=>{
 api.mockResolvedValue({items:[row],page:{next_cursor:'more'}});const change=vi.fn();
 render(<FinanceInvoiceReference company={company} value="" from="2026-04-01" to="2026-04-30" disabled={false} onChange={change} onReady={()=>{}}/>);
 fireEvent.focus(screen.getByRole('combobox'));fireEvent.click(await screen.findByRole('option',{name:/SALE-2026-42/}));
 expect(change).toHaveBeenCalledWith(invoice);expect(api.mock.calls[0][2]).toContain('date_from=2026-04-01');
});
it('rejects a retained invoice from another company',async()=>{
 api.mockResolvedValue({...row,company_id:uuid(99)});const ready=vi.fn();
 render(<FinanceInvoiceReference company={company} value={invoice} disabled={false} onChange={()=>{}} onReady={ready}/>);
 await screen.findByText(/ownership could not be verified/);expect(ready).not.toHaveBeenCalledWith(true);
});
it('permits only bounded read-only invoice lookup paths',()=>{
 const path='/v1/companies/'+company+'/invoice-records';
 expect(allowedProductRequest('accounting','GET',path+'?limit=50&date_to=2026-04-30')).toBe(true);
 expect(allowedProductRequest('accounting','GET',path+'/'+invoice)).toBe(true);
 expect(allowedProductRequest('accounting','POST',path)).toBe(false);
 expect(allowedProductRequest('accounting','GET',path+'?limit=500')).toBe(false);
 expect(allowedProductRequest('accounting','GET',path+'?company_id='+uuid(99))).toBe(false);
});
