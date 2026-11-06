'use client';

import { useEffect, useId, useRef, useState } from 'react';
import { Button, ClockIcon, Drawer, EmptyState, IconButton, Notice, Tabs, tabButtonId, useFormatters } from '@janso/ui';
import { serviceCall, type ServiceRequest } from '../lib/service-call';
import { readSupplierPurchases, type SupplierPurchaseRow } from '../lib/purchase-supplier-history';
import { readProductPurchase, readProductPurchaseSupplierName, type ProductPurchaseEntry, type ProductPurchaseLine } from '../lib/purchase-product-history';

const read = <T,>(request: ServiceRequest) => serviceCall<T>('/api/product-fields', request, 'Product purchase history');
type Result = { entry?: ProductPurchaseEntry; supplierName?: string; error?: boolean };
type Scope = 'supplier' | 'all';

/** Product history with supplier-scoped and all-supplier tabs; detail reads start only when opened. */
export function PurchaseProductHistory({ company, supplier, product, name, supplierName }: { company: string; supplier: string; product: string; name: string; supplierName?: string }) {
  const format = useFormatters();
  const id = useId(), panelId = `${id}-panel`;
  const [scope, setScope] = useState<Scope>(supplier ? 'supplier' : 'all');
  const [open, setOpen] = useState(false), [rows, setRows] = useState<SupplierPurchaseRow[]>([]);
  const [results, setResults] = useState<Record<string, Result>>({}), [next, setNext] = useState<string | null>(null);
  const [loading, setLoading] = useState(false), [failure, setFailure] = useState('');
  const run = useRef<AbortController | null>(null);
  const names = useRef(new Map<string, Promise<string>>());
  const money = (value: string | null, currency: string | null, precision?: number) => value && currency ? `${format.money(value, { display: 'none', precision })} ${currency}` : '—';
  const close = () => { run.current?.abort(); setOpen(false); };
  const changeScope = (value: string) => {
    const nextScope = value === `${id}-all` ? 'all' : 'supplier';
    if (nextScope === scope) return;
    run.current?.abort(); setRows([]); setResults({}); setNext(null); setFailure(''); setLoading(true); setScope(nextScope);
  };
  const supplierLabel = (supplierId: string, signal: AbortSignal) => {
    if (supplierId === supplier && supplierName?.trim()) return Promise.resolve(supplierName.trim());
    let pending = names.current.get(supplierId);
    if (!pending) {
      pending = readProductPurchaseSupplierName(read, company, supplierId, signal).catch(() => 'Supplier name unavailable');
      names.current.set(supplierId, pending);
    }
    return pending;
  };
  const load = async (cursor?: string) => {
    run.current?.abort();
    if (scope === 'supplier' && !supplier) { setRows([]); setResults({}); setNext(null); setLoading(false); setFailure(''); return; }
    const controller = new AbortController(); run.current = controller;
    if (!cursor) { setRows([]); setResults({}); setNext(null); if (scope === 'all') names.current.clear(); }
    setLoading(true); setFailure('');
    try {
      const page = await readSupplierPurchases(read, company, scope === 'supplier' ? supplier : null, controller.signal, cursor, product);
      if (controller.signal.aborted) return;
      setRows(current => cursor ? [...current, ...page.items] : page.items);
      setNext(page.next);
      let index = 0;
      const worker = async () => {
        while (index < page.items.length && !controller.signal.aborted) {
          const row = page.items[index++];
          try {
            const entry = await readProductPurchase(read, company, scope === 'supplier' ? supplier : null, product, row, controller.signal);
            if (controller.signal.aborted) continue;
            setResults(current => ({ ...current, [row.id]: { entry } }));
            if (scope === 'all') {
              const name = await supplierLabel(entry.supplierId, controller.signal);
              if (!controller.signal.aborted) setResults(current => ({ ...current, [row.id]: { entry, supplierName: name } }));
            }
          } catch {
            if (!controller.signal.aborted) setResults(current => ({ ...current, [row.id]: { error: true } }));
          }
        }
      };
      await Promise.all([worker(), worker()]);
    } catch { if (!controller.signal.aborted) setFailure('Product purchase history is unavailable. Try again.'); }
    finally { if (run.current === controller) { run.current = null; setLoading(false); } }
  };
  useEffect(() => {
    if (open) void load();
    return () => { run.current?.abort(); };
  }, [open, company, supplier, product, scope]);
  const lineFields = (line: ProductPurchaseLine, currency: string) => [
    { label: 'Quantity', value: format.quantity(line.quantity, { precision: 4 }) },
    { label: line.includesTax ? 'Price incl. tax' : 'Price', value: line.price ? money(line.price, currency, 4) : '—', note: line.priceFor ? `per ${format.quantity(line.priceFor, { precision: 4 })} units` : 'per unit' },
    { label: 'Discount', value: money(line.discount, currency) },
    { label: 'Tax', value: money(line.tax, currency), note: line.reverseCharge ? 'Includes reverse charge' : undefined },
    { label: 'Amount', value: money(line.amount, currency) },
  ];
  return <span className="janso-product-purchases__trigger" onKeyDown={event => { if (open) event.stopPropagation(); }}>
    <IconButton size="sm" label={`Purchase history for ${name}`} icon={<ClockIcon size={16} />}
      onClick={() => { names.current.clear(); setScope(supplier ? 'supplier' : 'all'); setLoading(true); setOpen(true); }} aria-haspopup="dialog" aria-expanded={open} />
    <Drawer open={open} title={`${name} · purchase history`} size="lg" onClose={close} footer={<Button variant="ghost" onClick={close}>Close</Button>}>
      <Tabs tabs={[{ id: `${id}-supplier`, label: 'Current supplier' }, { id: `${id}-all`, label: 'All suppliers' }]}
        active={`${id}-${scope}`} onChange={changeScope}
        label="Product purchase history views" panelId={panelId} />
      <div id={panelId} role="tabpanel" aria-labelledby={tabButtonId(`${id}-${scope}`)} className="janso-product-purchases__panel" tabIndex={0}>
      <div className="janso-product-purchases">
        <p className="janso-product-purchases__intro">{scope === 'supplier' ? supplier ? `Purchases from ${supplierName || 'the selected supplier'}, newest invoice first.` : 'Select a supplier on the bill to see their purchases of this product.' : 'Purchases from all suppliers, newest invoice first.'}</p>
        {failure ? <Notice tone="danger" title="History unavailable">{failure}<Button variant="ghost" onClick={() => void load(next ?? undefined)}>Try again</Button></Notice> : null}
        {!rows.length && loading ? <p role="status">Loading product purchases…</p> : null}
        {rows.length ? <ul className="janso-product-purchases__list" aria-label={scope === 'all' ? 'Product purchases from all suppliers' : 'Product purchases from current supplier'}>{rows.map(row => {
          const result = results[row.id], entry = result?.entry;
          return <li key={row.id} className="janso-product-purchases__invoice">
            <div className="janso-product-purchases__invoice-head" data-scope={scope}>
              {scope === 'all' ? <div><small>Supplier</small><strong>{result?.supplierName || (result?.error ? 'Supplier unavailable' : 'Loading supplier…')}</strong></div> : null}
              <div><small>Supplier invoice</small><strong>{row.invoice || 'Number unavailable'}</strong></div>
              <div><small>Invoice date</small><span>{row.date ? format.date(row.date) : 'Date unavailable'}</span></div>
              <span className="janso-product-purchases__status">{row.status.toLowerCase()}</span>
            </div>
            {!result ? <p className="janso-product-purchases__message" role="status">Loading line details…</p> : null}
            {result?.error ? <p className="janso-product-purchases__message">Line details are unavailable for this invoice.</p> : null}
            {entry ? <>
              {entry.lines.map((line, lineIndex) => <div key={line.key} className="janso-product-purchases__line">
                {entry.lines.length > 1 ? <small className="janso-product-purchases__line-number">Product line {lineIndex + 1}</small> : null}
                <dl>{lineFields(line, entry.currency).map(field => <div key={field.label}><dt>{field.label}</dt><dd>{field.value}</dd>{field.note ? <small>{field.note}</small> : null}</div>)}</dl>
              </div>)}
              {!entry.calculationReady ? <p className="janso-product-purchases__message">Saved calculation unavailable; discount, tax and amount cannot be verified.</p> : null}
            </> : null}
          </li>;
        })}</ul> : !loading && !failure ? <EmptyState title={scope === 'supplier' && !supplier ? 'Choose a supplier' : 'No purchases of this product'} body={scope === 'supplier' ? supplier ? 'Purchases from this supplier will appear here when saved.' : 'Select a supplier on the bill, or use All suppliers to review this product now.' : 'Purchases from any supplier will appear here when saved.'} /> : null}
        {next && !failure ? <Button variant="ghost" disabled={loading} onClick={() => void load(next)}>{loading ? 'Loading…' : 'Show more purchases'}</Button> : null}
      </div>
      </div>
    </Drawer>
  </span>;
}
