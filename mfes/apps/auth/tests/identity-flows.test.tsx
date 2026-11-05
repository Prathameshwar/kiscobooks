import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderScreen } from './helpers';
import AcceptPage from '../app/accept/page';
import StepUpPage from '../app/step-up/page';
const { signIn, signOut, goTo } = vi.hoisted(() => ({ signIn: vi.fn(), signOut: vi.fn(), goTo: vi.fn() }));
vi.mock('next-auth/react', () => ({ signIn, signOut }));
vi.mock('../app/lib/navigate', () => ({ goTo, consoleUrl: () => 'https://console.test/' }));
vi.mock('../app/lib/provider-client', () => ({ authProviderId: async () => 'authentik', useAuthProvider: () => 'authentik' })); // these suites exercise the Authentik provider
beforeEach(() => { vi.clearAllMocks(); window.history.replaceState({}, '', '/'); });
describe('invitation acceptance', () => {
  it('explains both recipient paths and links a new user to signup with the invitation preserved', () => {
    vi.stubGlobal('fetch', vi.fn());
    window.history.replaceState({}, '', '/accept?tenant=tenant&invitation=reference');
    renderScreen(<AcceptPage />);
    expect(screen.getByText(/already have an account/i)).toBeInTheDocument();
    expect(screen.getByText(/approval and email verification/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Create an account' })).toHaveAttribute('href',
      '/signup?returnTo=' + encodeURIComponent('/accept?tenant=tenant&invitation=reference'));
    expect(screen.getByRole('link', { name: 'Go to Home' })).toHaveAttribute('href', 'https://console.test/');
    expect(screen.getByRole('navigation', { name: 'Invitation links' })).toContainElement(screen.getByRole('link', { name: 'Go to Home' }));
    expect(fetch).not.toHaveBeenCalled();
  });
  it('finishes the clicked invitation after Authentik returns to the same tab', async () => {
    const fetcher = vi.fn().mockResolvedValueOnce({ status: 401, ok: false }).mockResolvedValueOnce({ status: 200, ok: true });
    vi.stubGlobal('fetch', fetcher);
    window.history.replaceState({}, '', '/accept?tenant=tenant&invitation=reference');
    const first = renderScreen(<AcceptPage />);
    expect(fetcher).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: 'Accept invitation' }));
    expect(signIn).toHaveBeenCalledWith('authentik', { callbackUrl: expect.stringContaining('invitation=reference') }, { prompt: 'login', max_age: '1' });
    const callback = new URL(signIn.mock.calls[0][1].callbackUrl);
    expect(callback.searchParams.get('resume')).toBeTruthy();
    first.unmount();
    window.history.replaceState({}, '', callback.pathname + callback.search);
    renderScreen(<AcceptPage />);
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
    expect(goTo).toHaveBeenCalledWith('https://console.test/');
  });
  it('does not accept from a pasted return URL without the matching same-tab marker', () => {
    vi.stubGlobal('fetch', vi.fn());
    window.history.replaceState({}, '', '/accept?tenant=tenant&invitation=reference&resume=untrusted');
    renderScreen(<AcceptPage />);
    expect(fetch).not.toHaveBeenCalled();
  });
  it('stops after one failed automatic acceptance instead of looping through sign-in', async () => {
    const fetcher = vi.fn().mockResolvedValue({ status: 401, ok: false });
    vi.stubGlobal('fetch', fetcher);
    window.history.replaceState({}, '', '/accept?tenant=tenant&invitation=reference');
    const first = renderScreen(<AcceptPage />);
    await userEvent.click(screen.getByRole('button', { name: 'Accept invitation' }));
    const callback = new URL(signIn.mock.calls[0][1].callbackUrl);
    first.unmount();
    window.history.replaceState({}, '', callback.pathname + callback.search);
    renderScreen(<AcceptPage />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Sign in did not complete');
    expect(signIn).toHaveBeenCalledTimes(1);
    expect(fetcher).toHaveBeenCalledTimes(2);
  });
  it.each([401, 403, 500, 200])('handles HTTP %s without exposing credentials', async (status) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ status, ok: status === 200 }));
    window.history.replaceState({}, '', '/accept?tenant=tenant&invitation=reference');
    renderScreen(<AcceptPage />);
    await userEvent.click(screen.getByRole('button', { name: 'Accept invitation' }));
    if (status === 401) expect(signIn).toHaveBeenCalledWith('authentik', expect.any(Object), { prompt: 'login', max_age: '1' });
    else if (status === 200) expect(goTo).toHaveBeenCalledWith('https://console.test/');
    else if (status === 403) expect(await screen.findByRole('alert')).toHaveTextContent('signed-in account cannot accept');
    else expect(await screen.findByRole('alert')).toHaveTextContent('unavailable');
  });
  it('offers to switch accounts after a verified-email denial and keeps the invitation URL', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ status: 403, ok: false }));
    window.history.replaceState({}, '', '/accept?tenant=tenant&invitation=reference');
    renderScreen(<AcceptPage />);
    await userEvent.click(screen.getByRole('button', { name: 'Accept invitation' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('invited email');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in with invited account' }));
    expect(signOut).toHaveBeenCalledWith({ callbackUrl: window.location.href });
  });
  it('lets the invited-account action recover from a failed sign-out', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ status: 403, ok: false }));
    signOut.mockRejectedValueOnce(new Error('offline'));
    renderScreen(<AcceptPage />);
    await userEvent.click(screen.getByRole('button', { name: 'Accept invitation' }));
    await userEvent.click(screen.getByRole('button', { name: 'Sign in with invited account' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Unable to sign out');
    expect(screen.getByRole('button', { name: 'Accept invitation' })).toBeEnabled();
  });
  it('handles a failed connection', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')));
    renderScreen(<AcceptPage />);
    await userEvent.click(screen.getByRole('button', { name: 'Accept invitation' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Unable to reach');
  });
  it('blocks repeated clicks while acceptance is pending', async () => {
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(new Promise(() => {})));
    renderScreen(<AcceptPage />);
    await userEvent.click(screen.getByRole('button', { name: 'Accept invitation' }));
    expect(screen.getByRole('button', { name: /Connecting/ })).toBeDisabled();
  });
});
describe('company verification', () => {
  it('requests a fresh provider login and preserves the challenge', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ status: 200, ok: true, json: async () => ({ challenge: 'abc' }) }));
    window.history.replaceState({}, '', '/step-up?company=company');
    renderScreen(<StepUpPage />);
    await userEvent.click(screen.getByRole('button', { name: 'Continue verification' }));
    expect(signIn).toHaveBeenCalledWith('authentik', { callbackUrl: expect.stringContaining('challenge=abc') }, { prompt: 'login', max_age: '1' });
  });
  it('completes the challenge before opening the console', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ status: 200, ok: true }));
    window.history.replaceState({}, '', '/step-up?company=company&challenge=abc&complete=1');
    renderScreen(<StepUpPage />);
    await userEvent.click(screen.getByRole('button', { name: 'Continue verification' }));
    expect(goTo).toHaveBeenCalledWith('https://console.test/');
  });
  it.each([['/vouchers?draft=1', 'https://console.test/vouchers?draft=1'],
    ['https://evil.test', 'https://console.test/']])('preserves only Console return destinations after verification: %s', async (returnTo, expected) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ status: 200, ok: true }));
    window.history.replaceState({}, '', '/step-up?company=company&challenge=abc&complete=1&returnTo=' + encodeURIComponent(returnTo));
    renderScreen(<StepUpPage />);
    await userEvent.click(screen.getByRole('button', { name: 'Continue verification' }));
    expect(goTo).toHaveBeenCalledWith(expected);
  });
  it.each([401, 403, 422, 500])('handles verification HTTP %s', async (status) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ status, ok: false }));
    renderScreen(<StepUpPage />);
    await userEvent.click(screen.getByRole('button', { name: 'Continue verification' }));
    if (status === 401) expect(signIn).toHaveBeenCalled();
    else expect(await screen.findByRole('alert')).toHaveTextContent('unavailable or expired');
  });
  it('allows retry after a connection failure', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')));
    renderScreen(<StepUpPage />);
    await userEvent.click(screen.getByRole('button', { name: 'Continue verification' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Unable to verify');
  });
  it('blocks repeated clicks during verification', async () => {
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(new Promise(() => {})));
    renderScreen(<StepUpPage />);
    await userEvent.click(screen.getByRole('button', { name: 'Continue verification' }));
    expect(screen.getByRole('button', { name: 'Verifying...' })).toBeDisabled();
  });
});
