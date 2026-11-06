'use client';

import { useEffect, useState } from 'react';
import { useFormatters } from '@janso/ui';
import { purchaseBatch, type PurchaseBatch } from '../lib/purchase-stock';

/** Read the chosen batch from Accounting so saved lines show its code and expiry. */
export function PurchaseBatchSummary({ company, item, batchId, permitted }: { company: string; item: string; batchId: string; permitted: boolean }) {
  const { date } = useFormatters();
  const [batch, setBatch] = useState<PurchaseBatch | null>(null);
  const [failure, setFailure] = useState(false);
  useEffect(() => {
    const abort = new AbortController();
    setBatch(null); setFailure(false);
    if (!permitted) return () => abort.abort();
    void purchaseBatch(company, item, batchId, abort.signal)
      .then(value => { if (!abort.signal.aborted) setBatch(value); })
      .catch(() => { if (!abort.signal.aborted) setFailure(true); });
    return () => abort.abort();
  }, [company, item, batchId, permitted]);
  if (!permitted) return <span>Batch selected</span>;
  if (failure) return <span className="janso-error">Batch needs verification</span>;
  if (!batch) return <span>Checking batch…</span>;
  return <span>Batch {batch.code || batch.id.slice(-8)}{batch.expires_on ? ` · Expires ${date(batch.expires_on)}` : ''}</span>;
}
