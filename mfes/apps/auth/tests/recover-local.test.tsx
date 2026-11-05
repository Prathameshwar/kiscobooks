import { screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { renderScreen } from './helpers';
import { PasswordRecovery } from '../app/recover/PasswordRecovery';

const { goTo } = vi.hoisted(() => ({ goTo: vi.fn() }));
vi.mock('../app/lib/navigate', () => ({ goTo }));

it('explains recovery by an administrator-issued one-time link, with no provider and no email claim', () => {
  renderScreen(<PasswordRecovery destination={null} signInHref="/login" local />);
  expect(screen.getByRole('heading', { name: 'Forgot password?' })).toBeInTheDocument();
  expect(screen.getByRole('status')).toHaveTextContent('Password recovery is by a one-time link from your administrator.');
  expect(screen.getByText(/ask for a password recovery link/)).toBeInTheDocument();
  expect(screen.getByText(/verify your identity before sharing/)).toBeInTheDocument();
  expect(screen.getByText(/10 minutes and can be used once/)).toBeInTheDocument();
  expect(screen.getByText(/No email has been sent from this page/)).toBeInTheDocument();
  expect(document.body).not.toHaveTextContent('Authentik');
  expect(document.body).not.toHaveTextContent('authentication factors');
});
it('collects nothing and offers no provider hand-off', () => {
  renderScreen(<PasswordRecovery destination="https://authentik.test/if/flow/bill-self-service-recovery/" signInHref="/login" local />);
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Continue to reset password' })).not.toBeInTheDocument();
  expect(screen.queryByRole('link', { name: /authentik/i })).not.toBeInTheDocument();
  expect(goTo).not.toHaveBeenCalled();
});
it('keeps the reviewed destination on both ways back to sign in', () => {
  const signInHref = '/login?returnTo=' + encodeURIComponent('https://books.test/vouchers?draft=1');
  renderScreen(<PasswordRecovery destination={null} signInHref={signInHref} local />);
  const back = screen.getAllByRole('link', { name: 'Back to sign in' });
  expect(back).toHaveLength(2);
  for (const link of back) expect(link).toHaveAttribute('href', signInHref);
  expect(screen.getByRole('link', { name: 'Sign in' })).toHaveAttribute('href', signInHref);
});
it('keeps the existing Authentik copy when `local` is not set', () => {
  renderScreen(<PasswordRecovery destination="https://authentik.test/if/flow/bill-self-service-recovery/" signInHref="/login" />);
  expect(screen.getByText(/Authentik will help you reset/)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Continue to reset password' })).toBeInTheDocument();
});
