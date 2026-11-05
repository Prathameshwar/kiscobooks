/**
 * An administrator creating a one-time recovery link for another user (docs/local-auth.md §4).
 *
 * A link is a way into an account, so what is tested is what could leak or be misused: the link
 * must be exactly the provider's shape; it is never retried, stored or shown to someone who cannot
 * create it; and it is not offered for yourself or for a user who cannot be recovered.
 */
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { UserDetail } from '../app/components/UserDetail';
import { allowedAccessRequest } from '../app/lib/access-request-policy';
import { serviceCall } from '../app/lib/service-call';
import { access, page, userId, userRecord } from './access-fixtures';
import { renderWithProviders } from './helpers';

vi.mock('../app/lib/service-call', () => ({ serviceCall: vi.fn(), requestFailure: (e: unknown) => e }));

const token = 'A1b2C3d4E5f6G7h8I9j0K-L_mNoPqRsTuVwXyZ01234';
const link = `https://bill.example.com/reset?token=${token}`;
const receipt = (over: Record<string, unknown> = {}) => ({
  recovery_url: link,
  expires_at: new Date(Date.now() + 600_000).toISOString(),
  ...over,
});
const recoveries = () =>
  vi.mocked(serviceCall).mock.calls.filter(([, request]) => request.path.endsWith('/password-recovery'));

function serve(answer: () => unknown = () => receipt(), record: unknown = userRecord) {
  vi.mocked(serviceCall).mockImplementation((async (_: string, request: { path: string }) => {
    if (request.path.endsWith('/password-recovery')) return answer();
    return request.path === '/v1/users/' + userId ? record : page([]);
  }) as never);
}

async function open(context = access) {
  const user = userEvent.setup();
  await renderWithProviders(<UserDetail context={context} id={userId} />);
  await user.click(await screen.findByRole('button', { name: 'Create recovery link' }));
  return { user, dialog: within(await screen.findByRole('dialog')) };
}

beforeEach(() => {
  window.history.replaceState(null, '', '/users');
  vi.mocked(serviceCall).mockReset();
  serve();
});

describe('the request allowlist', () => {
  const id = '01990000-0000-7000-8000-000000000001';

  it('allows exactly one POST with no query', () => {
    expect(allowedAccessRequest('identity', 'POST', `/v1/users/${id}/password-recovery`)).toBe(true);
    for (const [method, path] of [
      ['GET', `/v1/users/${id}/password-recovery`],
      ['PATCH', `/v1/users/${id}/password-recovery`],
      ['POST', `/v1/users/${id}/password-recovery?x=1`],
      ['POST', `/v1/users/${id}/password-recovery/extra`],
      ['POST', '/v1/users/not-an-id/password-recovery'],
      ['POST', `/v1/users/${id}/../x/password-recovery`],
    ] as const) {
      expect(allowedAccessRequest('identity', method, path), `${method} ${path}`).toBe(false);
    }
  });
});

describe('who is offered it', () => {
  it('offers it to someone who may update users, for another active user', async () => {
    await renderWithProviders(<UserDetail context={access} id={userId} />);
    expect(await screen.findByRole('button', { name: 'Create recovery link' })).toBeInTheDocument();
  });

  it('does not offer it without the permission', async () => {
    const without = access.tenantPermissions.filter((key) => key !== 'user.update');
    await renderWithProviders(<UserDetail context={{ ...access, tenantPermissions: without }} id={userId} />);
    await screen.findByRole('heading', { name: 'Ava Singh' });
    expect(screen.queryByRole('button', { name: 'Create recovery link' })).not.toBeInTheDocument();
  });

  it('does not offer it for yourself — use change password', async () => {
    await renderWithProviders(<UserDetail context={{ ...access, userId }} id={userId} />);
    await screen.findByRole('heading', { name: 'Ava Singh' });
    expect(screen.queryByRole('button', { name: 'Create recovery link' })).not.toBeInTheDocument();
  });

  it.each(['invited', 'suspended', 'deactivated'])('does not offer it for a %s user', async (status) => {
    serve(() => receipt(), { ...userRecord, status });
    await renderWithProviders(<UserDetail context={access} id={userId} />);
    await screen.findByRole('heading', { name: 'Ava Singh' });
    expect(screen.queryByRole('button', { name: 'Create recovery link' })).not.toBeInTheDocument();
  });
});

