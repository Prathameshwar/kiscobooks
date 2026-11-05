import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {beforeEach,expect,it,vi} from 'vitest';
import {FinanceReportWorkspace} from '../app/components/FinanceReportWorkspace';
import {productFieldRequest} from '../app/lib/product-fields';
import {financeFixture} from './finance-fixture';
import {trialProps,trialJob} from './trial-balance-fixture';
import type {FinanceReportCode} from '../app/lib/finance-workspace';

vi.mock('../app/lib/product-fields',()=>({productFieldRequest:vi.fn()}));
const api=vi.mocked(productFieldRequest);
beforeEach(()=>{api.mockReset();localStorage.clear();});

it.each(['BANK_RECONCILIATION','BANK_RECONCILIATION_EVIDENCE','BANK_RECONCILIATION_WORKLIST'] as FinanceReportCode[])('%s waits for its required inputs',async code=>{
  api.mockImplementation(financeFixture(code).request as typeof productFieldRequest);
  render(<FinanceReportWorkspace {...trialProps} report={code}/>);
  await screen.findByRole('button',{name:'Apply'});
  expect(screen.getByRole('form')).toBeVisible();
  expect(api.mock.calls.some(call=>call[1]==='POST')).toBe(false);
  if(code==='BANK_RECONCILIATION_EVIDENCE')expect(screen.getByRole('combobox',{name:/Finalised reconciliation session/})).toBeDisabled();
});

it.each(['OUTSTANDING_BILLS','ADVANCES'] as FinanceReportCode[])('%s switches to party balances with matching export columns',async code=>{
  let view='default';
  api.mockImplementation(async(service,method,path,body)=>{
    if(path.endsWith('/report-runs')&&method==='POST')view=(body as {view:string}).view;
    return financeFixture(code,view).request(service,method,path,body);
  });
  render(<FinanceReportWorkspace {...trialProps} report={code} initialRun={trialJob.id}/>);
  await screen.findByText('Verified account');
  expect(screen.getByRole('columnheader',{name:'Reference'})).toBeVisible();
  fireEvent.click(screen.getByRole('radio',{name:'Balances by party'}));
  await screen.findByRole('columnheader',{name:'Net debt'});
  expect(screen.queryByRole('columnheader',{name:'Remaining'})).not.toBeInTheDocument();
  expect(api.mock.calls.find(call=>call[1]==='POST')?.[3]).toMatchObject({code,view:'party_balances'});
});

it('shows a prepared Day Book count and allows export for a pinned result',async()=>{
  const fixture=financeFixture('DAY_BOOK');
  api.mockImplementation(async(...args)=>{
    const response=await fixture.request(...args.slice(0,4) as Parameters<typeof fixture.request>);
    if(args[2].endsWith('/report-runs/'+trialJob.id))return {...fixture.job,completed_rows:0,result:{plan:{mode:'PINNED_QUERY'},evidence:{book_summary:{code:'DAY_BOOK',record_count:1,entry_count:1,amounts:{INR:{debit:'1.0000',credit:'1.0000'}}}}}};
    return response;
  });
  render(<FinanceReportWorkspace {...trialProps} report="DAY_BOOK" initialRun={trialJob.id}/>);
  await screen.findByText('Verified account');
  expect(screen.getByText('Posted entries')).toBeVisible();
  expect(screen.queryByText('Closing balance')).not.toBeInTheDocument();
  await waitFor(()=>expect(screen.getByRole('button',{name:'Print / PDF'})).toBeEnabled());
});
