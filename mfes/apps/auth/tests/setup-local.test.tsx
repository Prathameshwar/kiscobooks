import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderScreen } from './helpers';
import SetupPage from '../app/setup/page';

const { signIn } = vi.hoisted(() => ({ signIn: vi.fn() }));
vi.mock('next-auth/react', () => ({ signIn }));
vi.mock('../app/lib/provider-client', () => ({ authProviderId: async () => 'local', useAuthProvider: () => 'local' }));

const draft = { platform_name: 'KiscoBooks', public_url: 'http://localhost:4320', workspace_name: 'Platform Administration',
  workspace_slug: 'platform-admin', administrator_name: '', country_code: 'IN', currency_code: 'INR', timezone: 'Asia/Kolkata' };
const connections = { ready: true, checks: [{ name: 'Identity', status: 'ready', message: 'Connected' }],
  countries: [{ code: 'IN', name: 'India' }], currencies: [{ code: 'INR', name: 'Indian rupee' }],
  timezones: [{ code: 'Asia/Kolkata', name: 'Asia/Kolkata' }], languages: [{ code: 'en', name: 'English' }] };
const password = 'An Administrator Passphrase 7!';
const LEAK = 'SHOULD-NEVER-BE-SHOWN';
let status: object, administratorExists: boolean, create: () => Response | Promise<Response>;
let fetcher: ReturnType<typeof vi.fn>;
const bodies = () => fetcher.mock.calls.filter(([, options]) => options?.body).map(([, options]) => JSON.parse(String(options.body)));
beforeEach(() => {
  window.history.replaceState({}, '', '/setup');
  administratorExists = false;
  status = { available: true, completed: false, unlocked: false, provider: 'local' };
  create = () => Response.json({ created: true }, { status: 201 });
  signIn.mockReset();
  fetcher = vi.fn(async (input: string, options?: RequestInit) => {
    const action = options?.body ? JSON.parse(String(options.body)).action : new URL(input, 'http://test').searchParams.get('action');
    if (action === 'status') return Response.json(status);
    if (action === 'unlock') {
      status = { available: true, completed: false, unlocked: true, provider: 'local', administratorExists };
      return Response.json({ unlocked: true, saved: true });
    }
    if (action === 'checks') return Response.json(connections);
    if (action === 'create-administrator') return create();
    if (action === 'administrator') return Response.json({ email: 'admin@example.com' });
    return Response.json({ saved: true });
  });
  vi.stubGlobal('fetch', fetcher);
});
afterEach(() => vi.unstubAllGlobals());

const next = () => userEvent.click(screen.getByRole('button', { name: 'Next' }));
async function unlock() {
  renderScreen(<SetupPage />);
  await userEvent.type(await screen.findByLabelText('One-time setup key'), 'local-installation-key');
  await userEvent.click(screen.getByRole('button', { name: 'Unlock setup' }));
  await screen.findByText('Connected');
}
async function toCreateStep() {
  await unlock();
  await next(); await screen.findByLabelText('Platform name');
  await next(); await screen.findByLabelText('Administration workspace name');
  await next();
  await screen.findByRole('heading', { name: 'Create administrator account' });
}
async function enter(label: string, value: string) {
  await userEvent.click(screen.getByLabelText(label));
  await userEvent.paste(value);
}
async function fillAdministrator(values: { name?: string; email?: string; password?: string; again?: string } = {}) {
  const { name = 'Platform Admin', email = 'Admin@Example.Test', password: secret = password, again = secret } = values;
  if (name) await enter('Administrator full name', name);
  if (email) await enter('Administrator email address', email);
  if (secret) await enter('Password', secret);
  if (again) await enter('Confirm password', again);
  await userEvent.tab(); // leave the last field, as a person would: the email is tidied on blur
}
const createButton = () => screen.getByRole('button', { name: 'Create administrator' });

