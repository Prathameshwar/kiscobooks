import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';
import ConsoleError from '../app/error';
const { goTo } = vi.hoisted(() => ({ goTo: vi.fn() }));
vi.mock('../app/lib/navigate', () => ({ goTo, signInUrl: () => 'https://auth.test/login' }));
it('offers retry and sign in for unavailable session/company access without exposing server details', async () => {
  const reset = vi.fn(); render(<ConsoleError reset={reset} error={new Error('private database failure')} />);
  expect(screen.getByRole('alert')).toHaveTextContent('Unable to load your books');
  expect(screen.queryByText('private database failure')).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Try again' })); expect(reset).toHaveBeenCalledTimes(1);
  await userEvent.click(screen.getByRole('button', { name: 'Sign in' })); expect(goTo).toHaveBeenCalledWith('https://auth.test/login');
});
