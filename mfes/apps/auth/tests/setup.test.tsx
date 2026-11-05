import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderScreen } from './helpers';
import SetupPage from '../app/setup/page';
const { signIn } = vi.hoisted(() => ({ signIn: vi.fn() }));
vi.mock('next-auth/react', () => ({ signIn }));
vi.mock('../app/lib/provider-client', () => ({ authProviderId: async () => 'authentik', useAuthProvider: () => 'authentik' })); // these suites exercise the Authentik provider
const draft = { platform_name: 'KiscoBooks', public_url: 'http://localhost:4320',
  workspace_name: 'Platform Administration', workspace_slug: 'platform-admin', administrator_name: 'Admin',
  country_code: 'IN', currency_code: 'INR', timezone: 'Asia/Kolkata' };
const connections = { ready: true, checks: [{ name: 'Identity', status: 'ready', message: 'Connected' }],
  countries: [{ code: 'IN', name: 'India' }], currencies: [{ code: 'INR', name: 'Indian rupee' }], timezones: [{ code: 'Asia/Kolkata', name: 'Asia/Kolkata' }], languages: [{ code: 'en', name: 'English' }] };
let status: object, checkResult: object;
let fetcher: ReturnType<typeof vi.fn>;
beforeEach(() => {
  window.history.replaceState({}, '', '/setup');
  status = { available: true, completed: false, unlocked: false };
  checkResult = connections;
  signIn.mockReset();
  fetcher = vi.fn(async (input: string, options?: RequestInit) => {
    const action = options?.body ? JSON.parse(String(options.body)).action : new URL(input, 'http://test').searchParams.get('action');
    if (action === 'status') return Response.json(status);
    if (action === 'checks') return Response.json(checkResult);
    if (action === 'administrator') return Response.json({ email: 'admin@example.com' });
    if (action === 'complete') return Response.json({ completed: true, verified: true, destination: 'http://localhost:4320/platform' });
    return Response.json({ unlocked: true, saved: true });
  });
  vi.stubGlobal('fetch', fetcher);
});
afterEach(() => vi.unstubAllGlobals());

