import {fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {beforeEach,expect,it,vi} from 'vitest';
import {ReportsHub} from '../app/components/ReportsHub';
import {productFieldRequest} from '../app/lib/product-fields';

vi.mock('../app/lib/product-fields',()=>({productFieldRequest:vi.fn()}));
const company='01990000-0000-7000-8000-000000000001';
const reports=[
 ['SALES_PERFORMANCE','Sales performance'],
 ['PROFIT_MARGIN_ANALYSIS','Profit and margin analysis'],
 ['BUYER_PROFIT','Party (buyer) wise profit'],
 ['PRODUCT_PROFIT','Product wise profit'],
 ['CUSTOMER_INSIGHTS','Customer insights'],
 ['EXPENSE_PROFIT_LEAKAGE','Expense and profit leakage'],
 ['CASH_WORKING_CAPITAL','Cash and working capital'],
] as const;
const definition=(code:string,run_enabled=true)=>({definition:{code,version:1},run_enabled});
const catalogue=()=>({items:reports.map(([code])=>definition(code))});
beforeEach(()=>{vi.mocked(productFieldRequest).mockReset();});
const mount=()=>render(<ReportsHub company={company} category="analytics"/>);

it('opens all seven business analytics cards in their own report workspaces',async()=>{
 vi.mocked(productFieldRequest).mockResolvedValue(catalogue());mount();
 expect(screen.getByRole('heading',{level:1,name:'Analytics'})).toBeVisible();
 for(const [code,title] of reports)expect(await screen.findByRole('link',{name:title})).toHaveAttribute('href','/reports/workspace?report='+code);
 expect(screen.getByRole('link',{name:'Analytics'})).toHaveAttribute('aria-current','page');
 expect(screen.queryByRole('heading',{name:'Stock summary'})).not.toBeInTheDocument();
});

it('finds report cards by business purpose and clears the search',async()=>{
 vi.mocked(productFieldRequest).mockResolvedValue(catalogue());mount();
 await screen.findByRole('link',{name:'Customer insights'});
 fireEvent.change(screen.getByRole('searchbox',{name:'Search reports'}),{target:{value:'repeat purchasing'}});
 await waitFor(()=>expect(screen.getAllByRole('heading',{level:3})).toHaveLength(1));
 expect(screen.getByRole('link',{name:'Customer insights'})).toBeVisible();
 fireEvent.click(screen.getByRole('button',{name:'Clear search'}));
 for(const [,title] of reports)expect(await screen.findByRole('link',{name:title})).toBeVisible();
});

it('shows authorized cards and hides reports excluded by the company catalogue',async()=>{
 vi.mocked(productFieldRequest).mockResolvedValue({items:[definition('SALES_PERFORMANCE')]});mount();
 expect(await screen.findByRole('link',{name:'Sales performance'})).toBeVisible();
 expect(screen.queryByRole('heading',{name:'Cash and working capital'})).not.toBeInTheDocument();
 expect(screen.queryByText('Profit and margin analysis')).not.toBeInTheDocument();
});

it('keeps the business analytics cards disabled while availability is loading',()=>{
 vi.mocked(productFieldRequest).mockReturnValue(new Promise(()=>{}));mount();
 for(const [,title] of reports){
  const card=screen.getByRole('heading',{level:3,name:title}).closest('article')!;
  expect(within(card).getByRole('button')).toBeDisabled();
  expect(screen.queryByRole('link',{name:title})).not.toBeInTheDocument();
 }
});

it('keeps business analytics cards disabled during an outage and enables them after retry',async()=>{
 vi.mocked(productFieldRequest).mockRejectedValueOnce({status:503,message:'Reports unavailable'}).mockResolvedValue(catalogue());mount();
 const retry=await screen.findByRole('button',{name:'Retry report availability'});
 for(const [,title] of reports){
  const card=screen.getByRole('heading',{level:3,name:title}).closest('article')!;
  expect(within(card).getByRole('button',{name:'Report service unavailable'})).toBeDisabled();
  expect(screen.queryByRole('link',{name:title})).not.toBeInTheDocument();
 }
 fireEvent.click(retry);
 for(const [,title] of reports)expect(await screen.findByRole('link',{name:title})).toBeVisible();
 expect(productFieldRequest).toHaveBeenCalledTimes(2);
});

it.each([401,403])('keeps protected analytics cards hidden after a %s response',async status=>{
 vi.mocked(productFieldRequest).mockRejectedValue({status,message:'Access denied'});mount();
 await screen.findByRole('button',{name:'Retry report availability'});
 for(const [,title] of reports)expect(screen.queryByRole('heading',{name:title})).not.toBeInTheDocument();
});

it('allows opening completed analytics reports when new runs are disabled',async()=>{
 vi.mocked(productFieldRequest).mockResolvedValue({items:[definition('SALES_PERFORMANCE',false)]});mount();
 const card=await screen.findByRole('link',{name:'Sales performance'});
 expect(card).toHaveTextContent('View completed reports');
 await waitFor(()=>expect(screen.queryByText('Checking report availability…')).not.toBeInTheDocument());
});
