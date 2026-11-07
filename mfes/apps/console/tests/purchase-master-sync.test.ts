import { expect, it, vi } from 'vitest';
import { purchaseSourcePending, retryPurchaseSource } from '../app/lib/purchase-source-wait';

it('waits for lagging account evidence and uses the original request', async () => {
  const request = vi.fn().mockRejectedValueOnce({status: 409,
    message: 'voucher master evidence is still syncing'}).mockResolvedValue({id: 'purchase'});
  const onWait = vi.fn();
  expect(await retryPurchaseSource(request, {active: () => true, onWait, delayMs: 1}))
    .toEqual({id: 'purchase'});
  expect(request).toHaveBeenCalledTimes(2);
  expect(onWait).toHaveBeenCalledOnce();
});

it('retains the stale-version refusal instead of retrying it', () => {
  expect(purchaseSourcePending({status: 409,
    message: 'voucher master evidence is unavailable or stale'})).toBe(false);
});
