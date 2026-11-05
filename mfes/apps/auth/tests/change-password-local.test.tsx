import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderScreen } from './helpers';
import { LocalChangePassword } from '../app/change-password/LocalChangePassword';

const { signOut } = vi.hoisted(() => ({ signOut: vi.fn() }));
vi.mock('next-auth/react', () => ({ signOut }));
vi.mock('../app/lib/navigate', () => ({ consoleUrl: () => 'http://localhost:4320', goTo: vi.fn() }));

const current = 'My Current Passphrase 1!';
const next = 'My Brand New Passphrase 2!';
const LEAK = 'SHOULD-NEVER-BE-SHOWN';
let answer: () => Response | Promise<Response>;
let fetcher: ReturnType<typeof vi.fn>;
beforeEach(() => {
  signOut.mockReset().mockResolvedValue(undefined);
  answer = () => Response.json({ changed: true });
  fetcher = vi.fn(async () => answer());
  vi.stubGlobal('fetch', fetcher);
});
afterEach(() => vi.unstubAllGlobals());

// Paste rather than type: a 129-character value typed key by key outlives the test timeout.
async function enter(label: string, value: string, exact = true) {
  await userEvent.click(screen.getByLabelText(label, { exact }));
  await userEvent.paste(value);
}
async function fill(values: { current?: string; next?: string; again?: string } = {}) {
  const { current: now = current, next: fresh = next, again = fresh } = values;
  if (now) await enter('Current password', now, true);
  if (fresh) await enter('New password', fresh, true);
  if (again) await enter('Confirm new password', again);
}
const submit = () => userEvent.click(screen.getByRole('button', { name: 'Change password' }));
const open = () => renderScreen(<LocalChangePassword />);

