import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderScreen } from './helpers';
import { beforeEach, expect, it, vi } from 'vitest';
import Page from '../app/signup/page';
import { PASSWORD_RULE_MESSAGE } from '../app/lib/registration-input';
beforeEach(() => { vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ enabled: true, mode: 'manual-review', workspace_enabled: true, options: {
  countries: [{ code: 'IN', name: 'India' }], states: [{ code: 'IN-MH', name: 'Maharashtra', country_code: 'IN' }],
} }) })); });
async function fill() {
  await waitFor(() => expect(screen.getByRole('button', { name: 'Create account' })).toBeEnabled());
  fireEvent.change(screen.getByRole('combobox', { name: 'State' }), { target: { value: 'IN-MH' } });
  for (const [label, value] of [['Full name','New Account'],['Username','new-account'],['Email address','new@example.invalid']]) {
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
  }
  const password = crypto.randomUUID();
  for (const label of ['Password','Confirm password']) fireEvent.change(screen.getByLabelText(label, { exact: true }), { target: { value: password } });
}
it('renders accessible fields and sign-in link without the approval callout', async () => {
  renderScreen(<Page />); await fill();
  expect(screen.getByRole('heading', { name: 'Create your account' })).toBeInTheDocument();
  expect(screen.getByLabelText('Password', { exact: true })).toHaveAttribute('autocomplete', 'new-password');
  expect(screen.getByLabelText('Email address')).toHaveAttribute('type', 'email');
  expect(screen.queryByRole('textbox', { name: 'Workspace name' })).not.toBeInTheDocument();
  expect(screen.queryByText('Administrator approval comes next')).not.toBeInTheDocument();
  expect(screen.queryByText(/A platform administrator checks your details and email/)).not.toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Sign in' })).toHaveAttribute('href', '/login');
});
it('keeps a local invitation through account creation and explains the approval step', async () => {
  const tenant = '01900000-0000-7000-8000-000000000001', invitation = '01900000-0000-7000-8000-000000000002';
  const returnTo = `/accept?tenant=${tenant}&invitation=${invitation}`;
  window.history.replaceState({}, '', '/signup?returnTo=' + encodeURIComponent(returnTo));
  renderScreen(<Page />); await fill();
  expect(screen.queryByRole('textbox', { name: 'Workspace name' })).not.toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Back to invitation' })).toHaveAttribute('href', returnTo);
  expect(screen.queryByText('Administrator approval comes next')).not.toBeInTheDocument();
  expect(screen.queryByText('Approval activates your account so you can join the workspace in your invitation.')).not.toBeInTheDocument();
  expect(screen.queryByText(/Your workspace is created automatically after approval/)).not.toBeInTheDocument();
  vi.mocked(fetch).mockResolvedValueOnce({ status: 201, json: async () => ({ created: true, status: 'pending-review' }) } as Response);
  await userEvent.click(screen.getByRole('button', { name: 'Create account' }));
  expect(await screen.findByRole('link', { name: 'Return to invitation' })).toHaveAttribute('href', returnTo);
  expect(JSON.parse(vi.mocked(fetch).mock.calls[1][1]?.body as string)).toMatchObject({ invitation_tenant: tenant, invitation_id: invitation });
  expect(JSON.parse(vi.mocked(fetch).mock.calls[1][1]?.body as string)).not.toHaveProperty('workspace_name');
  expect(screen.getByText(/once your account is approved and your email is verified/i)).toBeInTheDocument();
});
it('rejects an external invitation return destination', async () => {
  window.history.replaceState({}, '', '/signup?returnTo=' + encodeURIComponent('https://evil.test/accept?tenant=t&invitation=i'));
  renderScreen(<Page />);
  await waitFor(() => expect(screen.getByRole('button', { name: 'Create account' })).toBeEnabled());
  expect(screen.queryByRole('link', { name: 'Back to invitation' })).not.toBeInTheDocument();
});
it('validates missing fields locally and focuses the first error', async () => {
  renderScreen(<Page />); const button = screen.getByRole('button', { name: 'Create account' });
  await waitFor(() => expect(button).toBeEnabled()); await userEvent.click(button);
  expect(screen.getByLabelText('Full name')).toHaveFocus();
  expect(screen.getByLabelText('Username')).toHaveAttribute('aria-invalid', 'true'); expect(fetch).toHaveBeenCalledTimes(1);
});
it('rejects short passwords and mismatched confirmation', async () => {
  renderScreen(<Page />); await fill();
  fireEvent.change(screen.getByLabelText('Password', { exact: true }), { target: { value: 'short' } });
  await userEvent.click(screen.getByRole('button', { name: 'Create account' }));
  expect(screen.getByLabelText('Password', { exact: true })).toHaveAttribute('aria-invalid', 'true');
  expect(screen.getByText('Passwords must match.')).toBeInTheDocument(); expect(fetch).toHaveBeenCalledTimes(1);
});
it('submits a six-character password with matching guidance and strength advice', async () => {
  renderScreen(<Page />); await fill();
  const password = crypto.randomUUID().slice(0, 6);
  for (const label of ['Password', 'Confirm password']) fireEvent.change(screen.getByLabelText(label, { exact: true }), { target: { value: password } });
  expect(screen.getByText(PASSWORD_RULE_MESSAGE, { selector: 'p' })).toBeInTheDocument();
  expect(screen.queryByText('Too short')).not.toBeInTheDocument();
  vi.mocked(fetch).mockResolvedValueOnce({ status: 201, json: async () => ({ created: true, status: 'pending-review' }) } as Response);
  await userEvent.click(screen.getByRole('button', { name: 'Create account' }));
  await screen.findByText('Awaiting administrator approval');
  expect(screen.getByRole('link', { name: 'Back to sign in' })).toHaveAttribute('href', '/login');
  expect(screen.queryByRole('link', { name: 'Continue workspace setup' })).not.toBeInTheDocument();
  expect(JSON.parse(vi.mocked(fetch).mock.calls[1][1]?.body as string)).toMatchObject({ password, password_repeat: password });
  expect(JSON.parse(vi.mocked(fetch).mock.calls[1][1]?.body as string)).not.toHaveProperty('workspace_name');
});
it('prevents duplicate submits and focuses the successful approval state', async () => {
  renderScreen(<Page />); await fill(); let complete!: (value: Response) => void;
  vi.mocked(fetch).mockImplementationOnce(() => new Promise(resolve => { complete = resolve; }) as Promise<Response>);
  fireEvent.submit(screen.getByRole('form', { name: 'Create account' })); fireEvent.submit(screen.getByRole('form', { name: 'Create account' }));
  expect(screen.getByRole('button', { name: 'Creating account…' })).toBeDisabled();
  expect(screen.getByLabelText('Full name')).toBeDisabled(); expect(fetch).toHaveBeenCalledTimes(2);
  complete({ status: 201, json: async () => ({ created: true, status: 'pending-review' }) } as Response);
  await screen.findByText('Awaiting administrator approval'); expect(screen.getByLabelText('Account created')).toHaveFocus();
  expect(screen.queryByLabelText('Password', { exact: true })).not.toBeInTheDocument();
});
it.each([403, 422, 429, 500, 503])('handles %i safely and clears passwords', async status => {
  renderScreen(<Page />); await fill();
  vi.mocked(fetch).mockResolvedValueOnce({ status, json: async () => ({ error: 'secret provider error', fields: { username: 'raw details' } }) } as Response);
  await userEvent.click(screen.getByRole('button', { name: 'Create account' }));
  await waitFor(() => expect(screen.getByLabelText('Password', { exact: true })).toHaveValue(''));
  expect(screen.getByText('Choose another username. This one cannot be used.')).toBeInTheDocument();
  expect(screen.getByLabelText('Username')).toHaveFocus();
  expect(screen.queryByText('secret provider error')).not.toBeInTheDocument();
  if (status === 429) expect(screen.getByText(/wait a minute/)).toBeInTheDocument();
});
it('explains uncertain network outcomes and clears passwords for retry', async () => {
  renderScreen(<Page />); await fill(); vi.mocked(fetch).mockRejectedValueOnce(new Error('private'));
  await userEvent.click(screen.getByRole('button', { name: 'Create account' })); await screen.findByText(/could not confirm account creation/);
  expect(screen.getByLabelText('Confirm password', { exact: true })).toHaveValue('');
  expect(screen.getByRole('button', { name: 'Create account' })).toBeEnabled();
});
it.each([false, 'network'])('disables unavailable registration (%s)', async state => {
  if (state === 'network') vi.mocked(fetch).mockRejectedValueOnce(new Error());
  else vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => ({ enabled: false }) } as Response);
  renderScreen(<Page />); await screen.findByText(/Account creation is currently unavailable/);
  expect(screen.getByRole('button', { name: 'Create account' })).toBeDisabled(); expect(screen.getByLabelText('Username')).toBeDisabled();
});
