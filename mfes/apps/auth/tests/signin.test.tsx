import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderScreen } from './helpers';
import { SignInForm } from '../app/signin/SignInForm';

const { goTo } = vi.hoisted(() => ({ goTo: vi.fn() }));
vi.mock('../app/lib/navigate', () => ({ goTo, consoleUrl: () => 'http://localhost:4320' }));

const REQUEST_ID = 'rq_9f8e7d6c5b4a39281706f5e4d3c2b1a0';
const LEAK = 'SHOULD-NEVER-BE-SHOWN';
const password = 'Correct Horse 9! battery';
const callback = () => `${window.location.origin}/api/auth/callback/local?code=abc&state=xyz`;
let check: () => Response | Promise<Response>;
let login: () => Response | Promise<Response>;
let fetcher: ReturnType<typeof vi.fn>;
const posts = () => fetcher.mock.calls.filter(([, init]) => init?.method === 'POST');
beforeEach(() => {
  goTo.mockReset();
  check = () => Response.json({ valid: true });
  login = () => Response.json({ redirect_to: callback() });
  fetcher = vi.fn(async (_input: unknown, init?: RequestInit) => init?.method === 'POST' ? login() : check());
  vi.stubGlobal('fetch', fetcher);
});
afterEach(() => vi.unstubAllGlobals());

async function fill(email = 'Person@Example.Test', secret = password) {
  if (email) fireEvent.change(screen.getByLabelText('Username or email address'), { target: { value: email } });
  if (secret) fireEvent.change(screen.getByLabelText('Password', { exact: true }), { target: { value: secret } });
}
const submit = () => userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
const open = () => renderScreen(<SignInForm requestId={REQUEST_ID} available />);

