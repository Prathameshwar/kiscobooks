import {render,screen} from '@testing-library/react';
import {expect,it,vi} from 'vitest';
import Page from '../app/reports/page';
const state=vi.hoisted(()=>({allowed:true,company:'company' as string|undefined,canCreate:false}));
vi.mock('../app/lib/page-context',()=>({pageContext:async()=>({
  session:{permissions:[...(state.allowed?['report.read']:[]),...(state.canCreate?['company.create']:[])],
    display:{currency:'INR'},company:{name:'Acme',id:state.company},
    grants:[{scope_type:'tenant',scope_id:null,valid_from:'2000-01-01',valid_to:null,permissions:[...(state.allowed?['report.read']:[]),...(state.canCreate?['company.create']:[])]}]},
  context:{companies:[],companiesNote:null,fiscalYears:[],fiscalYear:null,fiscalNote:null},
})}));
vi.mock('../app/providers',()=>({Providers:({children}:{children:React.ReactNode})=>children}));
vi.mock('../app/components/ConsoleShell',()=>({ConsoleShell:({children}:{children:React.ReactNode})=>children}));
vi.mock('../app/components/ReportsHub',()=>({ReportsHub:()=> <div>Report cards</div>}));
it('uses the open company and the report permission',async()=>{state.allowed=true;state.company='company';render(await Page());expect(screen.getByText('Report cards')).toBeInTheDocument();});
it('refuses an open company the role cannot report on',async()=>{state.allowed=false;render(await Page());expect(screen.getByRole('alert')).toHaveTextContent("You don't have access to this");});
it('offers creation in the empty state only to an actor who may create a company',async()=>{
  state.company=undefined;state.canCreate=true;render(await Page());
  expect(screen.getByRole('link',{name:'Create a company'})).toHaveAttribute('href','/companies/new');
  state.canCreate=false;
});
it('points an actor who cannot create one at the companies they can open',async()=>{
  state.company=undefined;render(await Page());
  expect(screen.getByRole('link',{name:/companies you can open/})).toHaveAttribute('href','/companies');
});
