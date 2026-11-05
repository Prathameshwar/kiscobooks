import {render,screen} from '@testing-library/react';
import {beforeEach,expect,it,vi} from 'vitest';
import Page from '../app/vouchers/page';
const state=vi.hoisted(()=>({allowed:true,imports:false,createCompany:false,scope:'tenant' as 'tenant'|'company',company:'company' as string|undefined,note:null as string|null}));
vi.mock('../app/lib/page-context',()=>({pageContext:async()=>({
  session:{permissions:[...(state.allowed?['vouchers.read','vouchers.create']:[]),...(state.imports?['vouchers.import.read']:[]),...(state.createCompany?['company.create']:[])],
    grants:[{scope_type:state.scope,scope_id:state.scope==='tenant'?null:'company',valid_from:'2000-01-01',valid_to:null,permissions:[...(state.allowed?['vouchers.read','vouchers.create']:[]),...(state.imports?['vouchers.import.read']:[]),...(state.createCompany?['company.create']:[])]}],
    display:{currency:'INR'},company:{name:'Acme',id:state.company}},
  context:{companies:[],companiesNote:state.note,fiscalYears:[],fiscalYear:null,fiscalNote:null},
})}));
vi.mock('../app/providers',()=>({Providers:({children}:{children:React.ReactNode})=>children}));
vi.mock('../app/components/ConsoleShell',()=>({ConsoleShell:({children}:{children:React.ReactNode})=>children}));
vi.mock('../app/components/VoucherDirectory',()=>({VoucherDirectory:()=> <div>Voucher form</div>}));
vi.mock('../app/components/VoucherImport',()=>({VoucherImport:()=> <div>Voucher import</div>}));
beforeEach(()=>{state.allowed=true;state.imports=false;state.createCompany=false;state.scope='tenant';state.company='company';state.note=null;});
it('uses the open company from the session, with no second context fetch',async()=>{state.allowed=true;state.imports=false;state.company='company';render(await Page());expect(screen.getByText('Voucher form')).toBeInTheDocument();expect(screen.queryByText('Voucher import')).not.toBeInTheDocument();});
it('offers bulk import only with import read permission',async()=>{state.allowed=true;state.imports=true;render(await Page());expect(screen.getByText('Voucher import')).toBeInTheDocument();});
it('refuses an open company the role cannot read, rather than blaming the selection',async()=>{
  state.allowed=false;state.imports=false;state.company='company';render(await Page());
  expect(screen.getByRole('alert')).toHaveTextContent("You don't have access to this");
  expect(screen.queryByText(/No company is open/)).not.toBeInTheDocument();
});
it('explains an unopened company, carrying the reason the switcher gave',async()=>{
  state.company=undefined;state.note='No company has been created yet.';render(await Page());
  expect(screen.getByText(/No company is open, so there is nothing to record yet/)).toBeInTheDocument();
  expect(screen.getByText('No company has been created yet.')).toBeInTheDocument();
});
it('does not mount import below a denied voucher page',async()=>{
  state.allowed=false;state.imports=true;render(await Page());
  expect(screen.getByRole('alert')).toBeVisible();
  expect(screen.queryByText('Voucher import')).not.toBeInTheDocument();
});
it.each(['tenant','company'] as const)('requires tenant company-creation authority in the empty %s context',async scope=>{
  state.scope=scope;state.company=undefined;state.createCompany=true;render(await Page());
  expect(!!screen.queryByRole('link',{name:'Create a company'})).toBe(scope==='tenant');
});