describe('the sign-in form', () => {
  it('is an accessible email and password form with a show/hide toggle and a way to recover', () => {
    open();
    expect(screen.getByRole('heading', { level: 1, name: 'Sign in' })).toBeInTheDocument();
    expect(screen.getByRole('form', { name: 'Sign in' })).toBeInTheDocument();
    expect(screen.getByLabelText('Username or email address')).toHaveAttribute('type', 'text');
    expect(screen.getByLabelText('Username or email address')).toHaveAttribute('autocomplete', 'username');
    expect(screen.getByLabelText('Password', { exact: true })).toHaveAttribute('type', 'password');
    expect(screen.getByLabelText('Password', { exact: true })).toHaveAttribute('autocomplete', 'current-password');
    expect(screen.getByRole('link', { name: 'Forgot password?' })).toHaveAttribute('href', '/recover');
    expect(screen.getByRole('link', { name: 'Create account' })).toHaveAttribute('href', '/signup');
    expect(screen.queryByText(/Authentik/)).not.toBeInTheDocument();
  });
  it('puts account creation in the card footer band and keeps the one action out of it', () => {
    const { container } = open();
    const band = container.querySelector('.auth__foot--band') as HTMLElement;
    expect(band).toHaveTextContent('New to KiscoBooks?');
    expect(band.querySelector('a[href="/signup"]')).toBeInTheDocument();
    expect(band.querySelector('button')).toBeNull();
    expect(band).toBe(band.parentElement!.lastElementChild);
    expect(container.querySelector('form button[type="submit"]')).toBeInTheDocument();
  });
  it('shows and hides the password on request', async () => {
    open();
    await fill('', 'secret-value');
    const toggle = screen.getByRole('button', { name: 'Show password' });
    expect(toggle).toHaveAttribute('aria-pressed', 'false');
    await userEvent.click(toggle);
    expect(screen.getByLabelText('Password', { exact: true })).toHaveAttribute('type', 'text');
    await userEvent.click(screen.getByRole('button', { name: 'Hide password' }));
    expect(screen.getByLabelText('Password', { exact: true })).toHaveAttribute('type', 'password');
  });

  describe('the sign-in request', () => {
    it('is checked on load and the form stays when it is open', async () => {
      open();
      await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
      expect(String(fetcher.mock.calls[0][0])).toBe(`/api/local/login?request=${REQUEST_ID}`);
      expect(fetcher.mock.calls[0][1]).toMatchObject({ cache: 'no-store' });
      expect(screen.getByRole('form', { name: 'Sign in' })).toBeInTheDocument();
    });
    it('shows the expired state early when the request is unknown, expired or used', async () => {
      check = () => Response.json({ valid: false }, { status: 404 });
      open();
      expect(await screen.findByRole('heading', { name: 'Sign-in request expired' })).toBeInTheDocument();
      expect(screen.getByRole('status')).toHaveTextContent('This sign-in request has expired. Start again.');
      expect(screen.getByRole('link', { name: 'Start sign in again' })).toHaveAttribute('href', '/login');
      expect(screen.queryByLabelText('Password', { exact: true })).not.toBeInTheDocument();
    });
    it.each([['a server error', () => Response.json({}, { status: 503 })], ['a network error', () => Promise.reject(new Error('offline'))]])(
      'keeps the form usable when the check itself fails: %s', async (_name, answer) => {
        check = answer as typeof check;
        open();
        await waitFor(() => expect(fetcher).toHaveBeenCalled());
        await new Promise(resolve => setTimeout(resolve, 20));
        expect(screen.getByRole('form', { name: 'Sign in' })).toBeInTheDocument();
      });
    it('shows the expired state, without any request, when the link carries no usable id', () => {
      renderScreen(<SignInForm requestId={null} available />);
      expect(screen.getByRole('heading', { name: 'Sign-in request expired' })).toBeInTheDocument();
      expect(fetcher).not.toHaveBeenCalled();
    });
    it('explains that the page is off when the local provider is not in use', () => {
      renderScreen(<SignInForm requestId={REQUEST_ID} available={false} />);
      expect(screen.getByRole('status')).toHaveTextContent('not enabled for this installation');
      expect(screen.getByRole('link', { name: 'Back to sign in' })).toHaveAttribute('href', '/login');
      expect(screen.queryByLabelText('Username or email address')).not.toBeInTheDocument();
      expect(fetcher).not.toHaveBeenCalled();
    });
  });

  describe('validation', () => {
    it('asks for both fields without contacting the server and moves focus to the first problem', async () => {
      open();
      await submit();
      expect(screen.getAllByRole('alert').map(alert => alert.textContent).join(' ')).toMatch(/Enter your username or email address/);
      expect(screen.getByLabelText('Username or email address')).toHaveAttribute('aria-invalid', 'true');
      expect(screen.getByLabelText('Password', { exact: true })).toHaveAttribute('aria-invalid', 'true');
      expect(screen.getByLabelText('Username or email address')).toHaveFocus();
      expect(posts()).toHaveLength(0);
    });
    it('rejects a malformed email and an empty password', async () => {
      open();
      await fill('bad@address', '');
      await submit();
      expect(screen.getByLabelText('Username or email address')).toHaveAttribute('aria-invalid', 'true');
      expect(posts()).toHaveLength(0);
    });
    it('clears a field\'s error as it is edited', async () => {
      open();
      await submit();
      await userEvent.type(screen.getByLabelText('Username or email address'), 'a');
      expect(screen.getByLabelText('Username or email address')).not.toHaveAttribute('aria-invalid');
    });
  });

  describe('a successful sign-in', () => {
    it('accepts a username, normalises its case and sends it as the identifier', async () => {
      open();
      await fill(' TENANT1 ');
      await submit();
      await waitFor(() => expect(goTo).toHaveBeenCalledWith(callback()));
      expect(JSON.parse(posts()[0][1].body)).toEqual({ request_id: REQUEST_ID, identifier: 'tenant1', password });
    });
    it('sends the normalised email and the password once, then follows this app\'s own callback', async () => {
      open();
      await fill();
      await submit();
      await waitFor(() => expect(goTo).toHaveBeenCalledWith(callback()));
      expect(posts()).toHaveLength(1);
      const [url, init] = posts()[0];
      expect(String(url)).toBe('/api/local/login');
      expect(init.headers).toEqual({ 'Content-Type': 'application/json' });
      expect(JSON.parse(init.body)).toEqual({ request_id: REQUEST_ID, identifier: 'person@example.test', password });
      expect(goTo).toHaveBeenCalledTimes(1);
    });
    it('stays busy while the browser leaves, so it cannot be submitted twice, and keeps no password', async () => {
      open();
      await fill();
      await submit();
      await waitFor(() => expect(goTo).toHaveBeenCalled());
      expect(screen.getByRole('button', { name: 'Signing in…' })).toBeDisabled();
      expect(screen.getByLabelText('Password', { exact: true })).toHaveValue('');
    });
    it.each([
      ['another origin', 'https://evil.test/api/auth/callback/local?code=1&state=2'],
      ['a look-alike host', `${'http://'}localhost.evil.test/api/auth/callback/local`],
      ['another path on this origin', `${window.location.origin}/setup`],
      ['a parent-path escape', `${window.location.origin}/api/auth/callback/../signin`],
      ['credentials on this origin', `http://user:pw@${window.location.host}/api/auth/callback/local`],
      ['a relative URL', '/api/auth/callback/local?code=1'],
      ['a scripted URL', 'javascript:alert(1)'],
      ['nothing', undefined],
    ])('never follows %s', async (_name, redirect_to) => {
      login = () => Response.json({ redirect_to });
      open();
      await fill();
      await submit();
      expect(await screen.findByRole('alert')).toHaveTextContent('temporarily unavailable');
      expect(goTo).not.toHaveBeenCalled();
      expect(screen.getByRole('button', { name: 'Sign in' })).toBeEnabled();
    });
  });

  describe('every failure has one fixed message', () => {
    it.each([
      [401, {}, 'Username, email or password is incorrect.'],
      [403, { code: 'account_pending' }, 'Your account is waiting for administrator approval. You can sign in once it has been approved.'],
      [423, { retry_after_minutes: 15 }, 'This account is temporarily locked after too many failed attempts. Try again in 15 minutes.'],
      [423, { retry_after_minutes: 1 }, 'This account is temporarily locked after too many failed attempts. Try again in 1 minute.'],
      [423, { retry_after_minutes: 'soon' }, 'This account is temporarily locked after too many failed attempts. Please try again later.'],
      [429, {}, 'Too many attempts. Please wait a few minutes and try again.'],
      [422, {}, 'Enter your username or email address and password.'],
      [500, {}, 'Sign in is temporarily unavailable. Please try again.'],
      [503, {}, 'Sign in is temporarily unavailable. Please try again.'],
    ])('HTTP %i shows its message, never the server text, and empties the password', async (status, extra, message) => {
      login = () => Response.json({ error: LEAK, detail: LEAK, ...extra }, { status });
      open();
      await fill();
      await submit();
      const alert = await screen.findByRole('alert');
      expect(alert).toHaveTextContent(message);
      expect(document.body).not.toHaveTextContent(LEAK);
      expect(screen.getByLabelText('Password', { exact: true })).toHaveValue('');
      expect(screen.getByLabelText('Username or email address')).toHaveValue('Person@Example.Test');
      expect(screen.getByLabelText('Password', { exact: true })).toHaveFocus();
      expect(screen.getByRole('button', { name: 'Sign in' })).toBeEnabled();
    });
    it('a network failure is a temporary failure and can be retried', async () => {
      login = () => Promise.reject(new Error('offline'));
      open();
      await fill();
      await submit();
      expect(await screen.findByRole('alert')).toHaveTextContent('temporarily unavailable');
      login = () => Response.json({ redirect_to: callback() });
      await userEvent.type(screen.getByLabelText('Password', { exact: true }), password);
      await submit();
      await waitFor(() => expect(goTo).toHaveBeenCalledWith(callback()));
    });
    it('an unreadable answer is a temporary failure', async () => {
      login = () => new Response('<html>gateway</html>', { status: 200 });
      open();
      await fill();
      await submit();
      expect(await screen.findByRole('alert')).toHaveTextContent('temporarily unavailable');
      expect(goTo).not.toHaveBeenCalled();
    });
    it('a 404 on sign-in switches to the expired state with a way to start again', async () => {
      login = () => Response.json({ code: 'request_expired' }, { status: 404 });
      open();
      await fill();
      await submit();
      expect(await screen.findByRole('heading', { name: 'Sign-in request expired' })).toBeInTheDocument();
      expect(screen.getByRole('link', { name: 'Start sign in again' })).toHaveAttribute('href', '/login');
    });
    it('puts the next attempt in a clean error state', async () => {
      login = () => Response.json({}, { status: 401 });
      open();
      await fill();
      await submit();
      await screen.findByRole('alert');
      login = () => Response.json({ redirect_to: callback() });
      await userEvent.type(screen.getByLabelText('Password', { exact: true }), password);
      await submit();
      await waitFor(() => expect(goTo).toHaveBeenCalled());
      expect(screen.queryByText('Username, email or password is incorrect.')).not.toBeInTheDocument();
    });
  });

  describe('pending state', () => {
    it('disables and marks the form busy, and sends one request however often it is clicked', async () => {
      login = () => new Promise<Response>(() => undefined);
      open();
      await fill();
      await userEvent.dblClick(screen.getByRole('button', { name: 'Sign in' }));
      const busy = screen.getByRole('button', { name: 'Signing in…' });
      expect(busy).toBeDisabled();
      expect(busy).toHaveAttribute('aria-busy', 'true');
      expect(screen.getByRole('form', { name: 'Sign in' })).toHaveAttribute('aria-busy', 'true');
      expect(screen.getByLabelText('Username or email address')).toHaveAttribute('readonly');
      expect(posts()).toHaveLength(1);
    });
  });

  describe('the password stays out of the page', () => {
    it('is never rendered as text, in a link or in the URL', async () => {
      login = () => Response.json({}, { status: 401 });
      open();
      await fill();
      await submit();
      await screen.findByRole('alert');
      expect(document.body.innerHTML).not.toContain(password);
      expect(window.location.href).not.toContain('Correct');
      for (const link of screen.getAllByRole('link')) expect(link.getAttribute('href')).not.toContain('Correct');
    });
  });
});