describe('first administrator creation (local provider)', () => {
  it('adds a "Create administrator account" step before signing in as the administrator', async () => {
    await toCreateStep();
    const stepper = screen.getByRole('navigation', { name: 'Setup progress' });
    expect(stepper).toHaveTextContent('Create administrator account');
    expect(stepper).toHaveTextContent('First administrator');
    expect(screen.getByLabelText('Password', { exact: true })).toHaveAttribute('autocomplete', 'new-password');
    expect(document.body).not.toHaveTextContent('Authentik');
    // The status is read again after unlocking, because only an unlocked caller may learn it.
    expect(fetcher.mock.calls.filter(([input]) => String(input).includes('action=status'))).toHaveLength(2);
  });
  it('creates the account, forgets the passwords, then moves to signing in as the administrator', async () => {
    await toCreateStep();
    await fillAdministrator();
    await userEvent.click(createButton());
    await screen.findByRole('heading', { name: 'First administrator' });
    const sent = bodies().find(body => body.action === 'create-administrator');
    expect(sent).toEqual({ action: 'create-administrator', name: 'Platform Admin', email: 'Admin@example.test', password, password_repeat: password });
    // The name is carried into the saved draft for the next step; the password is not stored.
    const saved = bodies().filter(body => body.action === 'save').at(-1);
    expect(saved.draft.administrator_name).toBe('Platform Admin');
    expect(JSON.stringify(bodies().filter(body => body.action === 'save'))).not.toContain(password);
    expect(screen.getByLabelText('Administrator full name')).toHaveValue('Platform Admin');
    expect(document.body.innerHTML).not.toContain(password);
    expect(screen.getByText(/Sign in as the platform administrator account/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: 'Sign in as the administrator' }));
    await waitFor(() => expect(signIn).toHaveBeenCalledWith('local', { callbackUrl: expect.stringContaining('/setup?administrator=1') }, { prompt: 'login', max_age: '300' }));
  });
  it('does not create the account twice when the step is revisited', async () => {
    await toCreateStep();
    await fillAdministrator();
    await userEvent.click(createButton());
    await screen.findByRole('heading', { name: 'First administrator' });
    await userEvent.click(screen.getByRole('button', { name: 'Back' }));
    expect(await screen.findByText('The administrator account was created. Continue to sign in as the administrator.')).toBeInTheDocument();
    expect(screen.queryByLabelText('Password', { exact: true })).not.toBeInTheDocument();
    await next();
    await screen.findByRole('heading', { name: 'First administrator' });
    expect(bodies().filter(body => body.action === 'create-administrator')).toHaveLength(1);
  });

  describe('validation happens before anything is sent', () => {
    // Required and email-typed inputs are stopped by the browser's own validation first.
    it.each<[string, Record<string, string>]>([['no name', { name: '' }], ['an invalid email', { email: 'admin' }]])('%s', async (_name, values) => {
      await toCreateStep();
      await fillAdministrator(values);
      await userEvent.click(createButton());
      expect(bodies().some(body => body.action === 'create-administrator')).toBe(false);
      expect(screen.getByRole('heading', { name: 'Create administrator account' })).toBeInTheDocument();
    });
    it.each<[string, Record<string, string>, RegExp]>([
      ['a short password', { password: 'short', again: 'short' }, /6–128 characters/],
      ['a mismatch', { again: 'A different passphrase 8!' }, /do not match/],
    ])('%s', async (_name, values, message) => {
      await toCreateStep();
      await fillAdministrator(values);
      await userEvent.click(createButton());
      expect(await screen.findByRole('alert')).toHaveTextContent(message);
      expect(bodies().some(body => body.action === 'create-administrator')).toBe(false);
      expect(screen.getByRole('heading', { name: 'Create administrator account' })).toBeInTheDocument();
    });
  });

  describe('failures keep the form and forget the passwords', () => {
    it.each([[403, 'Setup access is no longer valid. Unlock setup again.'], [409, 'An administrator account already exists or setup is closed. Reload to check its status.'],
      [422, 'This password cannot be used. Choose another.'], [429, 'Too many attempts. Retry in a minute.'], [503, 'The administrator account could not be created. Check Identity and try again.']])(
      'HTTP %i shows the setup message', async (code, message) => {
        create = () => Response.json({ error: message, detail: LEAK }, { status: code });
        await toCreateStep();
        await fillAdministrator();
        await userEvent.click(createButton());
        expect(await screen.findByRole('alert')).toHaveTextContent(message);
        expect(document.body).not.toHaveTextContent(LEAK);
        expect(screen.getByRole('heading', { name: 'Create administrator account' })).toBeInTheDocument();
        expect(screen.getByLabelText('Password', { exact: true })).toHaveValue('');
        expect(screen.getByLabelText('Confirm password')).toHaveValue('');
        expect(screen.getByLabelText('Administrator email address')).toHaveValue('Admin@example.test');
        expect(createButton()).toBeEnabled();
      });
    it('shows a pending state and creates once however often it is clicked', async () => {
      create = () => new Promise<Response>(() => undefined);
      await toCreateStep();
      await fillAdministrator();
      await userEvent.dblClick(createButton());
      const busy = screen.getByRole('button', { name: 'Working…' });
      expect(busy).toBeDisabled();
      expect(busy).toHaveAttribute('aria-busy', 'true');
      expect(bodies().filter(body => body.action === 'create-administrator')).toHaveLength(1);
    });
  });

  describe('when an administrator already exists', () => {
    it('goes straight from the workspace to signing in', async () => {
      administratorExists = true;
      await unlock();
      await next(); await screen.findByLabelText('Platform name');
      await next(); await screen.findByLabelText('Administration workspace name');
      await next();
      expect(await screen.findByRole('heading', { name: 'First administrator' })).toBeInTheDocument();
      expect(screen.getByRole('navigation', { name: 'Setup progress' })).not.toHaveTextContent('Create administrator account');
      expect(screen.getByRole('button', { name: 'Sign in as the administrator' })).toBeDisabled();
    });
    it('returns from sign-in to the administrator step and completes with neutral wording', async () => {
      status = { available: true, completed: false, unlocked: true, provider: 'local', administratorExists: true, draft: { ...draft, administrator_name: 'Platform Admin' } };
      window.history.replaceState({}, '', '/setup?administrator=1');
      renderScreen(<SetupPage />);
      expect(await screen.findByLabelText('Verified email')).toHaveValue('admin@example.com');
      expect(screen.getByRole('heading', { name: 'First administrator' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Sign in again' })).toBeInTheDocument();
      await next(); await screen.findByText(/You can complete setup without email/);
      await next(); await screen.findByText('Verified email');
      expect(screen.getByText(/The signed-in administrator account will become the first platform administrator/)).toBeInTheDocument();
      expect(document.body).not.toHaveTextContent('Authentik');
    });
    it('returns to the administrator step even if the account has not been created yet', async () => {
      status = { available: true, completed: false, unlocked: true, provider: 'local', administratorExists: false, draft };
      window.history.replaceState({}, '', '/setup?administrator=1');
      renderScreen(<SetupPage />);
      expect(await screen.findByLabelText('Verified email')).toBeInTheDocument();
      expect(screen.getByRole('heading', { name: 'First administrator' })).toBeInTheDocument();
      expect(screen.getByRole('navigation', { name: 'Setup progress' })).toHaveTextContent('Create administrator account');
    });
  });

  it('shows the setup message when the status cannot be read', async () => {
    fetcher.mockImplementation(async () => Response.json({ error: 'Local sign-in status is unavailable. Check Identity and the Auth application settings.' }, { status: 503 }));
    renderScreen(<SetupPage />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Local sign-in status is unavailable');
  });
});
