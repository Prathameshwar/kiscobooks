import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderScreen } from './helpers';
import AcceptPage from '../app/accept/page';
import OnboardingPage from '../app/onboarding/page';
import StepUpPage from '../app/step-up/page';

// Every screen that starts a sign-in must use the id the server reports, not a hardcoded one.
const { signIn, provider } = vi.hoisted(() => ({ signIn: vi.fn(), provider: vi.fn() }));
vi.mock('next-auth/react', () => ({ signIn, signOut: vi.fn() }));
vi.mock('../app/lib/provider-client', () => ({ authProviderId: provider, useAuthProvider: () => 'local' }));
vi.mock('../app/lib/navigate', () => ({ goTo: vi.fn(), consoleUrl: () => 'https://console.test/' }));

beforeEach(() => {
  signIn.mockReset().mockResolvedValue(undefined);
  provider.mockReset().mockResolvedValue('local');
  window.history.replaceState({}, '', '/');
});

describe.each(['local', 'authentik'])('with the %s provider', id => {
  beforeEach(() => { provider.mockResolvedValue(id); });
  it('invitation acceptance signs in with the reported id', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ status: 401, ok: false }));
    window.history.replaceState({}, '', '/accept?tenant=tenant&invitation=reference');
    renderScreen(<AcceptPage />);
    await userEvent.click(screen.getByRole('button', { name: 'Accept invitation' }));
    await waitFor(() => expect(signIn).toHaveBeenCalledWith(id, { callbackUrl: expect.stringContaining('invitation=reference') }, { prompt: 'login', max_age: '1' }));
  });
  it('workspace onboarding signs in with the reported id', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ error: 'Sign in' }, { status: 401 })));
    renderScreen(<OnboardingPage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Sign in to continue' }));
    await waitFor(() => expect(signIn).toHaveBeenCalledWith(id, { callbackUrl: window.location.href }, { prompt: 'login', max_age: '1' }));
  });
  it('company step-up signs in with the reported id', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ status: 200, ok: true, json: async () => ({ challenge: 'abc' }) }));
    window.history.replaceState({}, '', '/step-up?company=company');
    renderScreen(<StepUpPage />);
    await userEvent.click(screen.getByRole('button', { name: 'Continue verification' }));
    await waitFor(() => expect(signIn).toHaveBeenCalledWith(id, { callbackUrl: expect.stringContaining('challenge=abc') }, { prompt: 'login', max_age: '1' }));
  });
  it('step-up asks to sign in again, with the reported id, when the session has gone', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ status: 401, ok: false }));
    renderScreen(<StepUpPage />);
    await userEvent.click(screen.getByRole('button', { name: 'Continue verification' }));
    await waitFor(() => expect(signIn).toHaveBeenCalledWith(id, { callbackUrl: window.location.href }));
  });
});

describe('when the provider cannot be determined', () => {
  beforeEach(() => { provider.mockRejectedValue(new Error('Authentication provider unavailable')); });
  it('invitation acceptance reports a failure and does not guess an id', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ status: 401, ok: false }));
    window.history.replaceState({}, '', '/accept?tenant=tenant&invitation=reference');
    renderScreen(<AcceptPage />);
    await userEvent.click(screen.getByRole('button', { name: 'Accept invitation' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Unable to reach the service');
    expect(signIn).not.toHaveBeenCalled();
  });
  it('onboarding reports a failure and can be retried', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ error: 'Sign in' }, { status: 401 })));
    renderScreen(<OnboardingPage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Sign in to continue' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Unable to start sign in');
    expect(screen.getByRole('button', { name: 'Sign in to continue' })).toBeEnabled();
    expect(signIn).not.toHaveBeenCalled();
  });
  it('step-up reports a failure and does not guess an id', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ status: 200, ok: true, json: async () => ({ challenge: 'abc' }) }));
    renderScreen(<StepUpPage />);
    await userEvent.click(screen.getByRole('button', { name: 'Continue verification' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Unable to verify your identity');
    expect(signIn).not.toHaveBeenCalled();
  });
});
