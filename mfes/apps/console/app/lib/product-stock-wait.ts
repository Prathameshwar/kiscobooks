import { requestFailure, type RequestFailure } from './service-call';

export type StockWaitReason = 'definitions' | 'confirmation';

export function stockWaitReason(error: unknown): StockWaitReason | null {
  const problem = requestFailure(error);
  if (problem.status !== 409) return null;
  if (problem.message === 'stock posting is using these definitions; retry after it completes') return 'definitions';
  if (problem.message.startsWith('An earlier stock posting is still being confirmed.')) return 'confirmation';
  return null;
}

export async function retryStockWait<T>(request: () => Promise<T>, options: {
  active: () => boolean;
  onWait: (reason: StockWaitReason) => void;
  onResume?: () => void;
  limitMs?: number;
  delayMs?: number;
}): Promise<T> {
  const started = Date.now();
  const limit = options.limitMs ?? 300_000;
  const delay = options.delayMs ?? 2_000;
  let waiting = false;
  try {
    for (;;) {
      if (!options.active()) throw { status: 503, message: 'Product setup was paused.' } satisfies RequestFailure;
      try { return await request(); }
      catch (error) {
        const reason = stockWaitReason(error);
        if (!reason) throw error;
        if (Date.now() - started >= limit) throw {
          status: 503,
          message: 'Your Product request is retained. Stock posting still blocks setup. Retry the same save, or contact support if this continues.',
        } satisfies RequestFailure;
        waiting = true;
        options.onWait(reason);
        await new Promise(resolve => setTimeout(resolve, delay));
      }
    }
  } finally { if (waiting) options.onResume?.(); }
}
