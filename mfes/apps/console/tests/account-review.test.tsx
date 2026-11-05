import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { AccountDetail, accountReturnTo } from '../app/platform/accounts/AccountDetail';
import { AccountDirectory } from '../app/platform/accounts/AccountDirectory';

const { call, navigate } = vi.hoisted(() => ({ call:vi.fn(),navigate:vi.fn() }));
vi.mock('../app/lib/platform-api', async importOriginal => ({ ...await importOriginal<typeof import('../app/lib/platform-api')>(),platformCall:call }));
vi.mock('../app/lib/navigate', () => ({ goTo:navigate,signInUrl:()=>'http://localhost:4310/login' }));
const id = '01900000-0000-7000-8000-000000000001';
const detail = {id,name:'New applicant',username:'new-applicant',email:'new@example.invalid',workspace_name:'New Books',status:'pending',needs_attention:false,country_code:'IN',state_code:'IN-MH',provider_active:false,provider_verified:false,version:1,created_at:'2026-10-21T10:00:00Z',updated_at:'2026-10-21T10:00:00Z',history:[]};
beforeEach(() => { call.mockReset();navigate.mockReset();call.mockResolvedValue(detail);window.history.replaceState(null,'','/platform/accounts'); });
it('shows independent identity and provider status with safe back navigation', async () => {
  render(<AccountDetail accountId={id} permissions={['platform.account.review']} returnTo="https://evil.invalid" />);
  expect(await screen.findByRole('heading',{name:'New applicant'})).toBeInTheDocument();
  expect(screen.getByRole('link',{name:'Back to account approvals'})).toHaveAttribute('href','/platform/accounts');
  expect(screen.getByText('new@example.invalid')).toBeInTheDocument();
  expect(screen.getByRole('checkbox')).not.toBeChecked();
  expect(accountReturnTo('/platform/accounts?status=pending')).toBe('/platform/accounts?status=pending');
});
it('puts the review decision in a card footer, Cancel first, off the setup-wizard classes', async () => {
  const { container } = render(<AccountDetail accountId={id} permissions={['platform.account.review']} />);
  await screen.findByRole('heading',{name:'New applicant'});
  const footer = [...container.querySelectorAll('.janso-card__footer')].find(node => node.querySelector('.janso-form-actions'))!;
  const links = within(footer as HTMLElement).getAllByRole('link');
  expect(links[0]).toHaveAccessibleName('Cancel');
  expect(footer.querySelector('.janso-form-actions')).toContainElement(screen.getByRole('button',{name:'Review decision'}));
  // The fields disable as a group through a fieldset, which is also what keeps the actions outside it.
  expect(container.querySelector('fieldset.janso-setup__fields')).toBeInTheDocument();
  expect(container.querySelector('div.janso-setup__actions')).not.toBeInTheDocument();
});
it.each(['manual', 'queued'])('validates attestation and keeps manual sharing after approval (%s)', async notificationStatus => {
  render(<AccountDetail accountId={id} permissions={['platform.account.review']} />);
  await screen.findByRole('heading',{name:'New applicant'});
  await userEvent.type(screen.getByRole('textbox',{name:'Review reason'}),'Checked identity independently');
  await userEvent.click(screen.getByRole('button',{name:'Review decision'}));
  expect(screen.getByRole('alert')).toHaveTextContent('independently checked');
  await userEvent.click(screen.getByRole('checkbox'));
  await userEvent.click(screen.getByRole('button',{name:'Review decision'}));
  expect(screen.getByRole('dialog')).toBeInTheDocument();
  expect(screen.getByRole('dialog')).toHaveTextContent('Account-ready email is sent when delivery is configured. Manual sharing remains available.');
  expect(screen.getByRole('dialog')).not.toHaveTextContent('No email will be sent.');
  call.mockResolvedValue({...detail,status:'approved',provider_active:true,provider_verified:true,version:3,handoff:{username:'new-applicant',sign_in_url:'https://auth.test/login',invitation_url:null,notification_status:notificationStatus},history:[{id,action:'approve',reason:'Reviewed',workspace_name:'New Books',status:'completed',created_at:detail.created_at,completed_at:detail.created_at,actor_id:id,attested:true,error_code:null}]});
  await userEvent.click(screen.getByRole('button',{name:'Approve account'}));
  expect(await screen.findByText('Account approved. The workspace and administrator access are ready.')).toBeInTheDocument();
  expect(call).toHaveBeenCalledWith(`/v1/platform/accounts/${id}/review`,'POST',expect.objectContaining({action:'approve',attested:true,version:1}),expect.any(String));
  expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  expect(screen.getByRole('textbox',{name:'Account access link'})).toHaveValue('https://auth.test/login');
  expect(screen.getByRole('button',{name:'Copy access link'})).toBeEnabled();
  expect(screen.getByRole('button',{name:'Copy login details'})).toBeEnabled();
  expect(screen.getByText(notificationStatus === 'queued' ? /Account-ready email is queued/ : /Automatic email is not configured/)).toBeInTheDocument();
});
it.each([401,403,404,409,422,429,503])('shows safe read errors for %s', async status => {
  call.mockRejectedValue({status,message:'Registration unavailable'});
  render(<AccountDetail accountId={id} permissions={[]} />);
  expect(await screen.findByRole('alert')).toHaveTextContent('Registration unavailable');
  expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
});
it.each([{status:'approved'}, {needs_attention:true}, {history:[{id,action:'approve',reason:'Reviewed',status:'queued',created_at:detail.created_at,completed_at:null,error_code:'provider_unavailable'}]}])('hides unsafe review controls for %j', async changed => {
  call.mockResolvedValue({...detail,...changed});render(<AccountDetail accountId={id} permissions={['platform.account.review']} />);
  await screen.findByRole('heading',{name:'New applicant'});expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
});
it('shows the shared directory and imports only bounded pages on refresh', async () => {
  call.mockImplementation(async path => path.includes('/sync') ? {imported:1,next_page:null} : {items:[detail],page:{next_cursor:null,has_more:false}});
  render(<AccountDirectory />);await screen.findByText('New applicant');
  expect(screen.getByRole('table',{name:'Account registrations'})).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button',{name:'Refresh accounts'}));
  await waitFor(()=>expect(call).toHaveBeenCalledWith('/v1/platform/accounts/sync?page=1','POST'));
  await userEvent.click(screen.getByRole('button',{name:/Actions.*New applicant/}));
  await userEvent.click(screen.getByRole('menuitem',{name:'View registration'}));
  expect(navigate).toHaveBeenCalledWith(expect.stringContaining(`/platform/accounts/${id}?returnTo=`));
});
it('imports a newly registered account automatically before displaying the approval list', async () => {
  let imported = false;
  call.mockImplementation(async path => {
    if (path.includes('/sync')) { imported = true; return { imported: 1, next_page: null }; }
    return { items: imported ? [{ ...detail, username: 'tenant3' }] : [], page: { next_cursor: null, has_more: false } };
  });
  render(<AccountDirectory />);
  expect(await screen.findByText('tenant3')).toBeInTheDocument();
  expect(call.mock.calls[0]).toEqual(['/v1/platform/accounts/sync?page=1', 'POST']);
});
it('keeps saved approval records visible if the automatic provider check fails', async () => {
  call.mockImplementation(async path => {
    if (path.includes('/sync')) throw { status: 503, message: 'Provider unavailable' };
    return { items: [detail], page: { next_cursor: null, has_more: false } };
  });
  render(<AccountDirectory />);
  expect(await screen.findByText('New applicant')).toBeInTheDocument();
  expect(screen.getByText(/Showing saved records/)).toBeInTheDocument();
});