describe('the in-app form', () => {
  it('asks for the current password, the new one twice, with password-manager hints and back navigation', () => {
    open();
    expect(screen.getByRole('heading', { level: 1, name: 'Change password' })).toBeInTheDocument();
    expect(screen.getByLabelText('Current password', { exact: true })).toHaveAttribute('autocomplete', 'current-password');
    expect(screen.getByLabelText('New password', { exact: true })).toHaveAttribute('autocomplete', 'new-password');
    expect(screen.getByLabelText('Confirm new password')).toHaveAttribute('autocomplete', 'new-password');
    expect(screen.getByRole('link', { name: 'Back to your workspace' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Sign out' })).toHaveAttribute('href', '/logout');
    expect(document.body).not.toHaveTextContent('Authentik');
    expect(fetcher).not.toHaveBeenCalled();
  });
  it('validates before contacting the server', async () => {
    open();
    await fill({ current: '', next: 'short', again: 'different' });
    await submit();
    expect(screen.getByLabelText('Current password', { exact: true })).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByLabelText('New password', { exact: true })).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByText('Passwords must match.')).toBeInTheDocument();
    expect(screen.getByLabelText('Current password', { exact: true })).toHaveFocus();
    expect(fetcher).not.toHaveBeenCalled();
  });
  it('refuses a new password equal to the current one', async () => {
    open();
    await fill({ next: current });
    await submit();
    expect(screen.getByText('Choose a password that is different from your current one.')).toBeInTheDocument();
    expect(fetcher).not.toHaveBeenCalled();
  });
  it.each([5, 129])('applies the 6–128 character rule: %i', async length => {
    open();
    await fill({ next: 'a'.repeat(length) });
    await submit();
    expect(screen.getByLabelText('New password', { exact: true })).toHaveAttribute('aria-invalid', 'true');
    expect(fetcher).not.toHaveBeenCalled();
  });
});

describe('a successful change', () => {
  it('posts exactly the two passwords, signs out and sends the person to sign in again', async () => {
    open();
    await fill();
    await submit();
    await waitFor(() => expect(signOut).toHaveBeenCalledTimes(1));
    const [url, init] = fetcher.mock.calls[0];
    expect(url).toBe('/api/change-password');
    expect(init).toMatchObject({ method: 'POST', cache: 'no-store', headers: { 'Content-Type': 'application/json' } });
    expect(JSON.parse(init.body)).toEqual({ current_password: current, new_password: next });
    expect(signOut).toHaveBeenCalledWith({ callbackUrl: new URL('/login?passwordChanged=1', window.location.href).href });
    expect(screen.getByRole('status')).toHaveTextContent('Your password was changed.');
    expect(screen.getByRole('link', { name: 'Continue to sign in' })).toHaveAttribute('href', '/login?passwordChanged=1');
    expect(screen.queryByLabelText('Current password', { exact: true })).not.toBeInTheDocument();
    expect(document.body.innerHTML).not.toContain(next);
    expect(document.body.innerHTML).not.toContain(current);
  });
  it('still confirms success, with a link, if signing out fails', async () => {
    signOut.mockRejectedValue(new Error('offline'));
    open();
    await fill();
    await submit();
    expect(await screen.findByRole('status')).toHaveTextContent('Your password was changed.');
    expect(screen.getByRole('link', { name: 'Continue to sign in' })).toBeInTheDocument();
  });
  it('shows a pending state and sends one request however often it is clicked', async () => {
    answer = () => new Promise<Response>(() => undefined);
    open();
    await fill();
    await userEvent.dblClick(screen.getByRole('button', { name: 'Change password' }));
    const busy = screen.getByRole('button', { name: 'Changing password…' });
    expect(busy).toBeDisabled();
    expect(busy).toHaveAttribute('aria-busy', 'true');
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});

describe('failures', () => {
  it('401 says the session ended and links to sign in', async () => {
    answer = () => Response.json({ error: LEAK }, { status: 401 });
    open();
    await fill();
    await submit();
    expect(await screen.findByRole('alert')).toHaveTextContent('Your session has ended. Sign in again before changing your password.');
    expect(screen.getByRole('link', { name: 'Sign in again' })).toHaveAttribute('href', '/login');
    expect(document.body).not.toHaveTextContent(LEAK);
    expect(signOut).not.toHaveBeenCalled();
  });
  it('422 on the current password marks that field, keeps the form and empties the passwords', async () => {
    answer = () => Response.json({ error: LEAK, fields: { current_password: LEAK } }, { status: 422 });
    open();
    await fill();
    await submit();
    expect(await screen.findByText('Your current password is incorrect.', { selector: 'p' })).toBeInTheDocument();
    expect(screen.getByLabelText('Current password', { exact: true })).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByLabelText('New password', { exact: true })).not.toHaveAttribute('aria-invalid');
    expect(screen.getByLabelText('Current password', { exact: true })).toHaveValue('');
    expect(screen.getByLabelText('New password', { exact: true })).toHaveValue('');
    expect(screen.getByLabelText('Current password', { exact: true })).toHaveFocus();
    expect(document.body).not.toHaveTextContent(LEAK);
    expect(signOut).not.toHaveBeenCalled();
  });
  it('422 on the new password marks that field', async () => {
    answer = () => Response.json({ fields: { new_password: LEAK } }, { status: 422 });
    open();
    await fill();
    await submit();
    expect(await screen.findByText('Choose a different password. This one cannot be used.', { selector: 'p' })).toBeInTheDocument();
    expect(screen.getByLabelText('New password', { exact: true })).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByLabelText('New password', { exact: true })).toHaveFocus();
  });
  it.each([[429, 'Too many attempts. Please wait a few minutes and try again.'], [500, 'Password change is temporarily unavailable. Please try again.'],
    [503, 'Password change is temporarily unavailable. Please try again.'], [422, 'Password change is temporarily unavailable. Please try again.']])(
    'HTTP %i shows a fixed message and can be retried', async (status, message) => {
      answer = () => Response.json({ error: LEAK }, { status });
      open();
      await fill();
      await submit();
      expect(await screen.findByRole('alert')).toHaveTextContent(message);
      expect(document.body).not.toHaveTextContent(LEAK);
      expect(screen.getByRole('button', { name: 'Change password' })).toBeEnabled();
      answer = () => Response.json({ changed: true });
      await fill();
      await submit();
      await waitFor(() => expect(signOut).toHaveBeenCalled());
    });
  it('a network failure is a temporary failure', async () => {
    answer = () => Promise.reject(new Error('offline'));
    open();
    await fill();
    await submit();
    expect(await screen.findByRole('alert')).toHaveTextContent('temporarily unavailable');
    expect(signOut).not.toHaveBeenCalled();
  });
  it('an answer that is not a clear success does not sign anyone out', async () => {
    answer = () => Response.json({ changed: 'maybe' });
    open();
    await fill();
    await submit();
    expect(await screen.findByRole('alert')).toHaveTextContent('temporarily unavailable');
    expect(signOut).not.toHaveBeenCalled();
  });
});
