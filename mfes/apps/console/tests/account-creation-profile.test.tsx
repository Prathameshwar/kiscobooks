import {render,screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {beforeEach,expect,it,vi} from 'vitest';
import {AccountCreationProfile,useAccountCreationProfile} from '../app/components/AccountCreationProfile';
import {serviceCall} from '../app/lib/service-call';
import {COMPANY,ID,response,form} from './accounting-configuration-fixtures';
vi.mock('../app/lib/service-call',async original=>({...await original<typeof import('../app/lib/service-call')>(),serviceCall:vi.fn()}));
const api=vi.mocked(serviceCall),save=vi.fn();
function Form({kind='BANK'}:{kind?:string}){
  const profile=useAccountCreationProfile(COMPANY,kind,true);
  return <><AccountCreationProfile company={COMPANY} profile={profile} disabled={false} errors={{}}/><button onClick={()=>save(profile.capture())}>Capture profile</button></>;
}
beforeEach(()=>{vi.clearAllMocks();api.mockImplementation(async(_,request)=>response(request.path,request.method,request.body) as never);});
it('does not load profiles for ordinary accounts',async()=>{
  render(<Form kind="GENERAL"/>);await userEvent.click(screen.getByRole('button',{name:'Capture profile'}));
  expect(api).not.toHaveBeenCalled();expect(save).toHaveBeenCalledWith({body:{},errors:{}});
});
it('requires the bank profile before an opening can be posted',async()=>{
  render(<Form/>);expect(await screen.findByRole('combobox',{name:/Company bank/})).toBeVisible();
  await userEvent.click(screen.getByRole('button',{name:'Capture profile'}));
  expect(save.mock.calls.at(-1)![0].errors['opening.profile.company_bank_id']).toBeTruthy();
  const bank=screen.getByRole('combobox',{name:/Company bank/});await userEvent.click(bank);
  await userEvent.click(await screen.findByRole('option',{name:'Company settlement bank'}));
  await userEvent.click(screen.getByRole('button',{name:'Capture profile'}));
  expect(save.mock.calls.at(-1)![0]).toMatchObject({body:{bank_profile:{company_bank_id:ID}},errors:{}});
});
it('does not capture an inaccessible tax profile',async()=>{
  api.mockResolvedValue({...form('account-tax-profiles'),can_create:false} as never);
  render(<Form kind="TAX"/>);expect(await screen.findByText(/does not allow creating/)).toBeVisible();
  await userEvent.click(screen.getByRole('button',{name:'Capture profile'}));expect(save.mock.calls.at(-1)![0].errors['opening.profile']).toBeTruthy();
});
