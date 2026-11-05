import { beforeEach, expect, it, vi } from 'vitest';
import { voucherReferenceLabels } from '../app/lib/voucher-reference-labels';

const request = vi.hoisted(() => vi.fn());
vi.mock('../app/lib/product-fields', () => ({ productFieldRequest: request }));
const id = (n: number) => '10000000-0000-7000-8000-' + String(n).padStart(12, '0');
beforeEach(() => { request.mockReset(); });

it('bounds current-label reads to 200 scoped targets and five concurrent requests', async () => {
  let active = 0, peak = 0;
  request.mockImplementation(async (_service, _method, path) => {
    peak = Math.max(peak, ++active);
    await Promise.resolve();
    active--;
    return { id: path.split('/').at(-1), company_id: 'company', name: 'Verified label', row_version: 9 };
  });
  const targets = Array.from({ length: 207 }, (_, n) => ({ resource: 'accounts', id: id(n) }));
  const labels = await voucherReferenceLabels('company', targets, new AbortController().signal);
  expect(request).toHaveBeenCalledTimes(200);
  expect(peak).toBe(5);
  expect(labels.size).toBe(200);
  expect(request.mock.calls.every(call => call[2].startsWith('/v1/companies/company/accounts/'))).toBe(true);
});

it('withholds foreign, mismatched and protected labels and rejects unsupported targets', async () => {
  request.mockImplementation(async (_service, _method, path) => {
    if (path.endsWith(id(1))) return { id: id(1), company_id: 'foreign', name: 'Foreign label' };
    if (path.endsWith(id(2))) return { id: id(3), company_id: 'company', name: 'Mismatched label' };
    throw new Error('403 Protected label');
  });
  const targets = [1, 2, 3].map(n => ({ resource: 'parties', id: id(n) }));
  targets.push({ resource: 'users', id: id(4) }, { resource: 'items', id: '../foreign' });
  const labels = await voucherReferenceLabels('company', targets, new AbortController().signal);
  expect(labels.size).toBe(0);
  expect(request).toHaveBeenCalledTimes(3);
});

it('does not notify or read further batches after the consuming scope is aborted', async () => {
  const controller = new AbortController(), onBatch = vi.fn();
  request.mockImplementation(async () => {
    controller.abort();
    return { id: id(1), company_id: 'company', name: 'Old scope' };
  });
  await voucherReferenceLabels('company', Array.from({ length: 12 }, () => ({ resource: 'accounts', id: id(1) })), controller.signal, onBatch);
  expect(request).toHaveBeenCalledTimes(5);
  expect(onBatch).not.toHaveBeenCalled();
});
