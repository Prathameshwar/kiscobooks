import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { renderScreen } from './helpers';
import LogoutPage from '../app/logout/page';
const { signOut } = vi.hoisted(() => ({ signOut: vi.fn() }));
vi.mock('next-auth/react', () => ({ signOut }));
beforeEach(() => { signOut.mockReset(); });
it('requires confirmation and exposes a pending state for the protected logout', async () => {
  signOut.mockReturnValue(new Promise(() => {}));
  renderScreen(<LogoutPage />);
  expect(screen.getByRole('heading', { name: 'Sign out' })).toBeInTheDocument();
  expect(signOut).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole('button', { name: 'Sign out' }));
  expect(signOut).toHaveBeenCalledWith({ callbackUrl: expect.stringContaining('/login') });
  expect(screen.getByRole('button', { name: 'Signing out…' })).toBeDisabled();
});
it('offers a retry without showing exception details', async () => {
  signOut.mockRejectedValue(new Error('private provider error'));
  renderScreen(<LogoutPage />);
  await userEvent.click(screen.getByRole('button', { name: 'Sign out' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Unable to sign out');
  expect(screen.queryByText('private provider error')).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Sign out' })).toBeEnabled();
});