it('resolves regional names and explicitly reconciles drift without approving', async () => {
  call.mockImplementation(async (path,method) => path.endsWith('/options') ? {countries:[{code:'IN',name:'India'}],states:[{code:'IN-MH',name:'Maharashtra',country_code:'IN'}]} : method==='POST' ? {...detail,version:4} : {...detail,needs_attention:true,version:3});
  render(<AccountDetail accountId={id} permissions={['platform.account.review']} />);
  expect(await screen.findByText('India')).toBeInTheDocument();
  expect(screen.getByText('Maharashtra')).toBeInTheDocument();
  await userEvent.type(screen.getByRole('textbox',{name:'Reconciliation reason'}),'Reviewed corrected registration');
  await userEvent.click(screen.getByRole('button',{name:'Reconcile current details'}));
  expect(await screen.findByText(/Current details reconciled/)).toBeInTheDocument();
  expect(call).toHaveBeenCalledWith(`/v1/platform/accounts/${id}/reconcile`,'POST',{version:3,reason:'Reviewed corrected registration'});
  expect(screen.getByRole('checkbox')).not.toBeChecked();
});

it('restores only a bounded per-reviewer decision draft and requires fresh attestation',async()=>{
  sessionStorage.setItem('janso-platform-draft:account-review:operator:'+id,JSON.stringify({at:Date.now(),key:'prior-key',draft:{action:'approve',reason:'Previously reviewed',workspace_name:''}}));
  render(<AccountDetail accountId={id} draftScope="operator" permissions={['platform.account.review']} />);
  await screen.findByRole('heading',{name:'New applicant'});
  expect(screen.getByRole('textbox',{name:'Review reason'})).toHaveValue('Previously reviewed');
  expect(screen.getByRole('checkbox')).not.toBeChecked();
  expect(screen.getByText(/Your decision draft was restored/)).toBeInTheDocument();
  expect(sessionStorage.getItem('janso-platform-draft:account-review:operator:'+id)).toBeNull();
});
