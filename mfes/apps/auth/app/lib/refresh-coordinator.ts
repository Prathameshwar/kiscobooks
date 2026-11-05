import { createCipheriv, createDecipheriv, createHmac, randomBytes, randomUUID } from 'node:crypto';
import { createClient } from 'redis';

export type RefreshResult = { accessToken: string; refreshToken: string; accessTokenExpires: number } |
  { error: 'invalid' | 'unavailable' };
export type RefreshIdentity = { secret: string; issuer: string; clientId: string; refreshToken: string };
export interface RefreshStore {
  get(key: string): Promise<string | null>;
  lock(key: string, owner: string): Promise<boolean>;
  publish(lock: string, owner: string, key: string, value: string): Promise<boolean>;
}

export function validToken(value: unknown): value is string {
  return typeof value === 'string' && value.length > 0 && value.length <= 16_384 && !/\s/.test(value);
}
export function validLifetime(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value > 30 && value <= 900;
}
const wait = () => new Promise<void>((resolve) => setTimeout(resolve, 50));

// Credential-specific HMAC keys and authenticated encryption keep raw credentials out of Redis.
export async function coordinateRefresh(store: RefreshStore, identity: RefreshIdentity,
  exchange: () => Promise<RefreshResult>): Promise<RefreshResult> {
  const digest = createHmac('sha256', identity.secret)
    .update(JSON.stringify([identity.issuer, identity.clientId, identity.refreshToken])).digest('hex');
  const key = `janso:refresh:{${digest}}:result`, lock = `janso:refresh:{${digest}}:lock`;
  const encryptionKey = createHmac('sha256', identity.secret).update('janso-refresh-cache-v1').digest();
  const seal = (result: RefreshResult) => {
    const iv = randomBytes(12), cipher = createCipheriv('aes-256-gcm', encryptionKey, iv);
    cipher.setAAD(Buffer.from(key));
    const bytes = Buffer.concat([cipher.update(JSON.stringify(result)), cipher.final()]);
    return Buffer.concat([iv, cipher.getAuthTag(), bytes]).toString('base64url');
  };
  const open = (value: string): RefreshResult => {
    const bytes = Buffer.from(value, 'base64url');
    const cipher = createDecipheriv('aes-256-gcm', encryptionKey, bytes.subarray(0, 12));
    cipher.setAAD(Buffer.from(key));
    cipher.setAuthTag(bytes.subarray(12, 28));
    const result = JSON.parse(Buffer.concat([cipher.update(bytes.subarray(28)), cipher.final()]).toString());
    if (result.error === 'invalid' || result.error === 'unavailable') return { error: result.error };
    if (!validToken(result.accessToken) || !validToken(result.refreshToken) ||
        !Number.isFinite(result.accessTokenExpires) || result.accessTokenExpires <= Date.now() + 10_000 ||
        result.accessTokenExpires > Date.now() + 900_000) throw new Error('Invalid cached refresh');
    return { accessToken: result.accessToken, refreshToken: result.refreshToken,
      accessTokenExpires: result.accessTokenExpires };
  };
  const deadline = Date.now() + 10_000;
  try {
    do {
      const cached = await store.get(key);
      if (cached) return open(cached);
      const owner = randomUUID();
      if (await store.lock(lock, owner)) {
        // A previous owner can publish between our GET and SET NX.
        const previous = await store.get(key);
        let result: RefreshResult;
        try { result = previous ? open(previous) : await exchange(); }
        catch { result = { error: 'unavailable' }; }
        if (!await store.publish(lock, owner, key, seal(result))) return { error: 'unavailable' };
        return result;
      }
      await wait();
    } while (Date.now() < deadline);
  } catch { /* A failed coordinator must never exchange the credential without a lock. */ }
  return { error: 'unavailable' };
}

const newClient = (url: string) => createClient({ url, RESP: 2, disableOfflineQueue: true,
  socket: { connectTimeout: 2000, reconnectStrategy: false } });
let client: ReturnType<typeof newClient> | undefined;
let connecting: Promise<unknown> | undefined;
let clientUrl: string | undefined;
export async function coordinatedRefresh(identity: RefreshIdentity,
  exchange: () => Promise<RefreshResult>): Promise<RefreshResult> {
  try {
    const url = process.env.AUTH_REDIS_URL;
    if (!url || !/^rediss?:\/\//.test(url)) return { error: 'unavailable' };
    if (!client || clientUrl !== url || (!client.isOpen && !connecting)) {
      if (client?.isOpen) client.destroy();
      client = newClient(url);
      client.on('error', () => { /* No credential-bearing error is logged. */ });
      clientUrl = url;
      connecting = client.connect().finally(() => { connecting = undefined; });
    }
    if (connecting) await connecting;
    const commands = client.withCommandOptions({ timeout: 1000 });
    return await coordinateRefresh({
      get: (key) => commands.get(key),
      lock: async (key, owner) => (await commands.set(key, owner, { NX: true, PX: 12_000 })) === 'OK',
      publish: async (lock, owner, key, value) => (await commands.eval(
        "if redis.call('GET',KEYS[1]) == ARGV[1] then redis.call('SET',KEYS[2],ARGV[2],'PX',15000); redis.call('DEL',KEYS[1]); return 1 else return 0 end",
        { keys: [lock, key], arguments: [owner, value] })) === 1,
    }, identity, exchange);
  } catch { return { error: 'unavailable' }; }
}
