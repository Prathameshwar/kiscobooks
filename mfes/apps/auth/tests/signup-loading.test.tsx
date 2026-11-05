import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { renderScreen } from './helpers';
import Page from '../app/signup/page';

const options = {
  countries: [{ code: 'IN', name: 'India' }, { code: 'US', name: 'United States' }],
  states: [{ code: 'IN-MH', name: 'Maharashtra', country_code: 'IN' }],
};
const ready = () => Response.json({ enabled: true, mode: 'manual-review', options });
const unavailable = () => Response.json({ enabled: false });

/** The availability request stays in flight until the test releases it, like a slow first load. */
let release!: (response: Response) => void;
beforeEach(() => {
  window.history.replaceState({}, '', '/signup');
  vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(resolve => { release = resolve; })));
});

const details = ['Full name', 'Username', 'Email address'] as const;

it('lets the person start typing while the form is still being prepared', async () => {
  renderScreen(<Page />);
  for (const label of details) expect(screen.getByLabelText(label)).toBeEnabled();
  expect(screen.getByLabelText('Password', { exact: true })).toBeEnabled();
  expect(screen.getByLabelText('Confirm password', { exact: true })).toBeEnabled();
  await userEvent.type(screen.getByLabelText('Full name'), 'New Account');
  expect(screen.getByLabelText('Full name')).toHaveValue('New Account');
});

it('says what is loading instead of showing a form that looks switched off', () => {
  renderScreen(<Page />);
  const country = screen.getByRole('combobox', { name: 'Country' });
  const state = screen.getByRole('combobox', { name: 'State' });
  expect(country).toHaveAttribute('aria-busy', 'true');
  expect(state).toHaveAttribute('aria-busy', 'true');
  expect(screen.getByText('Loading countries…', { selector: 'p' })).toBeInTheDocument();
  expect(screen.getByText('Loading states…', { selector: 'p' })).toBeInTheDocument();
  expect(country).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Create account' })).toBeDisabled();
});

it('cannot be submitted before the choices arrive', () => {
  renderScreen(<Page />);
  fireEvent.submit(screen.getByRole('form', { name: 'Create account' }));
  expect(fetch).toHaveBeenCalledTimes(1);
});

it('keeps what was typed when the choices arrive and then enables the rest', async () => {
  renderScreen(<Page />);
  await userEvent.type(screen.getByLabelText('Username'), 'new-account');
  release(ready());
  await waitFor(() => expect(screen.getByRole('button', { name: 'Create account' })).toBeEnabled());
  expect(screen.getByLabelText('Username')).toHaveValue('new-account');
  expect(screen.getByRole('combobox', { name: 'Country' })).toHaveValue('IN');
  expect(screen.getByRole('combobox', { name: 'Country' })).toBeEnabled();
  expect(screen.queryByText('Loading countries…', { selector: 'p' })).not.toBeInTheDocument();
  expect(screen.queryByText('Loading states…', { selector: 'p' })).not.toBeInTheDocument();
});

it('switches the form off with a reason, and keeps the details, when signup is unavailable', async () => {
  renderScreen(<Page />);
  await userEvent.type(screen.getByLabelText('Username'), 'new-account');
  release(unavailable());
  await screen.findByText(/Account creation is currently unavailable/);
  expect(screen.getByLabelText('Username')).toBeDisabled();
  expect(screen.getByLabelText('Username')).toHaveValue('new-account');
  expect(screen.getByRole('button', { name: 'Create account' })).toBeDisabled();
  expect(screen.queryByText('Loading countries…', { selector: 'p' })).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
  expect(screen.getByLabelText('Username')).toBeEnabled();
  release(ready());
  await waitFor(() => expect(screen.getByRole('button', { name: 'Create account' })).toBeEnabled());
  expect(screen.getByLabelText('Username')).toHaveValue('new-account');
});

it('does not say how sign-in works until the server has said which provider it is', async () => {
  renderScreen(<Page />);
  const username = screen.getByLabelText('Username');
  expect(username).toHaveAccessibleDescription('Lowercase letters, numbers, . _ or -');
  release(Response.json({ enabled: true, mode: 'manual-review', sign_in: 'username_or_email', options }));
  await waitFor(() => expect(username).toHaveAccessibleDescription(/you can also use your email address/));
});
