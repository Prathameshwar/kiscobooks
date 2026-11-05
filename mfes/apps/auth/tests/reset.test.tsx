import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderScreen } from './helpers';
import { ResetForm } from '../app/reset/ResetForm';

const { goTo } = vi.hoisted(() => ({ goTo: vi.fn() }));
vi.mock('../app/lib/navigate', () => ({ goTo, consoleUrl: () => 'http://localhost:4320' }));

const TOKEN = 'tk_0a1b2c3d4e5f60718293a4b5c6d7e8f9';
const LEAK = 'SHOULD-NEVER-BE-SHOWN';
const next = 'A Brand New Passphrase 42!';
let inspect: () => Response | Promise<Response>;
let redeem: () => Response | Promise<Response>;
let fetcher: ReturnType<typeof vi.fn>;
const actions = () => fetcher.mock.calls.map(([, init]) => JSON.parse(init.body).action);
beforeEach(() => {
  goTo.mockReset();
  inspect = () => Response.json({ valid: true });
  redeem = () => Response.json({ redeemed: true });
  fetcher = vi.fn(async (_url: unknown, init: RequestInit) => JSON.parse(String(init.body)).action === 'inspect' ? inspect() : redeem());
  vi.stubGlobal('fetch', fetcher);
});
afterEach(() => vi.unstubAllGlobals());

const open = (token: string | null = TOKEN, available = true) => renderScreen(<ResetForm token={token} available={available} />);
async function ready() {
  open();
  await screen.findByRole('form', { name: 'Reset password' });
}
// Paste rather than type: a 129-character value typed key by key outlives the test timeout.
async function enter(label: string, value: string, exact = true) {
  await userEvent.click(screen.getByLabelText(label, { exact }));
  await userEvent.paste(value);
}
async function fill(password = next, confirmation = password) {
  if (password) await enter('New password', password, true);
  if (confirmation) await enter('Confirm new password', confirmation);
}
const save = () => userEvent.click(screen.getByRole('button', { name: 'Set new password' }));

describe('the link is checked first', () => {
  it('verifies the token with the server before showing the password form', async () => {
    open();
    expect(screen.getByRole('status')).toHaveTextContent('Checking your recovery link');
    expect(screen.queryByLabelText('New password', { exact: true })).not.toBeInTheDocument();
    expect(await screen.findByRole('form', { name: 'Reset password' })).toBeInTheDocument();
    expect(fetcher).toHaveBeenCalledTimes(1);
    const [url, init] = fetcher.mock.calls[0];
    expect(url).toBe('/api/local/recover');
    expect(init).toMatchObject({ method: 'POST', cache: 'no-store' });
    expect(JSON.parse(init.body)).toEqual({ action: 'inspect', token: TOKEN });
  });
  it('says so plainly when the link is invalid, expired or already used, and offers a way back', async () => {
    inspect = () => Response.json({ valid: false }, { status: 404 });
    open();
    expect(await screen.findByRole('alert')).toHaveTextContent('This recovery link is invalid or has expired. Ask your administrator for a new one.');
    expect(screen.queryByLabelText('New password', { exact: true })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Back to sign in' })).toHaveAttribute('href', '/login');
  });
  it('shows the invalid state without any request when the link carries no usable token', () => {
    open(null);
    expect(screen.getByRole('alert')).toHaveTextContent('invalid or has expired');
    expect(fetcher).not.toHaveBeenCalled();
  });
  it('is switched off when the local provider is not in use', () => {
    open(TOKEN, false);
    expect(screen.getByRole('status')).toHaveTextContent('not enabled for this installation');
    expect(fetcher).not.toHaveBeenCalled();
  });
  it.each([['a server error', () => Response.json({}, { status: 503 })], ['a rate limit', () => Response.json({}, { status: 429 })],
    ['a network failure', () => Promise.reject(new Error('offline'))]])('separates an unavailable service from an invalid link: %s', async (_name, answer) => {
    inspect = answer as typeof inspect;
    open();
    expect(await screen.findByText('Password recovery is temporarily unavailable. Please try again.')).toBeInTheDocument();
    expect(screen.queryByText(/invalid or has expired/)).not.toBeInTheDocument();
    inspect = () => Response.json({ valid: true });
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('form', { name: 'Reset password' })).toBeInTheDocument();
    expect(actions()).toEqual(['inspect', 'inspect']);
  });
});

