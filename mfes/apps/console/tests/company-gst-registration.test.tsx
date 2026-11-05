import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {beforeEach,expect,it,vi} from 'vitest';
import {CompanyGstRegistration} from '../app/components/CompanyGstRegistration';
import {companyCall} from '../app/lib/company-api';
import { BEFORE_COMPANY_CHANGE } from '../app/lib/use-unsaved-changes';
vi.mock('../app/lib/company-api',()=>({companyCall:vi.fn(),companyFailure:(value: unknown)=>value}));
let canManage=true;
beforeEach(()=>{
 canManage=true;vi.mocked(companyCall).mockReset();
 vi.mocked(companyCall).mockImplementation(async(_service,path,request)=>{
  if(path.endsWith('/gst-registration-setup'))return {country_code:'IN',default_tax_system:'gst_in',can_manage:canManage,regimes:{regular:'Regular taxpayer'},states:[{code:'MH',name:'Maharashtra'}],create_schema:{properties:{number:{maxLength:40}}}};
  if(request?.method==='POST')return {id:'new'};
  return {items:[],page:{next_cursor:null}};
 });
});
it('adds an actual dated GST registration with server state and regime choices',async()=>{
 render(<CompanyGstRegistration company="01990000-0000-7000-8000-000000000001"/>);
 fireEvent.click(await screen.findByRole('button',{name:'Add GST registration'}));
 expect(screen.getByRole('dialog',{name:'Add GST registration'})).toHaveClass('janso-drawer__panel');
 fireEvent.change(screen.getByLabelText('GSTIN'),{target:{value:'27AAAPA1234A1ZT'}});
 fireEvent.change(screen.getByLabelText('GST registration state / UT'),{target:{value:'MH'}});
 fireEvent.change(screen.getByLabelText('GST regime'),{target:{value:'regular'}});
 fireEvent.change(screen.getByLabelText('GST registration valid from'),{target:{value:'2026-10-01'}});
 fireEvent.click(screen.getByRole('button',{name:'Save GST registration'}));
 await screen.findByText('GST registration saved. Configure its confirmed filing preference in GSTR-3B.');
 const saved=vi.mocked(companyCall).mock.calls.find(call=>call[2]?.method==='POST')!;
 expect(saved[2]?.body).toMatchObject({tax_system:'gst_in',regime:'regular',jurisdiction_code:'MH',valid_from:'2026-10-01',number:'27AAAPA1234A1ZT'});
});
it('keeps registration management hidden from a read-only company user',async()=>{
 canManage=false;render(<CompanyGstRegistration company="01990000-0000-7000-8000-000000000001"/>);
 await screen.findByRole('table',{name:'Company GST registrations'});
 expect(screen.queryByRole('button',{name:'Add GST registration'})).not.toBeInTheDocument();
 expect(screen.queryByLabelText('Registration closing date')).not.toBeInTheDocument();
});

it('uses grouped registration fields instead of a compressed filter toolbar', async () => {
 render(<CompanyGstRegistration company="01990000-0000-7000-8000-000000000001"/>);
 fireEvent.click(await screen.findByRole('button',{name:'Add GST registration'}));
 expect(screen.getByLabelText('GSTIN').closest('.janso-filter-bar')).toBeNull();
 expect(screen.getByRole('group',{name:'Registration details'})).toBeVisible();
 expect(screen.getByRole('group',{name:'Jurisdiction and validity'})).toBeVisible();
 expect(screen.getByLabelText('GST regime')).toBeRequired();
});

