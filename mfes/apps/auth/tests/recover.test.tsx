import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { renderScreen } from './helpers';
import { PasswordRecovery } from '../app/recover/PasswordRecovery';

const { goTo } = vi.hoisted(() => ({ goTo: vi.fn() }));
vi.mock('../app/lib/navigate', () => ({ goTo }));
beforeEach(() => goTo.mockReset());
const destination = 'https://authentik.test/if/flow/bill-self-service-recovery/';

it('offers honest administrator assistance without SMTP or collecting credentials', () => {
  renderScreen(<PasswordRecovery destination={null} signInHref="/login" />);
  expect(screen.getByRole('heading', { name: 'Forgot password?' })).toBeInTheDocument();
  expect(screen.getByRole('status')).toHaveTextContent('Email password recovery is not available yet.');
  expect(screen.getByText(/No email has been sent from this page/)).toBeInTheDocument();
  expect(screen.getByText(/verify your identity before sharing/)).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Continue to reset password' })).not.toBeInTheDocument();
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  expect(goTo).not.toHaveBeenCalled();
});
it('explains email proof, link expiry, existing factors and delivery troubleshooting', () => {
  renderScreen(<PasswordRecovery destination={destination} signInHref="/login" />);
  expect(screen.getByText(/If your account is eligible/)).toHaveTextContent('10 minutes and can be used once');
  expect(screen.getByText(/configured authentication checks/)).toBeInTheDocument();
  expect(screen.getByText(/spam folder/)).toBeInTheDocument();
  expect(screen.queryByText('Email password recovery is not available yet.')).not.toBeInTheDocument();
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
});
it('opens only the supplied native flow and blocks repeated clicks while leaving', async () => {
  renderScreen(<PasswordRecovery destination={destination} signInHref="/login" />);
  await userEvent.dblClick(screen.getByRole('button', { name: 'Continue to reset password' }));
  expect(goTo).toHaveBeenCalledTimes(1);
  expect(goTo).toHaveBeenCalledWith(destination);
  expect(screen.getByRole('button', { name: 'Opening recovery…' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Opening recovery…' })).toHaveAttribute('aria-busy', 'true');
});
it('allows an explicit retry if the browser cannot open recovery', async () => {
  goTo.mockImplementationOnce(() => { throw new Error('private failure'); });
  renderScreen(<PasswordRecovery destination={destination} signInHref="/login" />);
  await userEvent.click(screen.getByRole('button', { name: 'Continue to reset password' }));
  expect(screen.getByRole('alert')).toHaveTextContent('We could not open password recovery.');
  expect(screen.getByRole('alert')).not.toHaveTextContent('private failure');
  await userEvent.click(screen.getByRole('button', { name: 'Continue to reset password' }));
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  expect(goTo).toHaveBeenCalledTimes(2);
});
it.each([null, destination])('preserves the reviewed destination in both back links: %s', (url) => {
  const signInHref = '/login?returnTo=' + encodeURIComponent('https://books.test/vouchers?draft=1');
  renderScreen(<PasswordRecovery destination={url} signInHref={signInHref} />);
  const backLinks = screen.getAllByRole('link', { name: 'Back to sign in' });
  expect(backLinks).toHaveLength(2);
  for (const link of backLinks) expect(link).toHaveAttribute('href', signInHref);
  expect(screen.getByRole('link', { name: 'Sign in' })).toHaveAttribute('href', signInHref);
});