describe('the new password', () => {
  it('uses the shared rule and asks for a matching confirmation, without contacting the server', async () => {
    await ready();
    await fill('short', 'different');
    await save();
    expect(screen.getByLabelText('New password', { exact: true })).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByLabelText('Confirm new password')).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByText('Passwords must match.')).toBeInTheDocument();
    expect(screen.getByLabelText('New password', { exact: true })).toHaveFocus();
    expect(actions()).toEqual(['inspect']);
  });
  it.each([5, 129])('rejects %i characters', async length => {
    await ready();
    await fill('a'.repeat(length));
    await save();
    expect(screen.getByLabelText('New password', { exact: true })).toHaveAttribute('aria-invalid', 'true');
    expect(actions()).toEqual(['inspect']);
  });
  it('accepts the boundaries, counting Unicode characters', async () => {
    await ready();
    await fill('😀'.repeat(6));
    await save();
    await waitFor(() => expect(goTo).toHaveBeenCalled());
  });
  it('is a new-password field for password managers, with a confirmation and show/hide', async () => {
    await ready();
    expect(screen.getByLabelText('New password', { exact: true })).toHaveAttribute('autocomplete', 'new-password');
    expect(screen.getByLabelText('Confirm new password')).toHaveAttribute('autocomplete', 'new-password');
    expect(screen.getByRole('button', { name: 'Show new password' })).toBeInTheDocument();
  });
});

describe('redeeming the link', () => {
  it('sets the password once and sends the person to sign in', async () => {
    await ready();
    await fill();
    await save();
    await waitFor(() => expect(goTo).toHaveBeenCalledWith('/login?recovery=complete'));
    expect(goTo).toHaveBeenCalledTimes(1);
    const [, init] = fetcher.mock.calls[1];
    expect(JSON.parse(init.body)).toEqual({ action: 'redeem', token: TOKEN, new_password: next });
    expect(screen.getByLabelText('New password', { exact: true })).toHaveValue('');
  });
  it('shows a pending state and sends one request however often it is clicked', async () => {
    redeem = () => new Promise<Response>(() => undefined);
    await ready();
    await fill();
    await userEvent.dblClick(screen.getByRole('button', { name: 'Set new password' }));
    const busy = screen.getByRole('button', { name: 'Saving…' });
    expect(busy).toBeDisabled();
    expect(busy).toHaveAttribute('aria-busy', 'true');
    expect(actions()).toEqual(['inspect', 'redeem']);
  });
  it('a link that was spent in the meantime becomes the invalid state', async () => {
    redeem = () => Response.json({ valid: false }, { status: 404 });
    await ready();
    await fill();
    await save();
    expect(await screen.findByRole('alert')).toHaveTextContent('invalid or has expired');
    expect(screen.queryByLabelText('New password', { exact: true })).not.toBeInTheDocument();
    expect(goTo).not.toHaveBeenCalled();
  });
  it('a refused password is a fixed field error and the form stays open', async () => {
    redeem = () => Response.json({ error: LEAK, fields: { new_password: LEAK } }, { status: 422 });
    await ready();
    await fill();
    await save();
    expect(await screen.findAllByText('This password cannot be used. Check the length and that both entries match.')).not.toHaveLength(0);
    expect(document.body).not.toHaveTextContent(LEAK);
    expect(screen.getByLabelText('New password', { exact: true })).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByLabelText('New password', { exact: true })).toHaveValue('');
    expect(screen.getByRole('button', { name: 'Set new password' })).toBeEnabled();
    expect(goTo).not.toHaveBeenCalled();
  });
  it.each([[429, 'Too many attempts. Please wait a few minutes and try again.'], [500, 'Password recovery is temporarily unavailable. Please try again.'],
    [503, 'Password recovery is temporarily unavailable. Please try again.']])('HTTP %i shows its fixed message and can be retried', async (status, message) => {
    redeem = () => Response.json({ error: LEAK }, { status });
    await ready();
    await fill();
    await save();
    expect(await screen.findByRole('alert')).toHaveTextContent(message);
    expect(document.body).not.toHaveTextContent(LEAK);
    redeem = () => Response.json({ redeemed: true });
    await fill();
    await save();
    await waitFor(() => expect(goTo).toHaveBeenCalledWith('/login?recovery=complete'));
  });
  it('a network failure is a temporary failure', async () => {
    redeem = () => Promise.reject(new Error('offline'));
    await ready();
    await fill();
    await save();
    expect(await screen.findByRole('alert')).toHaveTextContent('temporarily unavailable');
    expect(goTo).not.toHaveBeenCalled();
  });
});

describe('the token and the password stay private', () => {
  it('never appear on the page, in a link or in any answer shown', async () => {
    redeem = () => Response.json({ error: LEAK }, { status: 500 });
    await ready();
    await fill();
    await save();
    await screen.findByRole('alert');
    expect(document.body.innerHTML).not.toContain(TOKEN);
    expect(document.body.innerHTML).not.toContain(next);
    for (const link of screen.getAllByRole('link')) expect(link.getAttribute('href')).not.toContain(TOKEN);
  });
});
