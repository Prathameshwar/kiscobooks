import {useState} from 'react';
import {fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {beforeEach,expect,it,vi} from 'vitest';
import {MasterOpeningStep} from '../app/components/MasterOpeningStep';
import {blankOpening,billErrors,billKinds,canOpen,newBill,openingDirty,openingPayload,pendingTotal,useMasterOpening,type OpeningAccount} from '../app/lib/master-opening';
import {addableMaster,masterEntry,verifyMasterPage} from '../app/lib/master-opening-held';
import {serviceCall} from '../app/lib/service-call';
import {COMPANY,OTHER} from './financial-opening-fixtures';
import {capture,draft,heldMaster,masterPage,supplier} from './master-opening-fixture';
vi.mock('../app/lib/service-call',async original=>({...await original<typeof import('../app/lib/service-call')>(),serviceCall:vi.fn()}));
const api=vi.mocked(serviceCall);
beforeEach(()=>{vi.clearAllMocks();api.mockResolvedValue(capture as never);});
it('leaves an optional blank or zero opening out of the native create body',()=>{
  for(const amount of ['', '0','0.0000'])expect(openingPayload(draft({amount}),null,supplier)).toEqual({errors:{}});
  expect(openingDirty(blankOpening())).toBe(false);expect(openingDirty(draft())).toBe(true);
});
it('keeps exact balance, explicit side and books-begin date',()=>{
  expect(openingPayload(draft({amount:'100.0001'}),capture,supplier).opening).toMatchObject({amount:'100.0001',side:'CREDIT',opening_date:'2026-04-01'});
  expect(openingPayload(draft({side:''}),capture,supplier).errors['opening.side']).toBeTruthy();
  expect(openingPayload(draft({date:'2026-04-02'}),capture,supplier).errors['opening.opening_date']).toBeTruthy();
  expect(openingPayload(draft({date:'2026-02-30'}),capture,supplier).errors['opening.opening_date']).toBeTruthy();
});
it.each(['-1','1.00001','1e2','NaN','1000000000000000'])('rejects invalid exact amounts %s',amount=>expect(openingPayload(draft({amount}),capture,supplier).errors['opening.amount']).toBeTruthy());
it('denies missing metadata, inventory, and missing native bill write access',()=>{
  expect(canOpen(null,supplier)).toBe(false);
  expect(openingPayload(draft(),null,supplier).errors['opening.amount']).toBeTruthy();
  expect(openingPayload(draft(),capture,{...supplier,inventory:true}).errors['opening.amount']).toMatch(/stock/);
  expect(canOpen({...capture,capture_permissions:{...capture.capture_permissions,open_items:{amount:false}}},supplier)).toBe(false);
  expect(canOpen({...capture,capture_permissions:{...capture.capture_permissions,open_items:{}}},supplier)).toBe(false);
});
it.each([['CUSTOMER','DEBIT','INVOICE'],['SUPPLIER','CREDIT','BILL'],['CUSTOMER','CREDIT','ADVANCE'],['SUPPLIER','DEBIT','ADVANCE']])('offers the correct bill type for %s %s',(role,side,kind)=>expect(billKinds({...supplier,role},side)[0]!.value).toBe(kind));
const bill=(values={})=>({...newBill(supplier,'CREDIT'),reference:'BILL-1',original:'200',pending:'60.0001',date:'2026-03-01',due:'2026-04-10',...values});
it('totals pending values and retains original bills with their real dates',()=>{
  const bills=[bill(),bill({reference:'BILL-2',pending:'39.9999'})];
  expect(pendingTotal(bills)).toBe('100.0000');
  const body=openingPayload(draft({mode:'bills',amount:'999',bills}),capture,supplier);
  expect(body.errors).toEqual({});expect(body.opening?.amount).toBe('100.0000');expect(body.opening?.documents?.[0]).toMatchObject({original_amount:'200',amount:'60.0001',document_kind:'BILL',document_date:'2026-03-01'});
  expect(openingPayload(draft({mode:'bills',bills:[...bills,bill({reference:' bill-1 '})]}),capture,supplier).errors['opening.documents.2.reference']).toMatch(/unique/);
  expect(openingPayload(draft({mode:'bills',bills,editor:bill()}),capture,supplier).errors['opening.documents']).toMatch(/current bill/);
  expect(openingPayload(draft({mode:'bills'}),capture,supplier).errors['opening.documents']).toBeTruthy();
  expect(openingPayload(draft({mode:'bills',bills}),capture,{...supplier,party:false}).errors['opening.documents']).toBeTruthy();
});
it.each([['pending',{pending:'201'}],['reference',{reference:'bad\nref'}],['original',{original:''}],['pending',{pending:'0'}],['date',{date:'2026-04-01'}],['due',{due:'2026-02-01'}],['kind',{kind:'INVOICE'}],['base',{base:''}]])('validates bill %s',(key,values)=>expect(billErrors(bill(values),supplier,'CREDIT','2026-04-01',key==='base')[key]).toBeTruthy());
it('requires historical foreign values and a reason for credit cash',()=>{
  const foreign={...supplier,currencyMode:'FIXED',currency:'USD'};
  expect(openingPayload(draft(),capture,foreign).errors).toHaveProperty('opening.exchange_rate');
  expect(openingPayload(draft({rate:'83.12345678',base:'8312.3456'}),capture,foreign).errors).toEqual({});
  expect(openingPayload(draft({mode:'bills',rate:'83',base:'8300',bills:[bill({pending:'100',base:'8299'})]}),capture,foreign).errors['opening.base_amount']).toBeTruthy();
  expect(openingPayload(draft(),capture,{party:false,kind:'CASH'}).errors['opening.credit_cash_reason']).toBeTruthy();
  expect(openingPayload(draft({cashReason:'Reviewed credit cash'}),capture,{party:false,kind:'CASH'}).opening?.credit_cash_reason).toBe('Reviewed credit cash');
});
function Step({account=supplier,initial=blankOpening(),meta=capture,disabled=false,onChange}:{account?:OpeningAccount;initial?:ReturnType<typeof blankOpening>;meta?:typeof capture;disabled?:boolean;onChange?:(draft:ReturnType<typeof blankOpening>)=>void}){const [value,setValue]=useState(initial);return <MasterOpeningStep draft={value} onChange={next=>{setValue(next);onChange?.(next);}} metadata={meta} loading={false} failure={null} retry={vi.fn()} account={account} disabled={disabled}/>;}
it('starts with three controls and only reveals bills when requested',async()=>{
  render(<Step/>);expect(screen.getByLabelText('Opening balance')).toBeVisible();expect(screen.getByLabelText('Opening date')).toHaveValue('2026-04-01');expect(screen.queryByLabelText('Bill number')).toBeNull();
  await userEvent.selectOptions(screen.getByRole('combobox',{name:'Dr / Cr'}),'CREDIT');
  await userEvent.click(screen.getByRole('radio',{name:'Bill-wise'}));
  expect(screen.getByLabelText('Opening balance')).toHaveAttribute('readonly');
  for(const [label,value] of [['Bill number','B-1'],['Bill amount','200'],['Pending amount','100'],['Bill date','2026-03-01'],['Due date','2026-04-10']])fireEvent.change(screen.getByLabelText(label!),{target:{value}});
  await userEvent.click(screen.getByRole('button',{name:'Add bill'}));
  expect(screen.getByLabelText('Opening balance')).toHaveValue('100.0000');
  await userEvent.click(screen.getByRole('button',{name:'Edit opening bill B-1'}));fireEvent.change(screen.getByLabelText('Pending amount'),{target:{value:'50'}});await userEvent.click(screen.getByRole('button',{name:'Update bill'}));
  expect(screen.getByLabelText('Opening balance')).toHaveValue('50.0000');
  await userEvent.click(screen.getByRole('button',{name:'Remove opening bill B-1'}));expect(screen.queryByRole('region',{name:'Opening bills'})).toBeNull();
});
it('keeps invalid bills in the editor and permits cancellation',async()=>{
  render(<Step initial={draft({mode:'bills',editor:bill({pending:'201'})})}/>);
  await userEvent.click(screen.getByRole('button',{name:'Add bill'}));expect(screen.getByText('Pending amount cannot exceed bill amount.')).toBeVisible();
  await userEvent.click(screen.getByRole('button',{name:'Cancel bill'}));expect(screen.queryByRole('region',{name:'Opening bill editor'})).toBeNull();
});
it('keeps the exact pending balance when switching from bill-wise to balance only',async()=>{
  render(<Step initial={draft({mode:'bills',amount:'',bills:[bill({pending:'100.0001'})]})}/>);
  await userEvent.click(screen.getByRole('radio',{name:'Balance only'}));
  expect(screen.getByLabelText('Opening balance')).toHaveValue('100.0001');
  await userEvent.click(screen.getByRole('radio',{name:'Bill-wise'}));
  expect(screen.getByRole('region',{name:'Opening bills'})).toBeVisible();
});
it('keeps historical foreign carrying values when switching out of bill-wise mode',async()=>{
  render(<Step account={{...supplier,currencyMode:'FIXED',currency:'USD'}} initial={draft({mode:'bills',rate:'83',base:'999',bills:[bill({base:'4980.0083'}),bill({reference:'BILL-2',pending:'39.9999',base:'3319.9917'})]})}/>);
  await userEvent.click(screen.getByRole('radio',{name:'Balance only'}));expect(screen.getByLabelText('Opening balance')).toHaveValue('100.0000');expect(screen.getByLabelText('Historical opening value')).toHaveValue('8300.0000');
});
it('captures foreign rate and historical value without altering exact precision',async()=>{
  const changed=vi.fn(),account={...supplier,currencyMode:'FIXED',currency:'USD'};render(<Step account={account} onChange={changed}/>);
  for(const [label,entered] of [['Opening balance','100.0001'],['Opening date','2026-04-01'],['Opening exchange rate','83.12345678'],['Historical opening value','8312.3456']])fireEvent.change(screen.getByLabelText(label!),{target:{value:entered}});
  await userEvent.selectOptions(screen.getByRole('combobox',{name:'Dr / Cr'}),'CREDIT');expect(openingPayload(changed.mock.calls.at(-1)![0],capture,account).opening).toMatchObject({amount:'100.0001',exchange_rate:'83.12345678',base_amount:'8312.3456'});
});
it('adds historical outstanding bills with an explicit type and validates duplicate references',async()=>{
  render(<Step account={{...supplier,currencyMode:'FIXED',currency:'USD'}} initial={draft({mode:'bills',rate:'83',base:'8300',bills:[bill({base:'4980'})],editor:bill({reference:' bill-1 ',base:'',pending:'40'})})}/>);
  fireEvent.change(screen.getByLabelText('Pending historical value'),{target:{value:'3320.0000'}});await userEvent.selectOptions(screen.getByRole('combobox',{name:'Bill type'}),'BILL');
  await userEvent.click(screen.getByRole('button',{name:'Add bill'}));
  expect(screen.getByText('Bill numbers must be unique.')).toBeVisible();
});
it('requires and retains a review reason when cash has a credit opening',async()=>{
  render(<Step account={{party:false,kind:'CASH'}} initial={draft()}/>);expect(screen.getByLabelText('Credit cash opening reason')).toBeVisible();
  fireEvent.change(screen.getByLabelText('Credit cash opening reason'),{target:{value:'Reviewed credit cash'}});expect(screen.getByLabelText('Credit cash opening reason')).toHaveValue('Reviewed credit cash');
  await userEvent.selectOptions(screen.getByRole('combobox',{name:'Dr / Cr'}),'DEBIT');expect(screen.queryByLabelText('Credit cash opening reason')).toBeNull();
});
it('can switch mode with an untouched bill editor and clear an unsaved bill',async()=>{
  render(<Step initial={draft({mode:'bills',editor:newBill(supplier,'CREDIT')})}/>);await userEvent.click(screen.getByRole('radio',{name:'Balance only'}));expect(screen.queryByLabelText('Bill number')).toBeNull();
  await userEvent.click(screen.getByRole('radio',{name:'Bill-wise'}));fireEvent.change(screen.getByLabelText('Bill number'),{target:{value:'UNSAVED'}});
  await userEvent.click(screen.getByRole('button',{name:'Clear opening balance'}));await userEvent.click(within(screen.getByRole('dialog')).getByRole('button',{name:'Clear opening'}));expect(screen.queryByLabelText('Bill number')).toBeNull();
});
it('keeps an unfinished bill visible when switching mode',async()=>{
  render(<Step initial={draft({mode:'bills',editor:bill({reference:'UNSAVED'})})}/>);
  await userEvent.click(screen.getByRole('radio',{name:'Balance only'}));
  expect(screen.getByLabelText('Bill number')).toHaveValue('UNSAVED');
  expect(screen.getByRole('alert')).toHaveTextContent(/cancel.*bill/i);
});
it('can clear a retained balance when opening access becomes unavailable',async()=>{
  render(<Step initial={draft()} meta={{...capture,can_capture:false}}/>);
  expect(screen.getByLabelText('Opening balance')).toBeDisabled();
  await userEvent.click(screen.getByRole('button',{name:'Clear opening balance'}));
  expect(screen.getByLabelText('Opening balance')).toHaveValue('');
  expect(screen.getByRole('combobox',{name:'Dr / Cr'})).toHaveValue('');
});
it('keeps clearing disabled while the opening creation is pending or uncertain',()=>{
  render(<Step initial={draft()} disabled/>);expect(screen.getByRole('button',{name:'Clear opening balance'})).toBeDisabled();expect(screen.getByLabelText('Opening balance')).toHaveValue('100');
});
it('confirms clearing retained bills and allows keeping them',async()=>{
  render(<Step initial={draft({mode:'bills',bills:[bill()]})}/>);
  await userEvent.click(screen.getByRole('button',{name:'Clear opening balance'}));
  const dialog=screen.getByRole('dialog',{name:'Clear opening balance?'});
  await userEvent.click(within(dialog).getByRole('button',{name:'Keep opening'}));
  expect(screen.getByRole('region',{name:'Opening bills'})).toBeVisible();
  await userEvent.click(screen.getByRole('button',{name:'Clear opening balance'}));
  await userEvent.click(within(screen.getByRole('dialog')).getByRole('button',{name:'Clear opening'}));
  expect(screen.queryByRole('region',{name:'Opening bills'})).toBeNull();
  expect(screen.getByLabelText('Opening balance')).toHaveValue('');
});
it('does not offer bill mode for a general account and respects unavailable capture',()=>{
  render(<Step account={{...supplier,party:false}} meta={{...capture,can_capture:false}}/>);
  expect(screen.queryByRole('radio',{name:'Bill-wise'})).toBeNull();expect(screen.getByLabelText('Opening balance')).toBeDisabled();expect(screen.getByText(/Opening capture is unavailable/)).toBeVisible();
});
function Hook({company=COMPANY}:{company?:string}){const value=useMasterOpening(company,true);return <><output>{value.metadata?.opening_date??'none'}</output><button onClick={()=>value.setDraft(draft())}>Change draft</button><button onClick={value.retry}>Retry</button><span>{value.draft.amount}</span>{value.failure&&<p role="alert">{value.failure.message}</p>}</>;}
it('loads scoped capture metadata and resets the financial draft on company change',async()=>{
  const view=render(<Hook/>);await screen.findByText('2026-04-01');await userEvent.click(screen.getByRole('button',{name:'Change draft'}));expect(screen.getByText('100')).toBeVisible();
  api.mockResolvedValue({...capture,company_id:OTHER} as never);view.rerender(<Hook company={OTHER}/>);await waitFor(()=>expect(api.mock.calls.at(-1)![1].path).toContain(OTHER));expect(screen.queryByText('100')).toBeNull();
});
it.each([{company_id:OTHER},{currency:'bad'},{capture_permissions:{journal_lines:{},open_items:{amount:true}}},{blockers:[false]}])('rejects malformed capture metadata %j',async changed=>{
  api.mockResolvedValue({...capture,...changed} as never);render(<Hook/>);expect(await screen.findByRole('alert')).toHaveTextContent(/could not be verified/);api.mockResolvedValue(capture as never);await userEvent.click(screen.getByRole('button',{name:'Retry'}));await screen.findByText('2026-04-01');
});
it('verifies native ownership, exact bill totals and deep copies held allocations',()=>{
  const item=heldMaster();expect(()=>verifyMasterPage(COMPANY,masterPage([item]))).not.toThrow();
  const line=masterEntry(item);line.documents![0]!.amount='1';expect(item.entry.documents[0]!.amount).toBe('100');
  expect(addableMaster([item],[],item.opening_date)).toEqual([item]);expect(addableMaster([item],[masterEntry(item)],item.opening_date)).toEqual([]);
  expect(addableMaster([{...item,included:true},{...item,status:'WITHDRAWN'}],[],item.opening_date)).toEqual([]);
});
it.each(['company','amount','reference','pending','date','cursor','duplicate'])('refuses invalid held %s',kind=>{
  const item=heldMaster(),page=masterPage([item]);
  if(kind==='company')item.company_id=OTHER;if(kind==='amount')item.entry.amount='99';if(kind==='reference')item.entry.documents[0]!.reference='bad\n';if(kind==='pending')item.entry.documents[0]!.original_amount='1';if(kind==='date')item.entry.documents[0]!.document_date='2026-04-01';if(kind==='cursor')page.page={limit:25,has_more:true,next_cursor:null};if(kind==='duplicate')page.items.push(item);
  expect(()=>verifyMasterPage(COMPANY,page)).toThrow();
});
