import {act,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {beforeEach,expect,it,vi} from 'vitest';
import {FinancialOpeningMasterBalances} from '../app/components/FinancialOpeningMasterBalances';
import {MasterOpeningSummary} from '../app/components/MasterOpeningSummary';
import {AccountingConfigurationEditor} from '../app/components/AccountingConfigurationEditor';
import {allowedFinancialOpeningRequest} from '../app/lib/financial-opening-policy';
import {accountingResource} from '../app/lib/accounting-configuration-resources';
import {serviceCall,type ServiceRequest} from '../app/lib/service-call';
import {masterEntry} from '../app/lib/master-opening-held';
import {COMPANY,ACCOUNT,access} from './financial-opening-fixtures';
import {capture,heldMaster,masterPage} from './master-opening-fixture';
import {COMPANY as ACCOUNT_COMPANY,GROUP,response} from './accounting-configuration-fixtures';
vi.mock('../app/lib/service-call',async original=>({...await original<typeof import('../app/lib/service-call')>(),serviceCall:vi.fn()}));
vi.mock('../app/lib/navigate',()=>({goTo:vi.fn(),signInUrl:()=>'/signin'}));
const api=vi.mocked(serviceCall),item=heldMaster();
let read=()=>masterPage([item]),write=(request:ServiceRequest)=>({...item,status:'WITHDRAWN'});
beforeEach(()=>{vi.clearAllMocks();read=()=>masterPage([item]);write=()=>({...item,status:'WITHDRAWN'});api.mockImplementation(async(_,request)=>{
  if(request.path.includes('/master-balances'))return (request.method==='POST'?write(request):read()) as never;
  return {id:ACCOUNT,company_id:COMPANY,name:'Supplier ledger'} as never;
});});
function panel(editable=true){const onAdd=vi.fn(),onDirty=vi.fn();const mounted=render(<FinancialOpeningMasterBalances company={COMPANY} rows={[]} date="2026-04-01" access={access} editable={editable} onAdd={onAdd} onDirty={onDirty}/>);return {...mounted,onAdd,onDirty};}
it('offers saved balances and exact bill evidence for the company worksheet',async()=>{
  const {onAdd}=panel();expect(await screen.findByText('Openings saved during creation')).toBeVisible();await userEvent.click(screen.getByRole('button',{name:'Add saved opening '+item.source_key}));expect(onAdd).toHaveBeenCalledWith([masterEntry(item)]);expect(screen.getByText('1 pending bills')).toBeVisible();
});
it('keeps addition disabled when the worksheet is not editable',async()=>{panel(false);expect(await screen.findByRole('button',{name:'Add saved opening '+item.source_key})).toBeDisabled();});
it('renders no panel for an empty list or a denied financial read',async()=>{
  read=()=>masterPage();const view=panel();await waitFor(()=>expect(api).toHaveBeenCalled());expect(view.container).toBeEmptyDOMElement();view.unmount();
  api.mockRejectedValue({status:403,message:'Opening read denied'});const denied=panel();await waitFor(()=>expect(api.mock.calls.length).toBeGreaterThan(1));expect(denied.container).toBeEmptyDOMElement();
});
it('withdraws with a version and review reason without losing original evidence',async()=>{
  const {onDirty}=panel();await userEvent.click(await screen.findByRole('button',{name:'Withdraw saved opening '+item.source_key}));const dialog=screen.getByRole('dialog');
  await userEvent.click(within(dialog).getByRole('button',{name:'Withdraw opening'}));expect(within(dialog).getByRole('alert')).toHaveTextContent(/reason/);
  await userEvent.type(within(dialog).getByLabelText('Withdrawal reason'),'Wrong balance');await userEvent.click(within(dialog).getByRole('button',{name:'Withdraw opening'}));
  expect(await screen.findByText('Saved opening withdrawn.')).toBeVisible();expect(api.mock.calls.find(([,r])=>r.method==='POST')![1].body).toEqual({expected_version:1,reason:'Wrong balance'});await waitFor(()=>expect(onDirty).toHaveBeenLastCalledWith(false));
});
it('freezes and retries an uncertain withdrawal with the same request and key',async()=>{
  let attempts=0;write=()=>{if(++attempts===1)throw {status:503,message:'Outcome unknown'};return {...item,status:'WITHDRAWN'};};
  panel();await userEvent.click(await screen.findByRole('button',{name:'Withdraw saved opening '+item.source_key}));const dialog=screen.getByRole('dialog');await userEvent.type(within(dialog).getByLabelText('Withdrawal reason'),'Wrong balance');await userEvent.click(within(dialog).getByRole('button',{name:'Withdraw opening'}));await userEvent.click(await within(dialog).findByRole('button',{name:'Retry the same request'}));
  await screen.findByText('Saved opening withdrawn.');const calls=api.mock.calls.filter(([,r])=>r.method==='POST');expect(calls[0]![1].key).toBe(calls[1]![1].key);expect(calls[0]![1].body).toEqual(calls[1]![1].body);
});
it('paginates available openings even when this page has already been included',async()=>{
  read=()=>masterPage([{...item,included:true}],true);panel();await userEvent.click(await screen.findByRole('button',{name:'Next saved balances'}));await waitFor(()=>expect(api.mock.calls.some(([,r])=>r.path.includes('cursor=verified-cursor'))).toBe(true));await userEvent.click(screen.getByRole('button',{name:'Previous saved balances'}));
});
it('shows the captured account balance, date, status and worksheet link',async()=>{
  render(<MasterOpeningSummary company={COMPANY} account={ACCOUNT}/>);expect(await screen.findByText('Opening saved during creation')).toBeVisible();expect(screen.getByText('Saved for company opening review')).toBeVisible();expect(screen.getByRole('link',{name:'Review company opening worksheet'})).toHaveAttribute('href','/accounting/opening?account_id='+ACCOUNT);
});
it('rejects a wrong-account summary receipt',async()=>{
  read=()=>masterPage([heldMaster({account_id:'01990000-0000-7000-8000-000000000009'})]);render(<MasterOpeningSummary company={COMPANY} account={ACCOUNT}/>);expect(await screen.findByText(/could not be verified/)).toBeVisible();
});
it('shows a posted creation opening without asking for another worksheet action',async()=>{
  read=()=>masterPage([{...item,status:'POSTED'}]);
  render(<MasterOpeningSummary company={COMPANY} account={ACCOUNT}/>);
  expect(await screen.findByText('Opening posted during creation')).toBeVisible();
  expect(screen.getByText('Posted',{exact:true})).toBeVisible();
  expect(screen.getByText(/No further opening action is required/)).toBeVisible();
  expect(screen.queryByRole('link',{name:'Review company opening worksheet'})).not.toBeInTheDocument();
});
it('keeps an interrupted posting distinct from a completed opening',async()=>{
  read=()=>masterPage([{...item,status:'POSTING'}]);
  render(<MasterOpeningSummary company={COMPANY} account={ACCOUNT}/>);
  expect(await screen.findByText(/Posting pending/)).toBeVisible();
  expect(screen.queryByText('Posted',{exact:true})).not.toBeInTheDocument();
  expect(screen.queryByRole('link',{name:'Review company opening worksheet'})).not.toBeInTheDocument();
});
it('captures an optional account opening as the final step and posts a single native request',async()=>{
  api.mockImplementation(async(_,request)=>request.path.endsWith('/master-balances/capture')?{...capture,company_id:ACCOUNT_COMPANY} as never:response(request.path,request.method,request.body) as never);
  render(<AccountingConfigurationEditor company={ACCOUNT_COMPANY} config={accountingResource('accounts')!} prefills={{kind:'GENERAL',group_id:GROUP}}/>);
  fireEvent.change(await screen.findByRole('textbox',{name:'Code'}),{target:{value:'OPEN-CAPITAL'}});fireEvent.change(screen.getByRole('textbox',{name:'Name'}),{target:{value:'Opening capital'}});
  await userEvent.click(screen.getByRole('button',{name:'Next'}));const amount=await screen.findByRole('textbox',{name:'Opening balance'});await waitFor(()=>expect(amount).toBeEnabled());await userEvent.type(amount,'100.0001');await userEvent.selectOptions(screen.getByRole('combobox',{name:'Dr / Cr'}),'CREDIT');await userEvent.click(screen.getByRole('button',{name:'Create account'}));
  await waitFor(()=>expect(api.mock.calls.some(([,r])=>r.method==='POST')).toBe(true));expect(api.mock.calls.find(([,r])=>r.method==='POST')![1].body).toMatchObject({opening:{amount:'100.0001',side:'CREDIT',opening_date:'2026-04-01'}});
});
it('confirms the original account creation after refreshed opening access becomes unavailable',async()=>{
  let reads=0,posts=0,resolveCapture!:(value:typeof capture)=>void;
  api.mockImplementation(async(_,request)=>{
    if(request.path.endsWith('/master-balances/capture')){
      if(++reads===1)return {...capture,company_id:ACCOUNT_COMPANY} as never;
      return await new Promise<typeof capture>(resolve=>{resolveCapture=resolve;}) as never;
    }
    if(request.method==='POST'&&++posts===1)throw {status:503,message:'Outcome unknown'};
    return response(request.path,request.method,request.body) as never;
  });
  render(<AccountingConfigurationEditor company={ACCOUNT_COMPANY} config={accountingResource('accounts')!} prefills={{kind:'GENERAL',group_id:GROUP}}/>);
  fireEvent.change(await screen.findByRole('textbox',{name:'Code'}),{target:{value:'OPEN-RETRY'}});fireEvent.change(screen.getByRole('textbox',{name:'Name'}),{target:{value:'Opening retry'}});
  await userEvent.click(screen.getByRole('button',{name:'Next'}));await waitFor(()=>expect(screen.getByLabelText('Opening balance')).toBeEnabled());
  fireEvent.change(screen.getByLabelText('Opening balance'),{target:{value:'100.0001'}});await userEvent.selectOptions(screen.getByRole('combobox',{name:'Dr / Cr'}),'CREDIT');
  await userEvent.click(screen.getByRole('button',{name:'Previous'}));await userEvent.click(screen.getByRole('button',{name:'Next'}));await waitFor(()=>expect(reads).toBe(2));
  await userEvent.click(screen.getByRole('button',{name:'Create account'}));await screen.findByRole('button',{name:'Retry same save'});
  await act(async()=>resolveCapture({...capture,company_id:ACCOUNT_COMPANY,can_capture:false}));
  await userEvent.click(screen.getByRole('button',{name:'Retry same save'}));await waitFor(()=>expect(posts).toBe(2));
  const calls=api.mock.calls.filter(([,request])=>request.method==='POST');expect(calls[1]![1]).toEqual(calls[0]![1]);
});
it.each([['GET','/capture',true],['POST','/capture',false],['GET','?status=PENDING&limit=50&account_id='+ACCOUNT,true],['GET','?limit=51',false],['GET','?status=PENDING&status=WITHDRAWN',false],['GET','?unknown=1',false],['POST','/'+item.id+'/withdraw',true],['POST','/'+item.id+'/withdraw?reason=x',false]])('bounds the opening proxy %s %s',(method,suffix,expected)=>expect(allowedFinancialOpeningRequest('accounting',method,`/v1/companies/${COMPANY}/opening-batches/master-balances`+suffix)).toBe(expected));
