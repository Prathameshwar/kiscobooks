import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NextRequest } from 'next/server';
import { GET, POST } from '../../app/api/registration/route';
import { registrationConfiguration } from '../../app/lib/registration-server';
import { AUTH_URL, BFF_SECRET, IDENTITY, LEAK, envelope, localEnv } from './local-support';

const regionalOptions = { countries: [{ code: 'IN', name: 'India' }, { code: 'US', name: 'United States' }],
  states: [{ code: 'IN-MH', name: 'Maharashtra', country_code: 'IN' }, { code: 'US-CA', name: 'California', country_code: 'US' }] };
const regional = vi.hoisted(() => ({ choices: vi.fn(), invitation: vi.fn() }));
vi.mock('../../app/lib/registration-regions-server', () => ({ registrationChoices: regional.choices, invitationAvailable: regional.invitation }));
const redis = vi.hoisted(() => ({ connect: vi.fn(), destroy: vi.fn(), eval: vi.fn(), on: vi.fn() }));
vi.mock('redis', () => ({ createClient: () => ({ ...redis, isOpen: true, withCommandOptions: () => ({ eval: redis.eval }) }) }));

const account = () => { const password = crypto.randomUUID();
  return { name: 'Test Account', username: 'registration-test', email: 'Registration@Example.Invalid', password, password_repeat: password,
    country_code: 'IN', state_code: 'IN-MH', workspace_name: 'Test workspace' }; };
const request = (body: unknown = account(), headers: Record<string, string> = {}) => new NextRequest(`${AUTH_URL}/api/registration`, {
  method: 'POST', headers: { origin: AUTH_URL, 'content-type': 'application/json', ...headers }, body: JSON.stringify(body) });
let fetcher: ReturnType<typeof vi.fn>;
beforeEach(() => {
  localEnv({ AUTH_REGISTRATION_MODE: 'manual-review', AUTH_REGISTRATION_WORKSPACE_ENABLED: 'true', AUTH_REDIS_URL: 'redis://localhost:6379' });
  fetcher = vi.fn(async () => Response.json({ status: 'pending-review' }, { status: 201 }));
  vi.stubGlobal('fetch', fetcher);
  redis.eval.mockResolvedValue(1); redis.connect.mockResolvedValue(undefined);
  regional.choices.mockReset().mockResolvedValue(regionalOptions);
  regional.invitation.mockReset().mockResolvedValue(true);
});
afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); });