it('freezes registration entry and prevents duplicate submits and company changes while saving', async () => {
 const answer=vi.mocked(companyCall).getMockImplementation()!; let finish!: (value: unknown)=>void;
 vi.mocked(companyCall).mockImplementation((service,path,request)=>request?.method==='POST'?new Promise(resolve=>{finish=resolve;}):answer(service,path,request));
 render(<CompanyGstRegistration company="01990000-0000-7000-8000-000000000001"/>);
 fireEvent.click(await screen.findByRole('button',{name:'Add GST registration'}));
 fireEvent.change(screen.getByLabelText('GSTIN'),{target:{value:'27AAAPA1234A1ZT'}});
 fireEvent.change(screen.getByLabelText('GST registration state / UT'),{target:{value:'MH'}});
 fireEvent.change(screen.getByLabelText('GST regime'),{target:{value:'regular'}});
 fireEvent.change(screen.getByLabelText('GST registration valid from'),{target:{value:'2026-10-01'}});
 const form=screen.getByRole('form',{name:'Add GST registration'});
 fireEvent.submit(form);fireEvent.submit(form);
 expect(vi.mocked(companyCall).mock.calls.filter(call=>call[2]?.method==='POST')).toHaveLength(1);
 expect(screen.getByLabelText('GSTIN')).toBeDisabled();
 expect(screen.getByRole('button',{name:'Cancel'})).toBeDisabled();
 expect(window.dispatchEvent(new Event(BEFORE_COMPANY_CHANGE,{cancelable:true}))).toBe(false);
 finish({id:'saved'});
 await screen.findByText(/GST registration saved/);
 await waitFor(()=>expect(window.dispatchEvent(new Event(BEFORE_COMPANY_CHANGE,{cancelable:true}))).toBe(true));
});

it('retains a failed registration payload and reuses its idempotency key on retry', async () => {
 const answer=vi.mocked(companyCall).getMockImplementation()!;let first=true;
 vi.mocked(companyCall).mockImplementation((service,path,request)=>request?.method==='POST'&&first?(first=false,Promise.reject({status:503,message:'Response lost'})):answer(service,path,request));
 render(<CompanyGstRegistration company="01990000-0000-7000-8000-000000000001"/>);
 fireEvent.click(await screen.findByRole('button',{name:'Add GST registration'}));
 fireEvent.change(screen.getByLabelText('GSTIN'),{target:{value:'27AAAPA1234A1ZT'}});
 fireEvent.change(screen.getByLabelText('GST registration state / UT'),{target:{value:'MH'}});
 fireEvent.change(screen.getByLabelText('GST regime'),{target:{value:'regular'}});
 fireEvent.change(screen.getByLabelText('GST registration valid from'),{target:{value:'2026-10-01'}});
 fireEvent.click(screen.getByRole('button',{name:'Save GST registration'}));await screen.findByText('Response lost');
 expect(screen.getByLabelText('GSTIN')).toHaveValue('27AAAPA1234A1ZT');
 fireEvent.click(screen.getByRole('button',{name:'Save GST registration'}));await screen.findByText(/GST registration saved/);
 const writes=vi.mocked(companyCall).mock.calls.filter(call=>call[2]?.method==='POST');expect(writes[0][2]?.key).toBe(writes[1][2]?.key);
});

it.each([true,false])('offers GST reports only when the page has verified their company context (%s)', async canOpenReports => {
 render(<CompanyGstRegistration company="01990000-0000-7000-8000-000000000001" canOpenReports={canOpenReports}/>);
 await screen.findByRole('table',{name:'Company GST registrations'});
 expect(screen.queryByRole('link',{name:'GST filing preferences and GSTR-3B'})!==null).toBe(canOpenReports);
});

it('shows a failed initial history read as an error instead of an empty registration list', async () => {
 const answer=vi.mocked(companyCall).getMockImplementation()!;
 vi.mocked(companyCall).mockImplementation((service,path,request)=>path.includes('/tax-registrations?')?Promise.reject({status:503,message:'Registration history unavailable'}):answer(service,path,request));
 render(<CompanyGstRegistration company="01990000-0000-7000-8000-000000000001"/>);
 await screen.findByText(/Registration history unavailable/);
 expect(screen.queryByRole('table',{name:'Company GST registrations'})).not.toBeInTheDocument();
 expect(screen.getByRole('button',{name:'Reload GST registrations'})).toBeEnabled();
});