describe('creating the link', () => {
  it('asks for a reason first and sends nothing without one', async () => {
    const { user, dialog } = await open();
    await user.click(dialog.getByRole('button', { name: 'Create recovery link' }));
    expect(await screen.findByText(/Enter a reason/)).toBeInTheDocument();
    expect(recoveries()).toHaveLength(0);
  });

  it('posts the reason once, with no idempotency key, and shows the link with when it expires', async () => {
    const { user, dialog } = await open();
    await user.type(dialog.getByLabelText('Reason'), '  Locked out after leave ');
    await user.click(dialog.getByRole('button', { name: 'Create recovery link' }));

    expect(await screen.findByRole('textbox', { name: 'Password recovery link' })).toHaveValue(link);
    expect(recoveries()).toHaveLength(1);
    const [, request] = recoveries()[0]!;
    expect(request).toMatchObject({
      path: `/v1/users/${userId}/password-recovery`,
      method: 'POST',
      body: { reason: 'Locked out after leave' },
    });
    expect(request).not.toHaveProperty('key');
    expect(screen.getByText(/Expires at/)).toBeInTheDocument();
  });

  it('copies the link on request and can hide it again', async () => {
    const { user, dialog } = await open();
    await user.type(dialog.getByLabelText('Reason'), 'Locked out');
    await user.click(dialog.getByRole('button', { name: 'Create recovery link' }));
    await screen.findByRole('textbox', { name: 'Password recovery link' });

    // `userEvent.setup()` installs its own clipboard, so the spy goes on after it.
    const write = vi.spyOn(navigator.clipboard, 'writeText');
    await user.click(screen.getByRole('button', { name: 'Copy recovery link' }));
    expect(write).toHaveBeenCalledWith(link);
    await user.click(screen.getByRole('button', { name: 'Hide recovery link' }));
    expect(screen.queryByRole('textbox', { name: 'Password recovery link' })).not.toBeInTheDocument();
  });

  it('never keeps the link in browser storage', async () => {
    sessionStorage.clear();
    localStorage.clear();
    const { user, dialog } = await open();
    await user.type(dialog.getByLabelText('Reason'), 'Locked out');
    await user.click(dialog.getByRole('button', { name: 'Create recovery link' }));
    await screen.findByRole('textbox', { name: 'Password recovery link' });
    expect(JSON.stringify({ ...sessionStorage, ...localStorage })).not.toContain(token);
  });

  it.each([
    ['another site', { recovery_url: `https://evil.example/reset?token=${token}&next=https://evil.example` }],
    ['plain http to a real host', { recovery_url: `http://bill.example.com/reset?token=${token}` }],
    ['a short token', { recovery_url: 'https://bill.example.com/reset?token=short' }],
    ['no link', { recovery_url: null }],
    ['an already-expired link', { expires_at: new Date(Date.now() - 1000).toISOString() }],
    ['a link good for far too long', { expires_at: new Date(Date.now() + 3_600_000).toISOString() }],
  ])('refuses a receipt carrying %s, and shows nothing', async (_, over) => {
    serve(() => receipt(over));
    const { user, dialog } = await open();
    await user.type(dialog.getByLabelText('Reason'), 'Locked out');
    await user.click(dialog.getByRole('button', { name: 'Create recovery link' }));
    await waitFor(() => expect(recoveries()).toHaveLength(1));
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.queryByRole('textbox', { name: 'Password recovery link' })).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue(/evil\.example|short/)).not.toBeInTheDocument();
  });

  it('shows a refusal and does not retry it — a second link would cancel the first', async () => {
    vi.mocked(serviceCall).mockImplementation((async (_: string, request: { path: string }) => {
      if (request.path.endsWith('/password-recovery')) {
        throw { status: 409, message: 'This account does not use local sign-in.' };
      }
      return request.path === '/v1/users/' + userId ? userRecord : page([]);
    }) as never);
    const { user, dialog } = await open();
    await user.type(dialog.getByLabelText('Reason'), 'Locked out');
    await user.click(dialog.getByRole('button', { name: 'Create recovery link' }));
    expect(await screen.findByText(/does not use local sign-in/)).toBeInTheDocument();
    expect(recoveries()).toHaveLength(1);
    expect(screen.queryByRole('textbox', { name: 'Password recovery link' })).not.toBeInTheDocument();
  });

  it('asks the operator to sign in again when the server wants a fresh sign-in, and returns here', async () => {
    window.history.replaceState(null, '', '/users?tab=access');
    vi.mocked(serviceCall).mockImplementation((async (_: string, request: { path: string }) => {
      if (request.path.endsWith('/password-recovery')) {
        throw { status: 403, code: 'reauthentication_required', message: 'Sign in again to confirm this administrative action.' };
      }
      return request.path === '/v1/users/' + userId ? userRecord : page([]);
    }) as never);
    const { user, dialog } = await open();
    await user.type(dialog.getByLabelText('Reason'), 'Locked out');
    await user.click(dialog.getByRole('button', { name: 'Create recovery link' }));
    const again = await screen.findByRole('link', { name: 'Sign in again' });
    const target = new URL(again.getAttribute('href') ?? '');
    expect(target.searchParams.get('reauth')).toBe('1');
    expect(target.searchParams.get('returnTo')).toBe('/users?tab=access');
    expect(recoveries()).toHaveLength(1);
  });

  it('offers no sign-in link for an ordinary refusal', async () => {
    vi.mocked(serviceCall).mockImplementation((async (_: string, request: { path: string }) => {
      if (request.path.endsWith('/password-recovery')) {
        throw { status: 403, code: 'permission_denied', message: 'This user holds authority you do not.' };
      }
      return request.path === '/v1/users/' + userId ? userRecord : page([]);
    }) as never);
    const { user, dialog } = await open();
    await user.type(dialog.getByLabelText('Reason'), 'Locked out');
    await user.click(dialog.getByRole('button', { name: 'Create recovery link' }));
    expect(await screen.findByText(/holds authority you do not/)).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Sign in again' })).not.toBeInTheDocument();
  });

  it('does not send twice when the button is pressed twice', async () => {
    let release: (value: unknown) => void = () => undefined;
    serve(() => new Promise((resolve) => { release = resolve; }));
    const { user, dialog } = await open();
    await user.type(dialog.getByLabelText('Reason'), 'Locked out');
    const confirm = dialog.getByRole('button', { name: 'Create recovery link' });
    await user.click(confirm);
    await user.click(confirm);
    expect(recoveries()).toHaveLength(1);
    release(receipt());
    await screen.findByRole('textbox', { name: 'Password recovery link' });
  });

  it('removes the link when it expires', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      serve(() => receipt({ expires_at: new Date(Date.now() + 5000).toISOString() }));
      const { user, dialog } = await open();
      await user.type(dialog.getByLabelText('Reason'), 'Locked out');
      await user.click(dialog.getByRole('button', { name: 'Create recovery link' }));
      await screen.findByRole('textbox', { name: 'Password recovery link' });
      await vi.advanceTimersByTimeAsync(6000);
      await waitFor(() =>
        expect(screen.queryByRole('textbox', { name: 'Password recovery link' })).not.toBeInTheDocument(),
      );
      expect(screen.getByText(/has expired/)).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });
});
