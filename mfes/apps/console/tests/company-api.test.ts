/**
 * `openCompany` — the one path that changes company context — and `setDefaultCompany`.
 *
 * The first exists so the rule that matters is stated once: a company answering
 * `step_up_required` is not a failure to show, it is a company that wants a fresh sign-in, and
 * auth owns that flow. Both the rail's switcher and the directory call this, so this is where
 * that branch is proved.
 */
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { companyCall, openCompany, setDefaultCompany } from '../app/lib/company-api';
import { goTo, reload } from '../app/lib/navigate';
import { sessionFetch } from '../app/lib/session-fetch';

vi.mock('../app/lib/session-fetch', () => ({ sessionFetch: vi.fn() }));
vi.mock('../app/lib/navigate', () => ({
  goTo: vi.fn(),
  reload: vi.fn(),
  stepUpUrl: (company: string) => 'http://auth.test/step-up?company=' + company,
}));

const COMPANY = '01990000-0000-7000-8000-000000000001';
const YEAR = '01990000-0000-7000-8000-00000000000a';

beforeEach(() => vi.clearAllMocks());
afterEach(() => { vi.resetAllMocks(); vi.useRealTimers(); });

it('waits for a verified Catalog source after company creation using the same idempotency key', async () => {
  vi.useFakeTimers();
  vi.mocked(sessionFetch)
    .mockResolvedValueOnce(Response.json({ error: { code: 'source_unavailable', message: 'Synchronizing' } }, { status: 503 }))
    .mockResolvedValueOnce(Response.json({ error: { code: 'source_unavailable', message: 'Synchronizing' } }, { status: 503 }))
    .mockResolvedValue(Response.json({ company_id: COMPANY, status: 'READY' }));
  const result = companyCall('catalog', `/v1/companies/${COMPANY}/tax-defaults/bootstrap`, { method: 'POST', body: {}, key: 'tax-init' });
  const checked = expect(result).resolves.toMatchObject({ status: 'READY' });
  await vi.advanceTimersByTimeAsync(2000);
  await checked;
  expect(sessionFetch).toHaveBeenCalledTimes(3);
  expect(new Set(vi.mocked(sessionFetch).mock.calls.map(([, request]) => request?.body)).size).toBe(1);
});

it.each([
  ['identity', 'POST', 'source_unavailable', 503, 'key'],
  ['catalog', 'POST', 'source_unavailable', 503, undefined],
  ['catalog', 'POST', 'permission_denied', 403, 'key'],
  ['catalog', 'POST', 'unavailable', 503, 'key'],
])('does not retry unsafe or unrelated failures: %s %s %s', async (service, method, code, status, key) => {
  vi.mocked(sessionFetch).mockResolvedValue(Response.json({ error: { code, message: 'Failed' } }, { status }));
  await expect(companyCall(service as 'catalog' | 'identity', '/v1/companies', { method, key })).rejects.toMatchObject({ status });
  expect(sessionFetch).toHaveBeenCalledTimes(1);
});

it('bounds source synchronization waits and retains the failure for a manual retry', async () => {
  vi.useFakeTimers();
  vi.mocked(sessionFetch).mockImplementation(async () => Response.json({ error: {
    code: 'source_unavailable', message: 'Still synchronizing',
  } }, { status: 503 }));
  const checked = expect(companyCall('catalog', '/v1/companies/' + COMPANY + '/tax-defaults/bootstrap',
    { method: 'POST', body: {}, key: 'tax-init' })).rejects.toMatchObject({ code: 'source_unavailable' });
  await vi.advanceTimersByTimeAsync(30000);
  await checked;
  expect(sessionFetch).toHaveBeenCalledTimes(30);
});

it('freezes the submitted body while awaiting source synchronization', async () => {
  vi.useFakeTimers();
  vi.mocked(sessionFetch)
    .mockResolvedValueOnce(Response.json({ error: { code: 'source_unavailable' } }, { status: 503 }))
    .mockResolvedValue(Response.json({ status: 'READY' }));
  const body = { values: { name: 'Original' } };
  const checked = expect(companyCall('catalog', '/v1/companies/' + COMPANY + '/item-groups',
    { method: 'POST', body, key: 'original-key' })).resolves.toMatchObject({ status: 'READY' });
  body.values.name = 'Changed';
  await vi.advanceTimersByTimeAsync(1000);
  await checked;
  expect(vi.mocked(sessionFetch).mock.calls[1][1]?.body).toBe(vi.mocked(sessionFetch).mock.calls[0][1]?.body);
});

it('records the selection and re-renders the page against it', async () => {
  vi.mocked(sessionFetch).mockResolvedValue(Response.json({ company: COMPANY, fiscalYear: YEAR }));

  expect(await openCompany(COMPANY, YEAR)).toBeNull();
  expect(sessionFetch).toHaveBeenCalledWith(
    '/api/company-context',
    expect.objectContaining({ method: 'POST', body: JSON.stringify({ company: COMPANY, fiscalYear: YEAR }) }),
  );
  expect(reload).toHaveBeenCalledTimes(1);
});

