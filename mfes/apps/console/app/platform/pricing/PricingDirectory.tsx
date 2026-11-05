'use client';

import { useEffect, useState } from 'react';
import { Badge, Button, Card, CardHeader, DataTable, FilterBar, Notice, PageHeader, PageNavigation, Pager, Select, useListQuery, type Column } from '@janso/ui';
import { platformCall, platformFailure, PlatformError, type PlatformFailure } from '../../lib/platform-api';
import { categories, usePricingMoney, type PriceItem, type PricePage } from './pricing-types';
import { PricingEditor } from './PricingEditor';

export function PricingDirectory({ scope }: { scope: string }) {
  const [data, setData] = useState<PricePage>({ items: [], page: { has_more: false, next_cursor: null } });
  const [loading, setLoading] = useState(true), [reload, setReload] = useState(0);
  const [error, setError] = useState<PlatformFailure | null>(null), [editor, setEditor] = useState<string | null>(null);
  const [message, setMessage] = useState('');
  const [loadedLimit, setLoadedLimit] = useState(50);
  const query = useListQuery({ meta: loading ? null : { ...data.page, limit: loadedLimit } });
  const money = usePricingMoney();
  const category = String(query.filters.category ?? ''), status = String(query.filters.status ?? 'active');
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError(null);
    const params = new URLSearchParams({ limit: String(query.limit), status });
    if (category) params.set('category', category);
    if (query.cursor) params.set('cursor', query.cursor);
    platformCall<PricePage>('/v1/platform/pricing?' + params, 'GET', undefined, undefined, controller.signal)
      .then(value => { if (!controller.signal.aborted) { setData(value); setLoadedLimit(query.limit); setLoading(false); } })
      .catch(value => { if (!controller.signal.aborted) { setError(platformFailure(value)); setLoading(false); } });
    return () => controller.abort();
    // Query callbacks are stable; the fields below are the request identity.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query.limit, query.cursor, category, status, reload]);
  const columns: Column<PriceItem>[] = [
    { key: 'name', header: 'Offering', type: 'custom', render: row => <div><strong>{row.name}</strong><div className="janso-fine">{row.code} · {row.term_months === 1 ? 'Monthly add-on' : `${row.term_months} months, billed upfront`}</div></div> },
    { key: 'monthly_fee', header: 'INR / month', type: 'custom', align: 'end', render: row => money(row.monthly_fee, 'INR') },
    { key: 'usd_monthly_fee', header: 'USD / month', type: 'custom', align: 'end', render: row => money(row.usd_monthly_fee, 'USD') },
    { key: 'usage', header: 'Usage / 1,000', type: 'custom', render: row => row.unit === 'none' ? 'Included platform access' : <div>{money(row.unit_price, 'INR', 4)}<div className="janso-fine">{money(row.usd_unit_price, 'USD', 4)} · {row.unit === 'tokens' ? 'input tokens' : row.unit}</div></div> },
    { key: 'status', header: 'Status', type: 'custom', render: row => <Badge tone={row.deleted_at ? 'danger' : row.is_active ? 'success' : 'neutral'}>{row.deleted_at ? 'Deleted' : row.is_active ? 'Active' : 'Inactive'}</Badge> },
  ];
  const refresh = () => { query.restart(); setReload(value => value + 1); };
  return <div className="janso-page">
    <PageNavigation back={{ href: '/platform', label: 'platform administration' }} breadcrumbs={[{ label: 'Platform administration', href: '/platform' }, { label: 'Fees and pricing' }]} />
    <PageHeader title="Fees and pricing" lede="Subscription plans and optional add-ons, priced in INR and USD." actions={<Button onClick={() => setEditor('new')}>Add offering</Button>} />
    <Notice>Prices exclude tax. Platform subscriptions are billed upfront for the full term. Add-ons are monthly, with usage charged separately and no included allowance. USD prices include a 20% premium over the saved INR conversion.</Notice>
    {message ? <Notice tone="success">{message}</Notice> : null}
    <PlatformError value={error} returnTo="/platform/pricing" />
    <Card><CardHeader title="Pricing catalog" subtitle="Edit an offering to view tax, term totals, model details and price history." />
      <FilterBar applied={[{ id: 'status', label: 'Status', value: status, fixed: true }, ...(category ? [{ id: 'category', label: 'Type', value: categories.find(item => item.value === category)?.label ?? category }] : [])]} onRemove={() => query.setFilter('category', null)} actions={<Button variant="ghost" onClick={refresh} disabled={loading}>Refresh prices</Button>}>
        <Select label="Offering type" value={category} options={[{ value: '', label: 'All types' }, ...categories]} onChange={value => query.setFilter('category', value || null)} />
        <Select label="Status" value={status} options={['active', 'inactive', 'deleted', 'all'].map(value => ({ value, label: value[0].toUpperCase() + value.slice(1) }))} onChange={value => query.setFilter('status', value)} />
      </FilterBar>
      <DataTable caption="Platform pricing catalog" rows={error ? [] : data.items} columns={columns} rowId={row => row.id} rowLabel={row => row.name} loading={loading}
        emptyTitle={error ? 'Prices could not be loaded' : 'No offerings match'} emptyBody={error ? 'Resolve the error above and refresh prices.' : 'Choose another filter or add an offering.'}
        rowActions={() => [{ id: 'edit', label: 'Manage offering' }]} onAction={(_, row) => setEditor(row.id)} />
      <Pager noun="offering" count={data.items.length} from={query.page.from} limit={query.limit} hasPrevious={query.page.hasPrevious} hasNext={!error && query.page.hasNext} onPrevious={query.previousPage} onNext={query.nextPage} onLimitChange={query.setLimit} busy={loading} />
    </Card>
    {editor ? <PricingEditor key={editor} id={editor} scope={scope} onClose={() => setEditor(null)} onSaved={value => { setMessage(value); refresh(); }} /> : null}
  </div>;
}
