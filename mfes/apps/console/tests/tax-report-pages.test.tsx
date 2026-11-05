import {beforeEach,expect,it,vi} from 'vitest';
import {render,screen} from '@testing-library/react';
import {useState} from 'react';
import Page from '../app/reports/workspace/page';
const state=vi.hoisted(()=>({allowed:true,actor:'actor',mounts:0,company:'01990000-0000-7000-8000-000000000001' as string|undefined}));
vi.mock('next/navigation',()=>({notFound:()=>{throw new Error('Not found');}}));
vi.mock('../app/lib/page-context',()=>({pageContext:async()=>({session:{user:{id:state.actor},permissions:state.allowed?['report.read']:[],company:{id:state.company,name:'Acme'},grants:[{scope_type:'company',scope_id:state.company,valid_from:'2000-01-01',valid_to:null,permissions:state.allowed?['report.read']:[]}]},context:{companies:[],fiscalYears:[],fiscalYear:null}})}));
vi.mock('../app/providers',()=>({Providers:({children}:{children:React.ReactNode})=>children}));
vi.mock('../app/components/ConsoleShell',()=>({ConsoleShell:({children}:{children:React.ReactNode})=>children}));
vi.mock('../app/components/TaxReportWorkspace',()=>({TaxReportWorkspace:({report}:{report:string})=><div>Tax workspace {report}</div>}));
vi.mock('../app/components/ReportWorkspace',()=>({ReportWorkspace:()=>{const [instance]=useState(()=>++state.mounts);return <div>Generic workspace {instance}</div>;}}));
vi.mock('../app/components/InventoryReportWorkspace',()=>({InventoryReportWorkspace:()=> <div>Inventory workspace</div>}));
beforeEach(()=>{state.allowed=true;state.actor='actor';state.mounts=0;state.company='01990000-0000-7000-8000-000000000001';});
it.each(['INVOICE_TAX_REGISTER','INVOICE_CREDIT_REGISTER','TAX_GL_BRIDGE'])('routes %s to its dedicated tax workspace',async(report)=>{render(await Page({searchParams:Promise.resolve({report})}));expect(screen.getByText('Tax workspace '+report)).toBeVisible();});
it('denies a tax workspace without current company report permission',async()=>{state.allowed=false;render(await Page({searchParams:Promise.resolve({report:'TAX_GL_BRIDGE'})}));expect(screen.getByRole('alert')).toBeVisible();expect(screen.queryByText('Tax workspace TAX_GL_BRIDGE')).not.toBeInTheDocument();});
it('requires an open company before opening a tax report',async()=>{state.company=undefined;render(await Page({searchParams:Promise.resolve({report:'INVOICE_TAX_REGISTER'})}));expect(screen.queryByText('Tax workspace INVOICE_TAX_REGISTER')).not.toBeInTheDocument();expect(screen.getByRole('link',{name:/companies you can open/})).toBeVisible();});
it('rejects malformed report navigation',async()=>{await expect(Page({searchParams:Promise.resolve({report:'bad/report'})})).rejects.toThrow('Not found');});

it('clears a retained ledger workspace when the signed-in actor changes',async()=>{
  const query={report:'ACCOUNT_LEDGER',run:'01990000-0000-7000-8000-000000000002'};
  const mounted=render(await Page({searchParams:Promise.resolve(query)}));expect(screen.getByText('Generic workspace 1')).toBeVisible();
  state.actor='another-actor';mounted.rerender(await Page({searchParams:Promise.resolve(query)}));
  expect(screen.getByText('Generic workspace 2')).toBeVisible();
});

it('carries a validated Trial Balance return link when opening the retained ledger',async()=>{
  const parent='01990000-0000-7000-8000-000000000003';
  render(await Page({searchParams:Promise.resolve({report:'ACCOUNT_LEDGER',run:'01990000-0000-7000-8000-000000000002',trial_balance_run:parent})}));
  expect(screen.getByRole('link',{name:'Back to Trial Balance'})).toHaveAttribute('href','/reports/workspace?report=TRIAL_BALANCE&run='+parent);
  for(const query of [{report:'ACCOUNT_LEDGER',run:'../bad'}, {report:'ACCOUNT_LEDGER',trial_balance_run:parent}, {report:'TRIAL_BALANCE',run:parent,trial_balance_run:parent}])await expect(Page({searchParams:Promise.resolve(query)})).rejects.toThrow('Not found');
});