it('leaves cookies untouched when an editor blocks the company or year change', async () => {
  const block = (event: Event) => event.preventDefault();
  window.addEventListener('janso:before-company-change', block);
  try {
    expect(await openCompany(COMPANY, YEAR)).toMatchObject({ status: 409, message: expect.stringMatching(/unsaved changes/i) });
    expect(sessionFetch).not.toHaveBeenCalled();
    expect(reload).not.toHaveBeenCalled();
  } finally { window.removeEventListener('janso:before-company-change', block); }
});

it('omits a year that was not chosen rather than sending null', async () => {
  vi.mocked(sessionFetch).mockResolvedValue(Response.json({ company: COMPANY }));

  await openCompany(COMPANY);
  expect(vi.mocked(sessionFetch).mock.calls[0][1]?.body).toBe(JSON.stringify({ company: COMPANY }));
});

it.each(['company', 'companies'] as const)('leaves setup for the selected %s page after saving company context', async destination => {
  vi.mocked(sessionFetch).mockResolvedValue(Response.json({ company: COMPANY }));
  expect(await openCompany(COMPANY, undefined, destination)).toBeNull();
  expect(goTo).toHaveBeenCalledWith(destination === 'company' ? '/companies/' + COMPANY : '/companies');
  expect(reload).not.toHaveBeenCalled();
});

it('keeps the Auth step-up navigation when company setup needs verification', async () => {
  vi.mocked(sessionFetch).mockResolvedValue(Response.json({ error: { code: 'step_up_required' } }, { status: 403 }));
  expect(await openCompany(COMPANY, undefined, 'company')).toBeNull();
  expect(goTo).toHaveBeenCalledOnce();
  expect(goTo).toHaveBeenCalledWith('http://auth.test/step-up?company=' + COMPANY);
});

it('sends a company that wants verification to auth, and reports no failure', async () => {
  vi.mocked(sessionFetch).mockResolvedValue(Response.json({ error: { code: 'step_up_required', message: 'Verify' } }, { status: 403 }));

  expect(await openCompany(COMPANY)).toBeNull();
  expect(goTo).toHaveBeenCalledWith('http://auth.test/step-up?company=' + COMPANY);
  expect(reload).not.toHaveBeenCalled();
});

it('returns any other refusal for the caller to render, and does not navigate', async () => {
  vi.mocked(sessionFetch).mockResolvedValue(Response.json({ error: { message: 'This company is unavailable.' } }, { status: 403 }));

  expect(await openCompany(COMPANY)).toEqual({ status: 403, code: undefined, message: 'This company is unavailable.' });
  expect(goTo).not.toHaveBeenCalled();
  expect(reload).not.toHaveBeenCalled();
});
it('serializes company changes from different entry points while a selection is pending', async () => {
  let resolve!: (response: Response) => void;
  vi.mocked(sessionFetch).mockReturnValue(new Promise(done => { resolve = done; }));
  const first = openCompany(COMPANY);
  const second = await openCompany(YEAR);
  expect(second).toMatchObject({ status: 409 }); expect(sessionFetch).toHaveBeenCalledOnce();
  resolve(Response.json({ company: COMPANY })); await first;
});

it('names a refusal that carried no message, rather than failing silently', async () => {
  vi.mocked(sessionFetch).mockResolvedValue(new Response('', { status: 500 }));

  expect(await openCompany(COMPANY)).toMatchObject({ status: 500, message: 'Unable to open this company. Try again.' });
});

it('reports an unreachable console route as an outage', async () => {
  vi.mocked(sessionFetch).mockRejectedValue(new TypeError('offline'));

  expect(await openCompany(COMPANY)).toEqual({ status: 503, message: 'The company service is unavailable. Try again.' });
  expect(reload).not.toHaveBeenCalled();
});

it('stores the default company as a self-write, with no idempotency key to replay', async () => {
  vi.mocked(sessionFetch).mockResolvedValue(Response.json({ id: 'u1', default_company_id: COMPANY }));

  await setDefaultCompany(COMPANY);
  const [endpoint, init] = vi.mocked(sessionFetch).mock.calls[0];
  expect(endpoint).toBe('/api/company');
  expect(JSON.parse(String(init?.body))).toEqual({
    service: 'identity',
    path: '/v1/session/preferences',
    method: 'PATCH',
    body: { default_company_id: COMPANY },
  });
  // A preference is not a money write: there is no key, so the client does not replay it after
  // a token refresh (`lib/service-call`).
  expect(JSON.parse(String(init?.body))).not.toHaveProperty('key');
  // Storing a default changes where the *next* session lands, not this page.
  expect(reload).not.toHaveBeenCalled();
});

it('throws a refused default for the caller to render', async () => {
  vi.mocked(sessionFetch).mockResolvedValue(
    Response.json({ error: { code: 'validation_failed', message: 'Choose a company you can open.' } }, { status: 422 }),
  );

  await expect(setDefaultCompany(COMPANY)).rejects.toMatchObject({ status: 422, message: 'Choose a company you can open.' });
});