describe('first-run wizard', () => {
  it('binds timezone and language to the setup reference API', async () => {
    status = { available: true, completed: false, unlocked: true };
    renderScreen(<SetupPage />); await screen.findByText('Connected');
    await userEvent.click(screen.getByRole('button', { name: 'Next' }));
    expect(await screen.findByRole('combobox', { name: 'Time zone' })).toHaveValue('Asia/Kolkata');
    expect(screen.getByRole('combobox', { name: 'Language' })).toHaveValue('en');
  });
  it('unlocks, tests connections, collects details and preserves progress before fresh authentication', async () => {
    renderScreen(<SetupPage />);
    await userEvent.type(await screen.findByLabelText('One-time setup key'), 'local-installation-key');
    await userEvent.click(screen.getByRole('button', { name: 'Unlock setup' }));
    await screen.findByText('Connected');
    await userEvent.click(screen.getByRole('button', { name: 'Next' }));
    expect(await screen.findByLabelText('Platform name')).toHaveValue('KiscoBooks');
    await userEvent.click(screen.getByRole('button', { name: 'Next' }));
    expect(await screen.findByLabelText('Administration workspace name')).toHaveValue('Platform Administration');
    await userEvent.click(screen.getByRole('button', { name: 'Next' }));
    await userEvent.type(await screen.findByLabelText('Administrator full name'), 'Admin');
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: 'Sign in through Authentik' }));
    await waitFor(() => expect(signIn).toHaveBeenCalledWith('authentik', { callbackUrl: expect.stringContaining('/setup?administrator=1') },
      { prompt: 'login', max_age: '300' }));
    expect(localStorage.getItem('setup')).toBeNull();
    expect(fetcher.mock.calls.some(([, options]) => options?.body && JSON.parse(String(options.body)).action === 'save')).toBe(true);
  });
  it('restores the authenticated draft, skips email, confirms and completes with verified access', async () => {
    status = { available: true, completed: false, unlocked: true, draft };
    window.history.replaceState({}, '', '/setup?administrator=1');
    renderScreen(<SetupPage />);
    expect(await screen.findByLabelText('Verified email')).toHaveValue('admin@example.com');
    await userEvent.click(screen.getByRole('button', { name: 'Next' }));
    await screen.findByText(/You can complete setup without email/);
    await userEvent.click(screen.getByRole('button', { name: 'Next' }));
    await screen.findByText('Verified email');
    expect(screen.getByRole('button', { name: 'Complete setup' })).toBeDisabled();
    await userEvent.click(screen.getByRole('checkbox'));
    await userEvent.click(screen.getByRole('button', { name: 'Complete setup' }));
    expect(await screen.findByRole('heading', { name: 'Platform setup completed' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open platform administration' })).toHaveAttribute('href', 'http://localhost:4320/platform');
  });
  it('blocks progress on failed checks and allows retesting', async () => {
    status = { available: true, unlocked: true };
    checkResult = { ...connections, ready: false, checks: [{ name: 'Redis', status: 'failed', message: 'Start Redis' }] };
    renderScreen(<SetupPage />);
    await screen.findByText('Start Redis');
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled();
    checkResult = connections;
    await userEvent.click(screen.getByRole('button', { name: 'Test connections again' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Next' })).toBeEnabled());
  });
  it.each([401, 403, 422, 500])('shows a retryable error for failed requests (%s)', async code => {
    renderScreen(<SetupPage />);
    await userEvent.type(await screen.findByLabelText('One-time setup key'), 'installation-key');
    fetcher.mockImplementationOnce(async () => Response.json({ error: 'Please retry setup.' }, { status: code }));
    await userEvent.click(screen.getByRole('button', { name: 'Unlock setup' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Please retry setup.');
    expect(screen.getByRole('button', { name: 'Unlock setup' })).toBeEnabled();
  });
  it('does not show provisioning controls when setup is closed', async () => {
    status = { available: false, completed: true };
    renderScreen(<SetupPage />);
    await screen.findByRole('heading', { name: 'Setup is closed' });
    expect(screen.queryByLabelText('One-time setup key')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Continue to sign in' })).toHaveAttribute('href', '/login');
  });
  it('shows loading and pending states and moves keyboard focus to the current heading', async () => {
    renderScreen(<SetupPage />);
    const key = await screen.findByLabelText('One-time setup key');
    await userEvent.type(key, 'local-key');
    fetcher.mockImplementationOnce(() => new Promise(() => {}));
    await userEvent.click(screen.getByRole('button', { name: 'Unlock setup' }));
    expect(screen.getByRole('button', { name: 'Working…' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Working…' })).toHaveAttribute('aria-busy', 'true');
  });
  it('requires confirmation again after a reviewed setting changes', async () => {
    status = { available: true, completed: false, unlocked: true, draft };
    window.history.replaceState({}, '', '/setup?administrator=1');
    renderScreen(<SetupPage />);
    await screen.findByLabelText('Verified email');
    await userEvent.click(screen.getByRole('button', { name: 'Next' }));
    await userEvent.click(screen.getByRole('button', { name: 'Next' }));
    await userEvent.click(screen.getByRole('checkbox'));
    await userEvent.click(screen.getByRole('button', { name: /Platform details.*completed/ }));
    await userEvent.type(screen.getByLabelText('Platform name'), ' updated');
    for (let index = 0; index < 4; index++) await userEvent.click(screen.getByRole('button', { name: 'Next' }));
    expect(screen.getByRole('checkbox')).not.toBeChecked();
    expect(screen.getByRole('button', { name: 'Complete setup' })).toBeDisabled();
  });
  it('shows saved setup when access verification is temporarily unavailable', async () => {
    status = { available: true, completed: false, unlocked: true, draft };
    window.history.replaceState({}, '', '/setup?administrator=1');
    renderScreen(<SetupPage />);
    await screen.findByLabelText('Verified email');
    await userEvent.click(screen.getByRole('button', { name: 'Next' }));
    await userEvent.click(screen.getByRole('button', { name: 'Next' }));
    await userEvent.click(screen.getByRole('checkbox'));
    fetcher.mockImplementationOnce(async () => Response.json({ completed: true, verified: false, destination: 'http://localhost:4320/platform' }));
    await userEvent.click(screen.getByRole('button', { name: 'Complete setup' }));
    expect(await screen.findByRole('heading', { name: 'Platform setup completed' })).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('Setup was saved');
  });
});
