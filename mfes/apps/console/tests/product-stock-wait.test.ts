import { expect, it, vi } from 'vitest';
import { retryStockWait, stockWaitReason } from '../app/lib/product-stock-wait';

it('retries only temporary stock blockers and keeps the caller request unchanged', async () => {
  const request = vi.fn()
    .mockRejectedValueOnce({ status: 409, message: 'stock posting is using these definitions; retry after it completes' })
    .mockRejectedValueOnce({ status: 409, message: 'An earlier stock posting is still being confirmed. Retry shortly.' })
    .mockResolvedValue('saved');
  const onWait = vi.fn(), onResume = vi.fn();
  expect(await retryStockWait(request, { active: () => true, onWait, onResume, delayMs: 1 })).toBe('saved');
  expect(request).toHaveBeenCalledTimes(3);
  expect(onWait.mock.calls.map(([reason]) => reason)).toEqual(['definitions', 'confirmation']);
  expect(onResume).toHaveBeenCalledOnce();
});

it('leaves unrelated conflicts for review and bounds a persistent stock wait', async () => {
  expect(stockWaitReason({ status: 409, message: 'product configuration changed' })).toBeNull();
  const unrelated = vi.fn().mockRejectedValue({ status: 409, message: 'product configuration changed' });
  await expect(retryStockWait(unrelated, { active: () => true, onWait: vi.fn(), delayMs: 1 })).rejects.toMatchObject({ message: 'product configuration changed' });
  expect(unrelated).toHaveBeenCalledOnce();
  const held = vi.fn().mockRejectedValue({ status: 409, message: 'stock posting is using these definitions; retry after it completes' });
  await expect(retryStockWait(held, { active: () => true, onWait: vi.fn(), limitMs: 1, delayMs: 2 })).rejects.toMatchObject({ status: 503, message: expect.stringContaining('request is retained') });
  expect(held.mock.calls.length).toBeGreaterThanOrEqual(2);
});
