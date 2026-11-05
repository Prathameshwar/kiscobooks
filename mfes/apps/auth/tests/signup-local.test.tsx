import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderScreen } from './helpers';
import { beforeEach, expect, it, vi } from 'vitest';
import Page from '../app/signup/page';

const options = { countries: [{ code: 'IN', name: 'India' }], states: [{ code: 'IN-MH', name: 'Maharashtra', country_code: 'IN' }] };
const availability = (extra: object = {}) => ({ ok: true, json: async () => ({ enabled: true, mode: 'manual-review', workspace_enabled: true, options, ...extra }) });
beforeEach(() => { window.history.replaceState({}, '', '/signup'); });

async function submitAccount() {
  await waitFor(() => expect(screen.getByRole('button', { name: 'Create account' })).toBeEnabled());
  fireEvent.change(screen.getByRole('combobox', { name: 'State' }), { target: { value: 'IN-MH' } });
  for (const [label, value] of [['Full name', 'New Account'], ['Username', 'new-account'], ['Email address', 'new@example.invalid']])
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
  const password = crypto.randomUUID();
  for (const label of ['Password', 'Confirm password']) fireEvent.change(screen.getByLabelText(label, { exact: true }), { target: { value: password } });
  await userEvent.click(screen.getByRole('button', { name: 'Create account' }));
}

it('says the local provider signs in by username or email, in the hint and on the approval screen', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(availability({ sign_in: 'username_or_email' }))
    .mockResolvedValueOnce({ status: 201, json: async () => ({ created: true, status: 'pending-review' }) }));
  renderScreen(<Page />);
  await waitFor(() => expect(screen.getByText(/you can also use your email address/)).toBeInTheDocument());
  expect(screen.getByText(/Used to sign in/)).toBeInTheDocument();
  await submitAccount();
  expect(await screen.findByText('Once approved, sign in with your username or email address and the password you chose.')).toBeInTheDocument();
  expect(screen.queryByText(/with the username and password/)).not.toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Back to sign in' })).toHaveAttribute('href', '/login');
});
it('keeps the username wording when the server does not report email sign-in', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(availability()).mockResolvedValueOnce({ status: 201, json: async () => ({ created: true, status: 'pending-review' }) }));
  renderScreen(<Page />);
  await waitFor(() => expect(screen.getByText(/Used to sign in/)).toBeInTheDocument());
  await submitAccount();
  expect(await screen.findByText('Once approved, sign in with the username and password you chose.')).toBeInTheDocument();
});
it.each(['username', 'phone', true, 1, null])('treats an unknown sign_in hint (%j) as the default wording', async hint => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(availability({ sign_in: hint })));
  renderScreen(<Page />);
  await waitFor(() => expect(screen.getByText(/Used to sign in/)).toBeInTheDocument());
});
