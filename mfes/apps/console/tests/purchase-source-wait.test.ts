import { expect, it, vi } from 'vitest';
import { retryPurchaseSource, purchaseSourcePending } from '../app/lib/purchase-source-wait';

it('waits for fresh Catalog evidence and replays the same Purchase command', async () => {
  const request = vi.fn()
    .mockRejectedValueOnce({ status: 409, message: 'product unit evidence is unavailable' })
    .mockRejectedValueOnce({ status: 409, message: 'item transaction policy evidence is unavailable' })
    .mockResolvedValue({ id: 'saved' });
  const onWait = vi.fn();
  expect(await retryPurchaseSource(request, { active: () => true, onWait, delayMs: 1 })).toEqual({ id: 'saved' });
  expect(request).toHaveBeenCalledTimes(3);
  expect(onWait).toHaveBeenCalledTimes(2);
});

it('does not retry stale versions or unrelated Purchase conflicts', async () => {
  const stale = { status: 409, message: 'item transaction policy is stale' };
  expect(purchaseSourcePending(stale)).toBe(false);
  const request = vi.fn().mockRejectedValue(stale);
  await expect(retryPurchaseSource(request, { active: () => true, onWait: vi.fn(), delayMs: 1 })).rejects.toEqual(stale);
  expect(request).toHaveBeenCalledTimes(1);
});

it('stops after its bound and asks for a later retry', async () => {
  const request = vi.fn().mockRejectedValue({ status: 409, message: 'product base unit evidence is unavailable; synchronize Catalog sources' });
  await expect(retryPurchaseSource(request, { active: () => true, onWait: vi.fn(), limitMs: 1, delayMs: 2 })).rejects.toMatchObject({ status: 409, message: expect.stringContaining('still syncing') });
});
