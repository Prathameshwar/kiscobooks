import { requestFailure, type RequestFailure } from './service-call';

const pending = new Set([
  'product base unit evidence is unavailable; synchronize Catalog sources',
  'product unit evidence is unavailable',
  'product unit evidence is incomplete; synchronize Catalog sources',
  'item transaction policy evidence is unavailable',
  'voucher master evidence is still syncing',
]);

/** A newly activated product or account can precede Vouchers' source scan. */
export function purchaseSourcePending(error: unknown): boolean {
  const problem = requestFailure(error);
  return problem.status === 409 && pending.has(problem.message);
}

export async function retryPurchaseSource<T>(request: () => Promise<T>, options: {
  active: () => boolean;
  onWait: () => void;
  onResume?: () => void;
  limitMs?: number;
  delayMs?: number;
}): Promise<T> {
  const started = Date.now();
  let waited = false;
  try {
    for (;;) {
      if (!options.active()) throw { status: 503, message: 'Purchase creation was paused.' } satisfies RequestFailure;
      try { return await request(); }
      catch (error) {
        if (!purchaseSourcePending(error)) throw error;
        if (Date.now() - started >= (options.limitMs ?? 60_000)) throw {
          status: 409,
          message: 'Purchase references are still syncing. Your entries are retained; retry Save in a moment.',
        } satisfies RequestFailure;
        waited = true;
        options.onWait();
        await new Promise(resolve => setTimeout(resolve, options.delayMs ?? 2_000));
      }
    }
  } finally { if (waited) options.onResume?.(); }
}
