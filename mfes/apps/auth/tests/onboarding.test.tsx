import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { renderScreen } from './helpers';
import Page from '../app/onboarding/page';
const { goTo, signIn } = vi.hoisted(() => ({ goTo: vi.fn(), signIn: vi.fn() }));
vi.mock('../app/lib/navigate', () => ({ goTo, consoleUrl: () => 'http://localhost:4320' }));
vi.mock('next-auth/react', () => ({ signIn }));
vi.mock('../app/lib/provider-client', () => ({ authProviderId: async () => 'authentik', useAuthProvider: () => 'authentik' })); // these suites exercise the Authentik provider
beforeEach(() => { vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ linked: false, email_verified: true, options: { countries: [{ code: 'IN', name: 'India' }], states: [{ code: 'IN-MH', name: 'Maharashtra', country_code: 'IN' }], currencies: [{ code: 'INR', name: 'Indian rupee' }], timezones: [{ code: 'Asia/Kolkata', name: 'Asia/Kolkata' }], languages: [{ code: 'en', name: 'English' }] } }))); goTo.mockReset(); signIn.mockReset(); window.history.replaceState({}, '', '/onboarding'); });
it('explains the access check without suggesting that a returning user needs setup', () => {
  vi.mocked(fetch).mockReturnValue(new Promise(() => {})); renderScreen(<Page />);
  expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Getting things ready');
  expect(screen.getByRole('status')).toHaveTextContent('Checking your workspace access');
  expect(screen.getByRole('list', { name: 'Workspace progress' }).querySelector('[aria-current="step"]')).toHaveTextContent('Check workspace access');
  expect(screen.queryByText(/Have a workspace invitation/)).not.toBeInTheDocument();
  expect(screen.queryByText('Set up your workspace')).not.toBeInTheDocument();
});
it('shows confirmed access and the opening step while navigation completes', async () => {
  vi.mocked(fetch).mockResolvedValue(Response.json({ linked: true })); renderScreen(<Page />);
  expect(await screen.findByRole('heading', { name: 'Opening your workspace' })).toBeInTheDocument();
  expect(screen.getByRole('status')).toHaveTextContent('Workspace access confirmed');
  expect(screen.getByRole('list', { name: 'Workspace progress' }).querySelector('[aria-current="step"]')).toHaveTextContent('Open your workspace');
  expect(screen.queryByText(/Have a workspace invitation/)).not.toBeInTheDocument();
});
it('restores the progress screen when retrying a failed access check', async () => {
  vi.mocked(fetch).mockRejectedValueOnce(new Error('Offline')); renderScreen(<Page />);
  await screen.findByRole('alert'); vi.mocked(fetch).mockReturnValue(new Promise(() => {}));
  await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
  expect(screen.getByRole('status')).toHaveTextContent('Checking your workspace access');
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});
it('shows business setup only to a verified unlinked account', async () => {
  renderScreen(<Page />); expect(await screen.findByRole('textbox', { name: 'Workspace name' })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Set up your workspace' })).toBeInTheDocument();
  expect(screen.getByText(/Have a workspace invitation/)).toBeInTheDocument();
  expect(screen.queryByLabelText(/password/i)).not.toBeInTheDocument();
  expect(screen.queryByRole('textbox', { name: 'Workspace ID' })).not.toBeInTheDocument();
  expect(screen.getAllByRole('combobox')).toHaveLength(2);
});
it('uses API-backed selectors for every regional default', async () => {
  renderScreen(<Page />); await screen.findByRole('textbox', { name: 'Workspace name' });
  for (const name of ['Country', 'State']) expect(screen.getByRole('combobox', { name })).toBeInTheDocument();
  expect(screen.getByRole('combobox', { name: 'Country' }).closest('.janso-form-grid')).toBe(screen.getByRole('combobox', { name: 'State' }).closest('.janso-form-grid'));
});
it('prefills the saved registration region and lets the user change it', async () => {
  vi.mocked(fetch).mockResolvedValue(Response.json({ linked: false, email_verified: true,
    registration_region: { country_code: 'US', state_code: 'US-CA' }, options: {
      countries: [{ code: 'IN', name: 'India' }, { code: 'US', name: 'United States' }],
      states: [{ code: 'US-CA', name: 'California', country_code: 'US' }], currencies: [{ code: 'USD', name: 'Dollar' }],
      languages: [{ code: 'en', name: 'English' }], timezones: [{ code: 'UTC', name: 'UTC' }],
    } }));
  renderScreen(<Page />); expect(await screen.findByRole('combobox', { name: 'Country' })).toHaveValue('US');
  expect(screen.getByRole('combobox', { name: 'State' })).toHaveValue('US-CA');
  await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Country' }), 'IN');
  expect(screen.getByRole('combobox', { name: 'State' })).toHaveValue('');
});
it('blocks workspace setup and offers retry when reference lists are empty', async () => {
  vi.mocked(fetch).mockResolvedValue(Response.json({ linked: false, email_verified: true, options: { countries: [], currencies: [], timezones: [], languages: [] } }));
  renderScreen(<Page />); expect(await screen.findByRole('alert')).toHaveTextContent('unavailable');
  expect(screen.queryByRole('button', { name: 'Create workspace' })).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Try again' })).toBeEnabled();
});
it('returns linked accounts to their requested Console page', async () => {
  window.history.replaceState({}, '', '/onboarding?returnTo=' + encodeURIComponent('http://localhost:4320/platform'));
  vi.mocked(fetch).mockResolvedValue(Response.json({ linked: true, email_verified: true })); renderScreen(<Page />);
  await waitFor(() => expect(goTo).toHaveBeenCalledWith('http://localhost:4320/platform'));
});
it('rejects an external return URL', async () => {
  window.history.replaceState({}, '', '/onboarding?returnTo=https://evil.invalid');
  vi.mocked(fetch).mockResolvedValue(Response.json({ linked: true })); renderScreen(<Page />);
  await waitFor(() => expect(goTo).toHaveBeenCalledWith('http://localhost:4320'));
});
it('requires sign-in for an absent session', async () => {
  vi.mocked(fetch).mockResolvedValue(new Response(null, { status: 401 })); renderScreen(<Page />);
  await userEvent.click(await screen.findByRole('button', { name: 'Sign in to continue' }));
  expect(signIn).toHaveBeenCalledWith('authentik', { callbackUrl: window.location.href }, { prompt: 'login', max_age: '1' });
});
it('requires manual verification before workspace provisioning', async () => {
  vi.mocked(fetch).mockResolvedValue(Response.json({ linked: false, email_verified: false })); renderScreen(<Page />);
  expect(await screen.findByText(/must be verified/)).toBeInTheDocument(); expect(screen.queryByRole('button', { name: 'Create workspace' })).not.toBeInTheDocument();
});
it.each([403, 500])('handles unavailable status (%i)', async status => {
  vi.mocked(fetch).mockResolvedValue(new Response(null, { status })); renderScreen(<Page />);
  expect(await screen.findByRole('alert')).toHaveTextContent('unavailable'); expect(screen.getByRole('button', { name: 'Try again' })).toBeEnabled();
});
it('creates a workspace once and continues to Console', async () => {
  renderScreen(<Page />); await screen.findByRole('textbox', { name: 'Workspace name' });
  await userEvent.type(screen.getByRole('textbox', { name: 'Workspace name' }), 'My Books');
  await userEvent.selectOptions(screen.getByRole('combobox', { name: 'State' }), 'IN-MH');
  await userEvent.type(screen.getByRole('textbox', { name: 'Your full name' }), 'Owner');
  vi.mocked(fetch).mockResolvedValueOnce(Response.json({ id: 'tenant' }, { status: 201 }));
  await userEvent.click(screen.getByRole('button', { name: 'Create workspace' }));
  await waitFor(() => expect(goTo).toHaveBeenCalledWith('http://localhost:4320/'));
  expect(screen.getByRole('heading', { name: 'Opening your workspace' })).toBeInTheDocument();
  const body = JSON.parse(String(vi.mocked(fetch).mock.lastCall![1]?.body));
  expect(body).toMatchObject({ country_code: 'IN', state_code: 'IN-MH' });
  for (const field of ['slug', 'currency_code', 'timezone', 'locale', 'administrator_email']) expect(body).not.toHaveProperty(field);
});
it.each([403, 409, 422, 500])('keeps a failed workspace form editable (%i)', async status => {
  renderScreen(<Page />); await screen.findByRole('textbox', { name: 'Workspace name' });
  await userEvent.type(screen.getByRole('textbox', { name: 'Workspace name' }), 'My Books');
  await userEvent.selectOptions(screen.getByRole('combobox', { name: 'State' }), 'IN-MH');
  await userEvent.type(screen.getByRole('textbox', { name: 'Your full name' }), 'Owner');
  vi.mocked(fetch).mockResolvedValueOnce(Response.json({ error: { message: 'Check workspace details' } }, { status }));
  await userEvent.click(screen.getByRole('button', { name: 'Create workspace' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Check workspace details');
  expect(screen.getByRole('combobox', { name: 'State' })).toHaveValue('IN-MH');
  expect(goTo).not.toHaveBeenCalled();
});
