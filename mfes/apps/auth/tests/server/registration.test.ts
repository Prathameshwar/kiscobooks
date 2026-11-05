import { beforeEach, describe, expect, it, vi } from 'vitest';
import { NextRequest } from 'next/server';
import { GET, POST } from '../../app/api/registration/route';
import { enroll } from '../../app/lib/registration-server';
import { initialWorkspaceName, registrationErrors, parseRegistration } from '../../app/lib/registration-input';
const regionalOptions = { countries: [{ code: 'IN', name: 'India' }, { code: 'US', name: 'United States' }],
  states: [{ code: 'IN-MH', name: 'Maharashtra', country_code: 'IN' }, { code: 'US-CA', name: 'California', country_code: 'US' }] };
const regional = vi.hoisted(() => ({ choices: vi.fn(), invitation: vi.fn() }));
vi.mock('../../app/lib/registration-regions-server', () => ({ registrationChoices: regional.choices, invitationAvailable: regional.invitation }));

const redis = vi.hoisted(() => ({ connect: vi.fn(), destroy: vi.fn(), eval: vi.fn(), on: vi.fn() }));
vi.mock('redis', () => ({ createClient: () => ({ ...redis, isOpen: true,
  withCommandOptions: () => ({ eval: redis.eval }) }) }));
const input = () => ({ name: 'Test Account', username: 'registration-test', email: 'registration@example.invalid',
  password: crypto.randomUUID(), password_repeat: '', country_code: 'IN', state_code: 'IN-MH', workspace_name: 'Test workspace' });
