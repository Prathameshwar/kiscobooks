import { screen, within } from '@testing-library/react';
import { renderScreen } from './helpers';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import LoginPage from '../app/login/page';
const { signIn } = vi.hoisted(() => ({ signIn: vi.fn() }));
vi.mock('next-auth/react', () => ({ signIn }));
vi.mock('../app/lib/provider-client', () => ({ authProviderId: async () => 'authentik', useAuthProvider: () => 'authentik' })); // these suites exercise the Authentik provider

describe('provider login', () => {
  it('groups account creation and password recovery in the same footer', () => {
    renderScreen(<LoginPage />);
    const footer = screen.getByRole('link', { name: 'Create account' }).closest('p')!;
    expect(within(footer).getByRole('link', { name: 'Forgot password?' })).toHaveAttribute('href', expect.stringContaining('/recover'));
    expect(footer).toHaveTextContent('New to KiscoBooks?');
  });
  it('puts the ways off the sign-in path in the card footer band, below the one action', () => {
    const { container } = renderScreen(<LoginPage />);
    const band = container.querySelector('.auth__foot--band') as HTMLElement;
    expect(band).toBeInTheDocument();
    expect(within(band).getByRole('link', { name: 'Create account' })).toBeInTheDocument();
    expect(within(band).getByRole('link', { name: 'Forgot password?' })).toBeInTheDocument();
    expect(within(band).queryByRole('button')).toBeNull();
    // The band is the card's last child: nothing hangs below it, outside the card.
    expect(band).toBe(band.parentElement!.lastElementChild);
  });
  it('keeps the platform-setup link in the same band when setup is open', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => Response.json({ available: true })));
    try {
      const { container } = renderScreen(<LoginPage />);
      const link = await screen.findByRole('link', { name: 'Set up this platform' });
      const band = container.querySelector('.auth__foot--band');
      expect(link.closest('.auth__foot--band')).toBe(band);
      expect(band).toBe(band!.parentElement!.lastElementChild);
    } finally { vi.unstubAllGlobals(); }
  });
  it('offers a dedicated forgot-password journey', () => {
    renderScreen(<LoginPage />);
    expect(screen.getByRole('link', { name: 'Forgot password?' })).toHaveAttribute('href', expect.stringContaining('/recover'));
    expect(screen.queryByText('Account verification and password recovery are available when you continue.')).not.toBeInTheDocument();
  });
  it('links directly to the branded account form', () => {
    renderScreen(<LoginPage />);
    expect(screen.getByRole('link', { name: 'Create account' })).toHaveAttribute('href', '/signup');
  });
  beforeEach(() => { signIn.mockReset(); window.history.replaceState({}, '', '/login'); });
  it('uses the provider and exposes a pending state without collecting credentials', async () => {
    signIn.mockResolvedValue(undefined);
    renderScreen(<LoginPage />);
    expect(screen.queryByLabelText(/password/i)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Continue to sign in' }));
    expect(signIn).toHaveBeenCalledWith('authentik', { callbackUrl: expect.any(String) }, { prompt: 'login', max_age: '1' });
    expect(screen.getByRole('button', { name: /Connecting/ })).toBeDisabled();
  });
  it('labels the pending state with a real ellipsis and marks the button busy', async () => {
    signIn.mockReturnValue(new Promise(() => {}));
    renderScreen(<LoginPage />);
    await userEvent.click(screen.getByRole('button', { name: 'Continue to sign in' }));
    const pending = screen.getByRole('button', { name: 'Connecting…' });
    expect(pending).toHaveAttribute('aria-busy', 'true');
    expect(pending).toHaveClass('janso-btn--block');
  });
  it('reports a failure to start as a danger notice, not bare text', async () => {
    signIn.mockRejectedValue(new Error('unavailable'));
    renderScreen(<LoginPage />);
    await userEvent.click(screen.getByRole('button', { name: 'Continue to sign in' }));
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveClass('janso-notice');
    expect(alert).toHaveAttribute('data-tone', 'danger');
  });
  it('allows retry when sign in cannot start', async () => {
    signIn.mockRejectedValue(new Error('unavailable'));
    renderScreen(<LoginPage />);
    await userEvent.click(screen.getByRole('button', { name: 'Continue to sign in' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Unable to start sign in');
    expect(screen.getByRole('button', { name: 'Continue to sign in' })).toBeEnabled();
  });
});

it('preserves the setup callback when retrying provider authentication', async () => {
  window.history.replaceState({}, '', '/login?callbackUrl=' + encodeURIComponent(window.location.origin + '/setup?administrator=1'));
  renderScreen(<LoginPage />);
  await userEvent.click(screen.getByRole('button', { name: 'Continue to sign in' }));
  expect(signIn).toHaveBeenCalledWith('authentik', { callbackUrl: window.location.origin + '/setup?administrator=1' },
    { prompt: 'login', max_age: '300' });
});

it.each(['OAuthCallback', 'AccessDenied', 'Configuration', 'SessionExpired', 'SessionUnavailable', '<private-error>'])
  ('shows sanitized callback errors and allows retry: %s', (code) => {
    window.history.replaceState({}, '', '/login?error=' + encodeURIComponent(code));
    renderScreen(<LoginPage />);
    expect(screen.getByRole('alert')).toHaveTextContent(/sign in|session/i);
    expect(screen.getByRole('alert')).not.toHaveTextContent('<private-error>');
    expect(screen.getByRole('button', { name: 'Continue to sign in' })).toBeEnabled();
  });
it('explains an unavailable sign-in service and lets the user retry', async () => {
  window.history.replaceState({}, '', '/login?error=OAuthSignin');
  signIn.mockResolvedValue(undefined);
  renderScreen(<LoginPage />);
  expect(screen.getByRole('alert')).toHaveTextContent(
    'The sign-in service is currently unavailable. Please try again shortly. If the problem continues, contact your administrator.'
  );
  const retry = screen.getByRole('button', { name: 'Continue to sign in' });
  expect(retry).toBeEnabled();
  await userEvent.click(retry);
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  expect(signIn).toHaveBeenCalledWith('authentik', { callbackUrl: expect.any(String) },
    { prompt: 'login', max_age: '1' });
});
it('explains a sign-in configuration failure with an actionable next step', () => {
  window.history.replaceState({}, '', '/login?error=Configuration');
  renderScreen(<LoginPage />);
  expect(screen.getByRole('alert')).toHaveTextContent(
    'Sign in is unavailable because the sign-in service is not configured correctly. Please contact your administrator.'
  );
});
it('offers recovery sign-in guidance without claiming success from a query parameter', () => {
  window.history.replaceState({}, '', '/login?recovery=complete');
  signIn.mockReset();
  renderScreen(<LoginPage />);
  expect(screen.getByRole('status')).toHaveTextContent('After completing recovery in Authentik');
  expect(screen.queryByText('Password recovery is complete.')).not.toBeInTheDocument();
  expect(signIn).not.toHaveBeenCalled();
});
it('prioritizes sign-in errors over recovery confirmation', () => {
  window.history.replaceState({}, '', '/login?recovery=complete&error=OAuthSignin');
  renderScreen(<LoginPage />);
  expect(screen.getAllByRole('alert')).toHaveLength(1);
  expect(screen.getByRole('alert')).toHaveTextContent('sign-in service is currently unavailable');
});
it('keeps the approved destination on the forgot-password link', () => {
  const returnTo = 'http://localhost:4320/reports?year=2026';
  window.history.replaceState({}, '', '/login?returnTo=' + encodeURIComponent(returnTo));
  renderScreen(<LoginPage />);
  expect(screen.getByRole('link', { name: 'Forgot password?' })).toHaveAttribute('href', '/recover?returnTo=' + encodeURIComponent(returnTo));
});
it.each([['http://localhost:4320/vouchers?draft=1', 'http://localhost:4320/vouchers?draft=1'],
  ['https://evil.test/path', 'http://localhost:4320'], ['http://user:pass@localhost:4320/path', 'http://localhost:4320']])
  ('restricts login return destinations: %s', async (returnTo, expected) => {
    window.history.replaceState({}, '', '/login?returnTo=' + encodeURIComponent(returnTo));
    renderScreen(<LoginPage />);
    await userEvent.click(screen.getByRole('button', { name: 'Continue to sign in' }));
    expect(signIn).toHaveBeenCalledWith('authentik', { callbackUrl: window.location.origin + '/onboarding?returnTo=' + encodeURIComponent(expected) }, { prompt: 'login', max_age: '1' });
  });
it.each(['error=SessionExpired', 'reauth=1'])('requires fresh provider authentication after revocation or logout: %s', async (query) => {
  window.history.replaceState({}, '', '/login?' + query);
  renderScreen(<LoginPage />);
  await userEvent.click(screen.getByRole('button', { name: 'Continue to sign in' }));
  expect(signIn).toHaveBeenCalledWith('authentik', { callbackUrl: expect.any(String) }, { prompt: 'login', max_age: '1' });
});
