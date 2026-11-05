import {fireEvent,render,screen} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {CompanyGstOutwardProfile} from '../app/components/CompanyGstOutwardProfile';
import {companyCall} from '../app/lib/company-api';

vi.mock('../app/lib/company-api',()=>({companyCall:vi.fn(),companyFailure:(value: unknown)=>value}));
const company='01990000-0000-7000-8000-000000000001',reg='01990000-0000-7000-8000-000000000002';
let manage=true;
afterEach(()=>vi.unstubAllGlobals());
beforeEach(()=>{manage=true;vi.mocked(companyCall).mockReset();vi.mocked(companyCall).mockImplementation(async(_service,path)=>path.endsWith('/gst-outward-profile-setup')?{can_manage:manage,create_schema:{properties:{reference:{maxLength:120}}}}:{items:[{id:company,registration_id:reg,annual_turnover:'40000000.0000',rule_14a:false,valid_from:'2026-04-01',valid_to:null}],page:{next_cursor:null}});});
it('shows exact turnover history and requires explicit Rule 14A and retained proof',async()=>{render(<CompanyGstOutwardProfile company={company} registrations={[{id:reg,number:'27ABCDE1234F1Z5',regime:'regular'}]}/>);await screen.findByText('40000000.0000');fireEvent.click(screen.getByRole('button',{name:'Add outward reporting profile'}));expect(screen.getByLabelText('Registered under Rule 14A')).toHaveValue('');expect(screen.getByRole('button',{name:'Save outward reporting profile'})).toBeDisabled();expect(screen.getByLabelText('Reporting profile evidence reference')).toHaveAttribute('maxlength','120');});
it('keeps the profile form and close action hidden from readers',async()=>{manage=false;render(<CompanyGstOutwardProfile company={company} registrations={[{id:reg,number:'27ABCDE1234F1Z5',regime:'regular'}]}/>);await screen.findByText('40000000.0000');expect(screen.queryByLabelText('Registered under Rule 14A')).not.toBeInTheDocument();expect(screen.queryByLabelText('Reporting profile closing date')).not.toBeInTheDocument();});
it('closes a dated profile using its native scoped API',async()=>{render(<CompanyGstOutwardProfile company={company} registrations={[{id:reg,number:'27ABCDE1234F1Z5',regime:'regular'}]}/>);await screen.findByText('40000000.0000');fireEvent.change(screen.getByLabelText('Reporting profile closing date'),{target:{value:'2027-04-01'}});fireEvent.click(screen.getByRole('button',{name:/Actions for/}));fireEvent.click(screen.getByRole('menuitem',{name:'Close at selected date'}));await screen.findByText(/Reporting profile closed/);expect(companyCall).toHaveBeenCalledWith('identity','/v1/companies/'+company+'/gst-outward-profiles/'+company,expect.objectContaining({method:'PATCH',body:{valid_to:'2027-04-01'},key:expect.any(String)}));});

it('keeps profile entry out of the history view until explicitly requested', async () => {
 render(<CompanyGstOutwardProfile company={company} registrations={[{id:reg,number:'27ABCDE1234F1Z5',regime:'regular'}]}/>);
 await screen.findByText('40000000.0000');
 expect(screen.queryByLabelText('Registered under Rule 14A')).not.toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'Add outward reporting profile'}));
 expect(screen.getByRole('dialog',{name:'Add outward reporting profile'})).toHaveClass('janso-drawer__panel');
 expect(screen.getByLabelText('Registered under Rule 14A').closest('.janso-filter-bar')).toBeNull();
 expect(screen.getByRole('group',{name:'Turnover and registration status'})).toBeVisible();
 expect(screen.getByRole('group',{name:'Supporting evidence'})).toBeVisible();
});

it('requires new valid evidence when a previously accepted file is replaced', async () => {
 vi.stubGlobal('crypto',{randomUUID:()=>company,subtle:{digest:vi.fn().mockResolvedValue(new ArrayBuffer(32))}});
 render(<CompanyGstOutwardProfile company={company} registrations={[{id:reg,number:'27ABCDE1234F1Z5',regime:'regular'}]}/>);
 await screen.findByText('40000000.0000');fireEvent.click(screen.getByRole('button',{name:'Add outward reporting profile'}));
 fireEvent.change(screen.getByLabelText('Reporting profile GSTIN'),{target:{value:reg}});
 fireEvent.change(screen.getByLabelText('Previous GST financial-year aggregate turnover (INR)'),{target:{value:'40000000.0000'}});
 fireEvent.change(screen.getByLabelText('Registered under Rule 14A'),{target:{value:'NO'}});
 fireEvent.change(screen.getByLabelText('Reporting profile effective from'),{target:{value:'2026-04-01'}});
 fireEvent.change(screen.getByLabelText('Reporting profile evidence reference'),{target:{value:'Registration certificate'}});
 const valid=new File(['proof'],'certificate.pdf');Object.defineProperty(valid,'arrayBuffer',{value:async()=>new ArrayBuffer(1)});
 fireEvent.change(screen.getByLabelText('Reporting profile evidence file'),{target:{files:[valid]}});
 await screen.findByText(/Evidence: certificate.pdf/);
 expect(screen.getByRole('button',{name:'Save outward reporting profile'})).toBeEnabled();
 const rejected=new File(['oversized'],'replacement.pdf');Object.defineProperty(rejected,'size',{value:11*1024*1024});
 fireEvent.change(screen.getByLabelText('Reporting profile evidence file'),{target:{files:[rejected]}});
 await screen.findByText('Choose evidence up to 10 MB.');
 expect(screen.getByRole('button',{name:'Save outward reporting profile'})).toBeDisabled();
 expect(screen.queryByText(/Evidence: certificate.pdf/)).not.toBeInTheDocument();
});

