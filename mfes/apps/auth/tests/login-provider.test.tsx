import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderScreen } from './helpers';
import LoginPage from '../app/login/page';
import { authProviderId, useAuthProvider } from '../app/lib/provider-client';

const { signIn } = vi.hoisted(() => ({ signIn: vi.fn() }));
vi.mock('next-auth/react', () => ({ signIn }));

// Deliberately NOT mocking provider-client: this suite covers the real lookup.
let provider: () => Response | Promise<Response>;
let fetcher: ReturnType<typeof vi.fn>;
beforeEach(() => {
  signIn.mockReset().mockResolvedValue(undefined);
  provider = () => Response.json({ provider: 'local' });
  fetcher = vi.fn(async (input: string) => input.startsWith('/api/provider') ? provider() : Response.json({ available: false }));
  vi.stubGlobal('fetch', fetcher);
  window.history.replaceState({}, '', '/login');
});
afterEach(() => vi.unstubAllGlobals());
const calls = (path: string) => fetcher.mock.calls.filter(([input]) => String(input).startsWith(path));

describe('the login page asks the server which provider to use', () => {
  it.each(['local', 'authentik'])('starts sign-in with the %s provider id', async id => {
    provider = () => Response.json({ provider: id });
    renderScreen(<LoginPage />);
    await waitFor(() => expect(calls('/api/provider')).toHaveLength(1));
    await userEvent.click(screen.getByRole('button', { name: 'Continue to sign in' }));
    expect(signIn).toHaveBeenCalledWith(id, { callbackUrl: expect.stringContaining('/onboarding?returnTo=') }, { prompt: 'login', max_age: '1' });
    expect(fetcher.mock.calls[0][1]).toMatchObject({ cache: 'no-store' });
  });
  it('still starts when the click comes before the lookup has finished', async () => {
    let answer!: (response: Response) => void;
    provider = () => new Promise<Response>(resolve => { answer = resolve; });
    renderScreen(<LoginPage />);
    const click = userEvent.click(screen.getByRole('button', { name: 'Continue to sign in' }));
    await waitFor(() => expect(calls('/api/provider').length).toBeGreaterThan(0));
    answer(Response.json({ provider: 'local' }));
    await click;
    await waitFor(() => expect(signIn).toHaveBeenCalledWith('local', expect.any(Object), expect.any(Object)));
  });
  it('preserves the setup return and the longer step-up bound for the local provider too', async () => {
    window.history.replaceState({}, '', '/login?callbackUrl=' + encodeURIComponent(window.location.origin + '/setup?administrator=1'));
    renderScreen(<LoginPage />);
    await waitFor(() => expect(calls('/api/provider')).toHaveLength(1));
    await userEvent.click(screen.getByRole('button', { name: 'Continue to sign in' }));
    expect(signIn).toHaveBeenCalledWith('local', { callbackUrl: window.location.origin + '/setup?administrator=1' }, { prompt: 'login', max_age: '300' });
  });
  it.each([['a server error', () => Response.json({}, { status: 503 })], ['an unknown provider', () => Response.json({ provider: 'saml' })],
    ['a network failure', () => Promise.reject(new Error('offline'))]])('never guesses a provider after %s', async (_name, answer) => {
    provider = answer as typeof provider;
    renderScreen(<LoginPage />);
    await waitFor(() => expect(calls('/api/provider').length).toBeGreaterThan(0));
    await userEvent.click(screen.getByRole('button', { name: 'Continue to sign in' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Unable to start sign in');
    expect(signIn).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Continue to sign in' })).toBeEnabled();
  });
});

describe('provider-neutral copy', () => {
  it('speaks neutrally about password recovery with the local provider', async () => {
    window.history.replaceState({}, '', '/login?recovery=complete');
    renderScreen(<LoginPage />);
    expect(await screen.findByRole('status')).toHaveTextContent('After resetting your password, continue to sign in with your new password.');
    expect(document.body).not.toHaveTextContent('Authentik');
  });
  it('keeps the Authentik wording with the Authentik provider', async () => {
    provider = () => Response.json({ provider: 'authentik' });
    window.history.replaceState({}, '', '/login?recovery=complete');
    renderScreen(<LoginPage />);
    expect(await screen.findByRole('status')).toHaveTextContent('After completing recovery in Authentik, continue to sign in with your new password.');
  });
  it('shows no recovery notice until the provider is known, and none without the query flag', async () => {
    provider = () => new Promise<Response>(() => undefined);
    window.history.replaceState({}, '', '/login?recovery=complete');
    renderScreen(<LoginPage />);
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });
  it('hints, without claiming success, that a password change needs a fresh sign-in (local only)', async () => {
    window.history.replaceState({}, '', '/login?passwordChanged=1');
    renderScreen(<LoginPage />);
    expect(await screen.findByRole('status')).toHaveTextContent('If you just changed your password, sign in again with your new password.');
  });
  it('ignores the password-changed flag under Authentik and when an error is being shown', async () => {
    provider = () => Response.json({ provider: 'authentik' });
    window.history.replaceState({}, '', '/login?passwordChanged=1');
    renderScreen(<LoginPage />);
    await waitFor(() => expect(calls('/api/provider')).toHaveLength(1));
    await new Promise(resolve => setTimeout(resolve, 20));
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });
  it('lets an error win over the password-changed hint', async () => {
    window.history.replaceState({}, '', '/login?passwordChanged=1&error=SessionExpired');
    renderScreen(<LoginPage />);
    await waitFor(() => expect(calls('/api/provider')).toHaveLength(1));
    await new Promise(resolve => setTimeout(resolve, 20));
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('Your session has ended');
  });
});

describe('provider lookup helpers', () => {
  it('authProviderId returns only a known provider and rejects everything else', async () => {
    await expect(authProviderId()).resolves.toBe('local');
    provider = () => Response.json({ provider: 'authentik' });
    await expect(authProviderId()).resolves.toBe('authentik');
    for (const bad of [Response.json({ provider: 'LOCAL' }), Response.json({}), Response.json({}, { status: 500 }), Response.json({ provider: { id: 'local' } })]) {
      provider = () => bad;
      await expect(authProviderId()).rejects.toThrow('Authentication provider unavailable');
    }
  });
  it('does not cache a failure: the next lookup asks again', async () => {
    provider = () => Response.json({}, { status: 503 });
    await expect(authProviderId()).rejects.toThrow();
    provider = () => Response.json({ provider: 'local' });
    await expect(authProviderId()).resolves.toBe('local');
  });
  it('useAuthProvider is null until the server answers, then the provider', async () => {
    function Probe() { return <p data-testid="probe">{String(useAuthProvider())}</p>; }
    render(<Probe />);
    expect(screen.getByTestId('probe')).toHaveTextContent('null');
    await waitFor(() => expect(screen.getByTestId('probe')).toHaveTextContent('local'));
  });
  it('useAuthProvider stays null when the server cannot say, and ignores an answer after unmount', async () => {
    provider = () => Response.json({}, { status: 500 });
    function Probe() { return <p data-testid="probe">{String(useAuthProvider())}</p>; }
    const view = render(<Probe />);
    await waitFor(() => expect(calls('/api/provider')).toHaveLength(1));
    expect(screen.getByTestId('probe')).toHaveTextContent('null');
    view.unmount();
  });
});