function valid() { const value = input(); value.password_repeat = value.password; return value; }
function request(body: unknown = valid(), headers: Record<string, string> = {}) {
  return new NextRequest('http://localhost:4310/api/registration', { method: 'POST',
    headers: { origin: 'http://localhost:4310', 'Content-Type': 'application/json', ...headers }, body: JSON.stringify(body) });
}
function provider(created = true, overrides = {}) {
  const initial = new Response(JSON.stringify({ component: 'ak-stage-prompt', fields:
    Object.keys(valid()).map(field_key => ({ field_key })) }), { headers: { 'Set-Cookie': 'authentik_session=opaque; HttpOnly' } });
  vi.mocked(fetch).mockResolvedValueOnce(initial).mockResolvedValueOnce(new Response(JSON.stringify(created ? {
    component: 'xak-flow-redirect', final_redirect: true, to: '/if/user/', ...overrides,
  } : { component: 'ak-stage-prompt', response_errors: { username: [{ string: 'secret provider detail', code: 'unique' }] } })));
}
beforeEach(() => {
  vi.stubEnv('AUTH_PROVIDER', 'authentik'); vi.stubEnv('AUTH_REGISTRATION_MODE', 'manual-review'); vi.stubEnv('NEXTAUTH_URL', 'http://localhost:4310');
  vi.stubEnv('AUTH_REGISTRATION_WORKSPACE_ENABLED', 'true');
  vi.stubEnv('AUTHENTIK_ISSUER', 'https://localhost:9443/application/o/janso-local/');
  vi.stubEnv('AUTH_REDIS_URL', 'redis://localhost:6379');
  vi.stubGlobal('fetch', vi.fn()); redis.eval.mockResolvedValue(1); redis.connect.mockResolvedValue(undefined);
  regional.choices.mockReset().mockResolvedValue(regionalOptions);
  regional.invitation.mockReset().mockResolvedValue(true);
});
describe('public registration API', () => {
  it('keeps the seven-field live enrollment usable until its provider blueprint is upgraded', async () => {
    vi.stubEnv('AUTH_REGISTRATION_WORKSPACE_ENABLED', 'false');
    expect((await (await GET()).json()).workspace_enabled).toBe(false);
    const legacy = Object.fromEntries(Object.entries(valid()).filter(([key]) => key !== 'workspace_name'));
    vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify({ component: 'ak-stage-prompt', fields: Object.keys(legacy).map(field_key => ({ field_key })) }), { headers: { 'Set-Cookie': 'authentik_session=opaque' } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ component: 'xak-flow-redirect', final_redirect: true, to: '/if/user/' })));
    expect((await POST(request(legacy))).status).toBe(201);
    expect(JSON.parse(vi.mocked(fetch).mock.calls[1][1]?.body as string)).not.toHaveProperty('workspace_name');
  });
  it('publishes only availability and disables safely when not configured', async () => {
    expect(await (await GET()).json()).toEqual({ enabled: true, mode: 'manual-review', workspace_enabled: true, options: regionalOptions });
    vi.stubEnv('AUTH_REGISTRATION_MODE', '');
    expect(await (await GET()).json()).toEqual({ enabled: false });
    expect((await POST(request())).status).toBe(503);
    expect(fetch).not.toHaveBeenCalled();
  });
  it.each(['US-CA', '', 'IN-XX'])('rejects invalid country/state membership before enrollment (%s)', async state_code => {
    const response = await POST(request({ ...valid(), state_code }));
    expect(response.status).toBe(422);
    expect((await response.json()).fields.state_code).toBe('Choose an available state for this country.');
    expect(fetch).not.toHaveBeenCalled();
  });
  it('rejects withdrawn countries and blocks safely when the database is unavailable', async () => {
    regional.choices.mockResolvedValueOnce({ countries: [{ code: 'US', name: 'United States' }], states: [] });
    expect((await POST(request())).status).toBe(422);
    regional.choices.mockRejectedValueOnce(new Error('private database credentials'));
    const result = await POST(request()); expect(result.status).toBe(503);
    expect(await result.text()).not.toContain('credentials'); expect(fetch).not.toHaveBeenCalled();
    regional.choices.mockRejectedValueOnce(new Error('database unavailable'));
    expect((await GET()).status).toBe(503);
  });
  it.each<Record<string, string>>([{ origin: 'https://attacker.invalid' }, { origin: '' }, { 'sec-fetch-site': 'cross-site' }])('rejects cross-origin creation %j', async headers => {
    expect((await POST(request(valid(), headers))).status).toBe(403); expect(fetch).not.toHaveBeenCalled();
  });
  it('rejects non-JSON and bounded oversized requests', async () => {
    expect((await POST(request(valid(), { 'Content-Type': 'text/plain' }))).status).toBe(415);
    expect((await POST(request(valid(), { 'Content-Length': '9000' }))).status).toBe(413);
    expect((await POST(request({ name: 'x'.repeat(9000) }))).status).toBe(400);
  });
  it('rejects mass assignment before contacting the provider', async () => {
    expect((await POST(request({ ...valid(), attributes: { billing_email_verified: true }, is_active: true }))).status).toBe(422);
    expect(fetch).not.toHaveBeenCalled();
  });
  it('derives a workspace from email while invitation signup joins the existing tenant', async () => {
    const empty = { ...valid(), workspace_name: '' };
    provider();
    expect((await POST(request(empty))).status).toBe(201);
    expect(JSON.parse(vi.mocked(fetch).mock.calls[1][1]?.body as string).workspace_name).toBe('Registration Workspace');
    vi.mocked(fetch).mockReset();
    expect(regional.invitation).not.toHaveBeenCalled();
    const tenant = '01900000-0000-7000-8000-000000000001';
    const invitation_id = '01900000-0000-7000-8000-000000000002';
    regional.invitation.mockResolvedValueOnce(false);
    expect((await POST(request({ ...empty, invitation_tenant: tenant, invitation_id }))).status).toBe(422);
    expect(fetch).not.toHaveBeenCalled();
    provider();
    expect((await POST(request({ ...empty, invitation_tenant: tenant, invitation_id }))).status).toBe(201);
    expect(regional.invitation).toHaveBeenCalledWith(tenant, invitation_id, empty.email);
    expect(JSON.parse(vi.mocked(fetch).mock.calls[1][1]?.body as string)).not.toHaveProperty('invitation_id');
  });
  it('validates fields on the server and never includes credentials in errors', async () => {
    const value = valid(); value.username = 'admin/role'; value.email = 'invalid'; value.password_repeat = 'mismatch';
    const result = await POST(request(value)); expect(result.status).toBe(422);
    const body = await result.json(); expect(body.fields).toHaveProperty('username'); expect(body.fields).toHaveProperty('email');
    expect(body.fields).toHaveProperty('password_repeat'); expect(JSON.stringify(body)).not.toContain(value.password);
    expect(fetch).not.toHaveBeenCalled();
  });
  it.each([5, 6, 128, 129])('checks password length %i before enrollment', async length => {
    const value = valid(); value.password = crypto.randomUUID().repeat(4).slice(0, length); value.password_repeat = value.password;
    if (length >= 6 && length <= 128) provider();
    const result = await POST(request(value));
    expect(result.status).toBe(length >= 6 && length <= 128 ? 201 : 422);
    if (result.status === 201) expect(JSON.parse(vi.mocked(fetch).mock.calls[1][1]?.body as string).password).toBe(value.password);
    else expect(fetch).not.toHaveBeenCalled();
  });
  it('fails closed for Redis errors and rate limits all workers with a retry hint', async () => {
    redis.eval.mockResolvedValueOnce(21);
    const result = await POST(request()); expect(result.status).toBe(429); expect(result.headers.get('Retry-After')).toBe('60');
    redis.connect.mockRejectedValueOnce(new Error('private URL'));
    const failed = await POST(request()); expect(failed.status).toBe(503); expect(await failed.text()).not.toContain('private URL');
    expect(fetch).not.toHaveBeenCalled();
  });
  it('creates through an anonymous provider session and cannot forward authority', async () => {
    provider(); const result = await POST(request(valid(), { Cookie: 'authentik_session=admin', Authorization: 'Bearer private' }));
    expect(result.status).toBe(201); expect(await result.json()).toEqual({ created: true, status: 'pending-review' });
    expect(result.headers.get('Cache-Control')).toBe('no-store');
    const [url, options] = vi.mocked(fetch).mock.calls[1];
    expect(String(url)).toContain('/api/v3/flows/executor/bill-account-enrollment/');
    expect(options?.headers).toMatchObject({ Cookie: 'authentik_session=opaque' });
    expect(options?.headers).not.toHaveProperty('Authorization');
    expect(JSON.parse(options?.body as string)).not.toHaveProperty('attributes');
    expect(JSON.parse(options?.body as string).workspace_name).toBe('Registration Workspace');
  });
  it('uses a safe bounded name without requiring or trusting a caller workspace name', async () => {
    const account = Object.fromEntries(Object.entries(valid()).filter(([key]) => key !== 'workspace_name'));
    provider(); expect((await POST(request(account))).status).toBe(201);
    expect(JSON.parse(vi.mocked(fetch).mock.calls[1][1]?.body as string).workspace_name).toBe('Registration Workspace');
    expect(initialWorkspaceName('acme.books+test@example.invalid')).toBe('Acme Books Workspace');
    expect(initialWorkspaceName('+++@example.invalid')).toBe('My Workspace');
    expect(initialWorkspaceName('a'.repeat(254)+'@example.invalid').length).toBeLessThanOrEqual(200);
  });
  it('sanitizes duplicate-account errors', async () => {
    provider(false); const result = await POST(request()); expect(result.status).toBe(422);
    const body = await result.json(); expect(body.fields.username).toContain('another username');
    expect(JSON.stringify(body)).not.toContain('secret provider detail');
  });
  it('follows only the exact executor redirect using GET and updated anonymous cookies', async () => {
    vi.mocked(fetch).mockReset();
    const endpoint = 'https://localhost:9443/api/v3/flows/executor/bill-account-enrollment/?query=next%3D%252Fif%252Fuser%252F';
    vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify({ component: 'ak-stage-prompt', fields: Object.keys(valid()).map(field_key => ({ field_key })) }), { headers: { 'Set-Cookie': 'authentik_session=initial' } }))
      .mockResolvedValueOnce(new Response(null, { status: 302, headers: { Location: endpoint, 'Set-Cookie': 'authentik_session=updated' } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ component: 'xak-flow-redirect', final_redirect: true, to: '/if/user/' })));
    expect((await POST(request())).status).toBe(201);
    const options = vi.mocked(fetch).mock.calls[2][1];
    expect(options?.method).toBeUndefined(); expect(options?.body).toBeUndefined();
    expect(options?.headers).toMatchObject({ Cookie: 'authentik_session=updated' });
  });
  it('does not follow an unexpected HTTP redirect', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify({ component: 'ak-stage-prompt', fields: Object.keys(valid()).map(field_key => ({ field_key })) }), { headers: { 'Set-Cookie': 'authentik_session=opaque' } }))
      .mockResolvedValueOnce(new Response(null, { status: 302, headers: { Location: 'https://attacker.invalid/' } }));
    expect((await POST(request())).status).toBe(503); expect(fetch).toHaveBeenCalledTimes(2);
  });
  it('completes skipped handoff redirects with GET and refuses an executor loop',async()=>{
    const endpoint='https://localhost:9443/api/v3/flows/executor/bill-account-enrollment/?query=next%3D%252Fif%252Fuser%252F';
    vi.mocked(fetch).mockReset();
    vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify({component:'ak-stage-prompt',fields:Object.keys(valid()).map(field_key=>({field_key}))}),{headers:{'Set-Cookie':'authentik_session=initial'}}));
    for(let count=0;count<2;count++)vi.mocked(fetch).mockResolvedValueOnce(new Response(null,{status:302,headers:{Location:endpoint}}));
    vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify({component:'xak-flow-redirect',final_redirect:true,to:'/if/user/'})));
    expect((await POST(request())).status).toBe(201);
    expect(vi.mocked(fetch).mock.calls.slice(2).every(([,options])=>!options?.method && !options?.body)).toBe(true);
    vi.mocked(fetch).mockReset();
    vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify({component:'ak-stage-prompt',fields:Object.keys(valid()).map(field_key=>({field_key}))}),{headers:{'Set-Cookie':'authentik_session=initial'}}));
    vi.mocked(fetch).mockImplementation(async()=>new Response(null,{status:302,headers:{Location:endpoint}}));
    expect((await POST(request())).status).toBe(503);expect(fetch).toHaveBeenCalledTimes(7);
  });
  it('never treats unexpected flow stages or off-site redirects as success', async () => {
    provider(true, { to: 'https://attacker.invalid' }); expect((await POST(request())).status).toBe(503);
    provider(true, { final_redirect: false }); expect((await POST(request())).status).toBe(503);
    vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify({ component: 'ak-stage-prompt', fields: [] })));
    await expect(enroll(valid())).rejects.toThrow('Unexpected enrollment flow');
  });
  it('handles provider outages without exposing infrastructure errors', async () => {
    vi.mocked(fetch).mockRejectedValueOnce(new Error('TLS internal host password'));
    const result = await POST(request()); expect(result.status).toBe(503); expect(await result.text()).not.toContain('internal host');
  });
});
describe('registration input', () => {
  it.each([5, 6, 128, 129])('enforces the 6–128 boundary at %i Unicode characters', length => {
    for (const character of ['a', '😀']) {
      const value = valid(); value.password = character.repeat(length); value.password_repeat = value.password;
      expect(Boolean(registrationErrors(value).password)).toBe(length < 6 || length > 128);
    }
  });
  it('normalizes identifiers but leaves the password intact', () => {
    const value = valid(); value.username = ' Test.User '; value.email = ' Person@Example.Invalid ';
    expect(parseRegistration(value)).toMatchObject({ username: 'test.user', email: 'person@example.invalid', password: value.password });
    expect(parseRegistration([])).toBeNull(); expect(parseRegistration({ ...value, name: 1 })).toBeNull();
  });
  it('accepts Unicode names and long passphrases, rejects controls and oversized credentials', () => {
    const value = valid(); value.name = 'श्री कुमार'; expect(registrationErrors(value)).toEqual({});
    value.password = '😀'.repeat(12); value.password_repeat = value.password; expect(registrationErrors(value)).toEqual({});
    value.password = 'a'.repeat(129); expect(registrationErrors(value)).toHaveProperty('password');
    value.name = 'name\n'; expect(registrationErrors(value)).toHaveProperty('name');
  });
});
