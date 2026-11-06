'use client';

import { useEffect, useState } from 'react';
import { businessToday, useDisplayConfig, useFormatters } from '@janso/ui';
import { serviceCall, type ServiceRequest } from '../lib/service-call';
import { balanceDate } from '../lib/purchase-supplier-balance';
import { readPurchaseSelectionBalance, type SelectionBalance } from '../lib/purchase-selection-balance';

/** Only the active purchase line mounts this hint, so a saved bill never fans out into stock or ledger reads. */
export function PurchaseSelectionBalance({ company, kind, subject, postingDate, currency, warehouse, permitted, unit }: {
  company: string; kind: 'ACCOUNT' | 'ITEM'; subject: string; postingDate: string;
  currency: string; warehouse?: string; permitted: boolean; unit?: string;
}) {
  const { money, quantity, date } = useFormatters();
  const display = useDisplayConfig();
  const [state, setState] = useState<{ key: string; result?: SelectionBalance; status: 'loading' | 'unavailable' | 'ready' } | null>(null);
  const asOf = balanceDate(postingDate, businessToday(display.timezone));
  const key = [company, kind, subject, kind === 'ACCOUNT' ? asOf : '', currency, warehouse ?? ''].join(':');
  useEffect(() => {
    if (!subject || !permitted) { setState(null); return; }
    const controller = new AbortController();
    setState({ key, status: 'loading' });
    const timer = setTimeout(() => { controller.abort(); setState({ key, status: 'unavailable' }); }, 15_000);
    void readPurchaseSelectionBalance(<T,>(request: ServiceRequest) => serviceCall<T>('/api/product-fields', request, 'Purchase balance'),
      { company, kind, subject, asOf, currency, warehouse, signal: controller.signal })
      .then(result => { if (!controller.signal.aborted) setState({ key, result, status: 'ready' }); })
      .catch(() => { if (!controller.signal.aborted) setState({ key, status: 'unavailable' }); })
      .finally(() => clearTimeout(timer));
    return () => { clearTimeout(timer); controller.abort(); };
  }, [key, permitted]);
  if (!subject || !permitted) return null;
  const current = state?.key === key ? state : { status: 'loading' as const };
  return <span className="janso-purchase-line-balance" role="status" aria-live="polite" data-purchase-line-balance={current.status}>
    {current.status === 'loading' ? 'Checking balance…' : current.status === 'unavailable' ? 'Balance unavailable' : current.result?.kind === 'ACCOUNT'
      ? <>Account balance {money(current.result.amount)} {current.result.side === 'NIL' ? 'settled' : current.result.side === 'DR' ? 'Dr' : 'Cr'} · as of {date(current.result.asOf)}</>
      : current.result?.kind === 'ITEM' ? <>Current {current.result.warehouse ? 'warehouse' : 'in-warehouse'} stock {quantity(current.result.quantity)} {unit}</> : null}
  </span>;
}