it('shows loading and retries a failed initial history read without reporting an empty list', async () => {
 const answer=vi.mocked(companyCall).getMockImplementation()!; let failed=true;
 vi.mocked(companyCall).mockImplementation((service,path,request)=>path.includes('/gst-outward-profiles?')&&failed?Promise.reject({status:503,message:'Reporting history unavailable'}):answer(service,path,request));
 render(<CompanyGstOutwardProfile company={company} registrations={[{id:reg,number:'27ABCDE1234F1Z5',regime:'regular'}]}/>);
 expect(screen.getByRole('status',{name:'Loading GST outward reporting profiles'})).toBeInTheDocument();
 await screen.findByText(/Reporting history unavailable/);
 expect(screen.queryByRole('table',{name:'Dated GST outward reporting profiles'})).not.toBeInTheDocument();
 failed=false; fireEvent.click(screen.getByRole('button',{name:'Reload outward reporting profiles'}));
 await screen.findByText('40000000.0000');
});

it('validates turnover, retains a failed profile and reuses its key when saving again', async () => {
 vi.stubGlobal('crypto',{randomUUID:()=>company,subtle:{digest:vi.fn().mockResolvedValue(new ArrayBuffer(32))}});
 const answer=vi.mocked(companyCall).getMockImplementation()!;let failed=true;
 vi.mocked(companyCall).mockImplementation((service,path,request)=>request?.method==='POST'?(failed?(failed=false,Promise.reject({status:503,message:'Save result unavailable'})):Promise.resolve({id:company})):answer(service,path,request));
 render(<CompanyGstOutwardProfile company={company} registrations={[{id:reg,number:'27ABCDE1234F1Z5',regime:'regular'}]}/>);
 await screen.findByText('40000000.0000');fireEvent.click(screen.getByRole('button',{name:'Add outward reporting profile'}));
 fireEvent.change(screen.getByLabelText('Reporting profile GSTIN'),{target:{value:reg}});
 fireEvent.change(screen.getByLabelText('Previous GST financial-year aggregate turnover (INR)'),{target:{value:'-1'}});
 fireEvent.change(screen.getByLabelText('Registered under Rule 14A'),{target:{value:'YES'}});
 fireEvent.change(screen.getByLabelText('Reporting profile effective from'),{target:{value:'2026-04-01'}});
 fireEvent.change(screen.getByLabelText('Reporting profile evidence reference'),{target:{value:'Registration certificate'}});
 const proof=new File(['proof'],'certificate.pdf');Object.defineProperty(proof,'arrayBuffer',{value:async()=>new ArrayBuffer(1)});
 fireEvent.change(screen.getByLabelText('Reporting profile evidence file'),{target:{files:[proof]}});
 await screen.findByText(/Evidence: certificate.pdf/);
 fireEvent.submit(screen.getByRole('form',{name:'Add outward reporting profile'}));
 await screen.findByText('Enter a non-negative turnover with up to four decimal places.');
 expect(vi.mocked(companyCall).mock.calls.filter(call=>call[2]?.method==='POST')).toHaveLength(0);
 fireEvent.change(screen.getByLabelText('Previous GST financial-year aggregate turnover (INR)'),{target:{value:'40000000.0000'}});
 fireEvent.submit(screen.getByRole('form',{name:'Add outward reporting profile'}));await screen.findByText('Save result unavailable');
 expect(screen.getByLabelText('Registered under Rule 14A')).toHaveValue('YES');
 expect(screen.getByLabelText('Previous GST financial-year aggregate turnover (INR)')).toHaveValue('40000000.0000');
 fireEvent.submit(screen.getByRole('form',{name:'Add outward reporting profile'}));await screen.findByText(/Dated GST outward reporting profile saved/);
 const writes=vi.mocked(companyCall).mock.calls.filter(call=>call[2]?.method==='POST');
 expect(writes).toHaveLength(2);expect(writes[0][2]?.key).toBe(writes[1][2]?.key);
 expect(writes[1][2]?.body).toMatchObject({registration_id:reg,annual_turnover:'40000000.0000',currency:'INR',rule_14a:true,valid_from:'2026-04-01',evidence_hash:'0'.repeat(64)});
});
