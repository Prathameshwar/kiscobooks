import { randomBytes } from 'node:crypto';
import { expect, it, vi } from 'vitest';
import { coordinateRefresh, type RefreshStore, validLifetime, validToken } from '../../app/lib/refresh-coordinator';

function memoryStore() {
  const entries = new Map<string, string>();
  const store: RefreshStore = {
    get: async (key) => entries.get(key) ?? null,
    lock: async (key, value) => { if (entries.has(key)) return false; entries.set(key, value); return true; },
    publish: async (lock, owner, key, value) => {
      if (entries.get(lock) !== owner) return false;
      entries.set(key, value); entries.delete(lock); return true;
    },
  };
  return { store, entries };
}
const identity = () => ({ secret: randomBytes(32).toString('hex'), issuer: 'https://id.test',
  clientId: 'test-client', refreshToken: randomBytes(32).toString('hex') });

it('coordinates independent instances and response ordering without exposing credentials in Redis', async () => {
  const { store, entries } = memoryStore(), id = identity();
  const result = { accessToken: randomBytes(32).toString('hex'), refreshToken: randomBytes(32).toString('hex'),
    accessTokenExpires: Date.now() + 300_000 };
  const exchange = vi.fn(async () => { await new Promise((resolve) => setTimeout(resolve, 30)); return result; });
  const results = await Promise.all(Array.from({ length: 12 }, () => coordinateRefresh({ ...store }, id, exchange)));
  expect(exchange).toHaveBeenCalledTimes(1);
  expect(results).toEqual(Array(12).fill(result));
  expect(await coordinateRefresh({ ...store }, id, exchange)).toEqual(result);
  const stored = JSON.stringify([...entries]);
  for (const credential of [id.refreshToken, result.accessToken, result.refreshToken]) expect(stored).not.toContain(credential);
});
it('shares invalid_grant failures so losing responses cannot race a second exchange', async () => {
  const { store } = memoryStore(), id = identity();
  const exchange = vi.fn(async () => ({ error: 'invalid' as const }));
  expect(await Promise.all([coordinateRefresh(store, id, exchange), coordinateRefresh(store, id, exchange)]))
    .toEqual([{ error: 'invalid' }, { error: 'invalid' }]);
  expect(exchange).toHaveBeenCalledTimes(1);
});
it('fails closed on unavailable storage and authenticated-cache tampering', async () => {
  const { store, entries } = memoryStore(), id = identity();
  const exchange = vi.fn(async () => ({ error: 'invalid' as const }));
  expect(await coordinateRefresh({ ...store, get: async () => { throw new Error('offline'); } }, id, exchange))
    .toEqual({ error: 'unavailable' });
  expect(exchange).not.toHaveBeenCalled();
  await coordinateRefresh(store, id, exchange);
  for (const key of entries.keys()) entries.set(key, 'tampered');
  expect(await coordinateRefresh(store, id, exchange)).toEqual({ error: 'unavailable' });
  expect(exchange).toHaveBeenCalledTimes(1);
});
it('rejects empty, whitespace, oversized credentials and unbounded expiry', () => {
  for (const value of ['', ' ', 'a b', 'a'.repeat(16_385), null]) expect(validToken(value)).toBe(false);
  for (const value of [Infinity, NaN, 0, 30, 901, '300']) expect(validLifetime(value)).toBe(false);
  expect(validLifetime(300)).toBe(true);
});
