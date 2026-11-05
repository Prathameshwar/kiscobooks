'use client';

import { useEffect, useState } from 'react';
import type { components } from '@janso/api-client/identity';
import { Button, DataTable, Pager, useListQuery, type Column } from '@janso/ui';
import { platformCall, platformFailure, PlatformError, type PlatformFailure } from '../../lib/platform-api';
import { usePricingMoney } from './pricing-types';

type Revision = components['schemas']['PlatformPriceRevisionItem'];
type RevisionPage = components['schemas']['Page_PlatformPriceRevisionItem_'];
export function PriceRevisions({ id, version }: { id: string; version: number }) {
  const [open, setOpen] = useState(false), [loading, setLoading] = useState(false);
  const [data, setData] = useState<RevisionPage>({ items: [], page: { has_more: false, next_cursor: null } });
  const [error, setError] = useState<PlatformFailure | null>(null), [retry, setRetry] = useState(0);
  const query = useListQuery({ meta: loading ? null : { ...data.page, limit: 50 } }), money = usePricingMoney();
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController(); setLoading(true); setError(null);
    const params = new URLSearchParams({ limit: String(query.limit) }); if (query.cursor) params.set('cursor', query.cursor);
    platformCall<RevisionPage>(`/v1/platform/pricing/${id}/revisions?${params}`, 'GET', undefined, undefined, controller.signal)
      .then(value => { if (!controller.signal.aborted) { setData(value); setLoading(false); } })
      .catch(value => { if (!controller.signal.aborted) { setError(platformFailure(value)); setLoading(false); } });
    return () => controller.abort();
  }, [id, open, version, query.limit, query.cursor, retry]);
  const columns: Column<Revision>[] = [
    { key: 'version', header: 'Version' }, { key: 'created_at', header: 'Saved', type: 'datetime' },
    { key: 'snapshot', header: 'Commercial terms', type: 'custom', render: row => <details><summary>{row.snapshot.name} · {row.snapshot.term_months} months</summary>
      <p className="janso-fine">{row.snapshot.description} · {row.snapshot.is_active ? 'Active' : 'Inactive'}{row.snapshot.deleted_at ? ' · Deleted' : ''} · Tax {row.snapshot.tax_percent}% · FX {row.snapshot.fx_inr_per_usd} INR/USD · {row.snapshot.provider} {row.snapshot.model}</p>
      {row.snapshot.prices.map(price => <p className="janso-fine" key={price.currency}>{money(price.monthly_fee, price.currency)} / month · Term net {money(price.term_net, price.currency)} · Tax {money(price.term_tax, price.currency)} · Total {money(price.term_total, price.currency)}{row.snapshot.unit !== 'none' ? ` · ${money(price.unit_price, price.currency, 4)} / 1,000 ${row.snapshot.unit}` : ''}{row.snapshot.unit === 'tokens' ? ` input; ${money(price.output_unit_price, price.currency, 4)} / 1,000 output tokens` : ''}</p>)}
    </details> },
  ];
  return <section aria-label="Price history"><Button variant="ghost" aria-expanded={open} onClick={() => setOpen(value => !value)}>{open ? 'Hide price history' : 'Show price history'}</Button>
    {open ? <><PlatformError value={error} returnTo="/platform/pricing" />{error ? <Button onClick={() => setRetry(value => value + 1)}>Retry price history</Button> : null}
      <DataTable caption="Price revisions" rows={error ? [] : data.items} columns={columns} rowId={row => row.id} rowLabel={row => `Version ${row.version}`} loading={loading} />
      <Pager noun="revision" count={data.items.length} limit={query.limit} hasPrevious={query.page.hasPrevious} hasNext={!error && query.page.hasNext} onPrevious={query.previousPage} onNext={query.nextPage} busy={loading} />
    </> : null}
  </section>;
}