describe('local registration', () => {
  it('needs no Authentik setting and reports username or email sign-in on the availability check', async () => {
    for (const name of ['AUTHENTIK_ISSUER', 'AUTHENTIK_CLIENT_ID']) expect(process.env[name]).toBeUndefined();
    expect(registrationConfiguration()).toMatchObject({ provider: 'local', origin: AUTH_URL, endpoint: null, workspaceEnabled: true });
    expect(await (await GET()).json()).toEqual({ enabled: true, mode: 'manual-review', workspace_enabled: true, options: regionalOptions, sign_in: 'username_or_email' });
  });
  it('stays disabled without the registration mode or the BFF credentials', async () => {
    vi.stubEnv('AUTH_REGISTRATION_MODE', '');
    expect(await (await GET()).json()).toEqual({ enabled: false });
    vi.stubEnv('AUTH_REGISTRATION_MODE', 'manual-review');
    vi.stubEnv('AUTH_LOCAL_BFF_SECRET', '');
    expect(await (await GET()).json()).toEqual({ enabled: false });
    expect((await POST(request())).status).toBe(503);
    expect(fetcher).not.toHaveBeenCalled();
  });
  it('creates the account through Identity and answers pending-review', async () => {
    const value = account();
    const response = await POST(request(value));
    expect(response.status).toBe(201);
    expect(await response.json()).toEqual({ created: true, status: 'pending-review' });
    expect(response.headers.get('cache-control')).toBe('no-store');
    expect(fetcher).toHaveBeenCalledTimes(1);
    const [url, options] = fetcher.mock.calls[0];
    expect(String(url)).toBe(`${IDENTITY}/internal/v1/local-auth/registrations`);
    expect(options).toMatchObject({ method: 'POST', cache: 'no-store', redirect: 'error' });
    expect(options.headers['X-Auth-Bff-Secret']).toBe(BFF_SECRET);
    // Exactly the contract's fields: normalised identifiers, no confirmation field, and the
    // server-derived workspace name (a caller-supplied one is never trusted).

    expect(JSON.parse(options.body)).toEqual({ name: 'Test Account', username: 'registration-test', email: 'registration@example.invalid',
      password: value.password, country_code: 'IN', state_code: 'IN-MH', workspace_name: 'Registration Workspace' });
  });
  it('sends no workspace name when workspaces are disabled, and an empty one when accepting an invitation', async () => {
    vi.stubEnv('AUTH_REGISTRATION_WORKSPACE_ENABLED', 'false');
    const { workspace_name: _ignored, ...plain } = account();
    expect((await POST(request(plain))).status).toBe(201);
    expect(JSON.parse(fetcher.mock.calls[0][1].body)).not.toHaveProperty('workspace_name');
    vi.stubEnv('AUTH_REGISTRATION_WORKSPACE_ENABLED', 'true');
    const invitation = { ...plain, invitation_tenant: '01900000-0000-7000-8000-000000000001', invitation_id: '01900000-0000-7000-8000-000000000002' };
    expect((await POST(request(invitation))).status).toBe(201);
    const sent = JSON.parse(fetcher.mock.calls[1][1].body);
    // Identity reads an empty name as "joins an existing invitation"; an absent one would mean an
    // earlier registration that still needs a workspace name, and review would then refuse to approve it.
    expect(sent.workspace_name).toBe('');
    expect(sent).not.toHaveProperty('invitation_id');
    expect(regional.invitation).toHaveBeenCalledWith(invitation.invitation_tenant, invitation.invitation_id, 'registration@example.invalid');
  });
  it('derives a workspace name from the email when none is given', async () => {
    const { workspace_name: _ignored, ...plain } = account();
    expect((await POST(request(plain))).status).toBe(201);
    expect(JSON.parse(fetcher.mock.calls[0][1].body).workspace_name).toBe('Registration Workspace');
  });
  it('never forwards the caller\'s cookies or authorization', async () => {
    await POST(request(account(), { cookie: 'session=private', authorization: 'Bearer private' }));
    expect(JSON.stringify(fetcher.mock.calls[0][1].headers)).not.toMatch(/private/);
  });

  it('keeps every existing validation, and never reaches Identity when one fails', async () => {
    const value = account();
    expect((await POST(request({ ...value, username: 'admin/role', email: 'invalid', password_repeat: 'mismatch' }))).status).toBe(422);
    expect((await POST(request({ ...value, state_code: 'US-CA' }))).status).toBe(422);
    expect((await POST(request({ ...value, password: 'short', password_repeat: 'short' }))).status).toBe(422);
    expect((await POST(request({ ...value, is_active: true, attributes: { x: 1 } }))).status).toBe(422);
    regional.invitation.mockResolvedValueOnce(false);
    expect((await POST(request({ ...value, invitation_tenant: '01900000-0000-7000-8000-000000000001', invitation_id: '01900000-0000-7000-8000-000000000002' }))).status).toBe(422);
    expect((await POST(request(value, { origin: 'https://evil.test' }))).status).toBe(403);
    expect((await POST(request(value, { 'sec-fetch-site': 'cross-site' }))).status).toBe(403);
    expect((await POST(request(value, { 'content-type': 'text/plain' }))).status).toBe(415);
    expect(fetcher).not.toHaveBeenCalled();
  });
  it('keeps the shared rate limit and fails closed when it is unavailable', async () => {
    redis.eval.mockResolvedValueOnce(21);
    const limited = await POST(request());
    expect(limited.status).toBe(429);
    expect(limited.headers.get('retry-after')).toBe('60');
    redis.connect.mockRejectedValueOnce(new Error('private URL'));
    expect((await POST(request())).status).toBe(503);
    expect(fetcher).not.toHaveBeenCalled();
  });

  describe('Identity refusals', () => {
    it('maps 422 field errors to the same fixed field messages as before', async () => {
      fetcher.mockResolvedValue(Response.json({ error: { code: 'validation_error', message: LEAK },
        fields: { username: LEAK, password: LEAK, email: LEAK, admin: LEAK } }, { status: 422 }));
      const response = await POST(request());
      expect(response.status).toBe(422);
      const text = await response.text();
      const body = JSON.parse(text);
      expect(body.error).toMatch(/cannot be used/);
      expect(body.fields).toEqual({ username: 'Choose another username. This one cannot be used.',
        password: 'Check your password and confirmation.', email: 'Check this account detail.' });
      expect(text).not.toContain(LEAK);
    });
    it('maps 422 registration_unavailable to the generic message without leaking whether an account exists', async () => {
      fetcher.mockResolvedValue(envelope(422, 'registration_unavailable'));
      const response = await POST(request());
      expect(response.status).toBe(422);
      const text = await response.text();
      expect(JSON.parse(text)).toEqual({ error: 'These account details cannot be used. Check the fields or contact your administrator.' });
      expect(text).not.toContain(LEAK);
    });
    it.each([400, 401, 403, 409, 429, 500, 503])('maps %i to the generic unavailable answer', async status => {
      fetcher.mockResolvedValue(envelope(status, 'x'));
      const response = await POST(request());
      expect(response.status).toBe(503);
      expect(await response.text()).not.toContain(LEAK);
    });
    it('treats a 422 it cannot read as unavailable', async () => {
      fetcher.mockResolvedValue(envelope(422, 'something_new'));
      expect((await POST(request())).status).toBe(503);
    });
    it('hides network failures', async () => {
      fetcher.mockRejectedValue(new Error('connect ECONNREFUSED 10.0.0.9'));
      const response = await POST(request());
      expect(response.status).toBe(503);
      expect(await response.text()).not.toContain('10.0.0.9');
    });
  });
});

describe('authentik registration is untouched', () => {
  it('still reports no sign_in hint and still needs its issuer', async () => {
    vi.stubEnv('AUTH_PROVIDER', 'authentik');
    vi.stubEnv('AUTHENTIK_ISSUER', 'https://localhost:9443/application/o/janso-local/');
    expect(await (await GET()).json()).toEqual({ enabled: true, mode: 'manual-review', workspace_enabled: true, options: regionalOptions });
    vi.stubEnv('AUTHENTIK_ISSUER', '');
    expect(await (await GET()).json()).toEqual({ enabled: false });
  });
});
