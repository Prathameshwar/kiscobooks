'use client';

import { useEffect, useRef, useState } from 'react';
import { Button, ClockIcon, Drawer, EmptyState, IconButton, Notice, useFormatters } from '@janso/ui';
import { serviceCall, type ServiceRequest } from '../lib/service-call';
import { readSupplierPurchaseDetail, readSupplierPurchases, type SupplierPurchaseDetail, type SupplierPurchaseRow } from '../lib/purchase-supplier-history';

const read = <T,>(request: ServiceRequest) => serviceCall<T>('/api/product-fields', request, 'Supplier purchases');

/** A compact entry action with an on-demand, paged read of this supplier's purchase bills. */
export function PurchaseSupplierHistory({ company, supplier, name }: { company: string; supplier: string; name: string }) {
  const format = useFormatters();
  const [open, setOpen] = useState(false), [rows, setRows] = useState<SupplierPurchaseRow[]>([]), [next, setNext] = useState<string | null>(null);
  const [loading, setLoading] = useState(false), [failure, setFailure] = useState('');
  const [selected, setSelected] = useState<SupplierPurchaseRow | null>(null), [detail, setDetail] = useState<SupplierPurchaseDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false), [detailFailure, setDetailFailure] = useState('');
  const listRun = useRef<AbortController | null>(null), detailRun = useRef<AbortController | null>(null);
  const money = (amount: string | null, currency: string | null) => amount && currency ? `${format.money(amount, { display: 'none' })} ${currency}` : 'Amount unavailable';

  const load = async (cursor?: string) => {
    listRun.current?.abort();
    const controller = new AbortController(); listRun.current = controller;
    setLoading(true); setFailure('');
    try {
      const page = await readSupplierPurchases(read, company, supplier, controller.signal, cursor);
      if (!controller.signal.aborted) { setRows(current => cursor ? [...current, ...page.items] : page.items); setNext(page.next); }
    } catch { if (!controller.signal.aborted) setFailure('Purchase history is unavailable. Try again.'); }
    finally { if (listRun.current === controller) { listRun.current = null; setLoading(false); } }
  };
  useEffect(() => {
    if (open) { setRows([]); setNext(null); setSelected(null); setDetail(null); void load(); }
    return () => { listRun.current?.abort(); detailRun.current?.abort(); };
  }, [open, company, supplier]);
  const openBill = async (row: SupplierPurchaseRow) => {
    detailRun.current?.abort();
    const controller = new AbortController(); detailRun.current = controller;
    setSelected(row); setDetail(null); setDetailFailure(''); setDetailLoading(true);
    try {
      const value = await readSupplierPurchaseDetail(read, company, supplier, row.id, controller.signal);
      if (!controller.signal.aborted) setDetail(value);
    } catch { if (!controller.signal.aborted) setDetailFailure('This purchase detail is unavailable. Try again.'); }
    finally { if (detailRun.current === controller) { detailRun.current = null; setDetailLoading(false); } }
  };
  const back = () => { detailRun.current?.abort(); detailRun.current = null; setSelected(null); setDetail(null); setDetailFailure(''); };
  const close = () => { listRun.current?.abort(); detailRun.current?.abort(); setOpen(false); back(); };
  const productLines = detail?.lines.filter(line => line.kind === 'ITEM') ?? [];
  const otherLines = detail?.lines.filter(line => line.kind === 'ACCOUNT') ?? [];
  return <>
    <IconButton size="sm" label={`Purchase history for ${name}`} icon={<ClockIcon size={16} />} onClick={() => setOpen(true)} aria-haspopup="dialog" aria-expanded={open} />
    <Drawer open={open} title={selected ? `Purchase ${selected.invoice || 'invoice'}` : `Purchases from ${name}`} size="lg" onClose={close}
      footer={<Button variant="ghost" onClick={close}>Close</Button>}>
      {selected ? <div className="janso-supplier-purchases">
        <Button variant="ghost" className="janso-supplier-purchases__back" onClick={back}>← All purchases</Button>
        <dl className="janso-supplier-purchases__summary"><div><dt>Supplier invoice</dt><dd>{selected.invoice || 'Number unavailable'}</dd></div><div><dt>Invoice date</dt><dd>{selected.date ? format.date(selected.date) : 'Unavailable'}</dd></div><div><dt>Purchase amount</dt><dd>{money(selected.amount, selected.currency)}</dd></div></dl>
        {detailLoading ? <p role="status">Loading purchase lines…</p> : null}
        {detailFailure ? <Notice tone="danger" title="Purchase detail unavailable">{detailFailure}<Button variant="ghost" onClick={() => void openBill(selected)}>Try again</Button></Notice> : null}
        {detail && <>
          <h3>Products</h3>
          {productLines.length ? <ul className="janso-supplier-purchases__lines">{productLines.map(line => <li key={line.key}><strong>{line.description}</strong><dl><div><dt>Billed qty</dt><dd>{line.quantity ? format.quantity(line.quantity) : 'Unavailable'}</dd></div><div><dt>{line.includesTax ? 'Price incl. tax' : 'Price'}{line.priceFor ? ` per ${format.quantity(line.priceFor)} units` : ' per unit'}</dt><dd>{line.price && selected.currency ? money(line.price, selected.currency) : 'Unavailable'}</dd></div><div><dt>Line amount</dt><dd>{line.amount && selected.currency ? money(line.amount, selected.currency) : 'Unavailable'}</dd></div></dl></li>)}</ul>
            : <p className="janso-entry-workspace__caption">This purchase has no product lines.</p>}
          {otherLines.length ? <><h3>Accounts and services</h3><ul className="janso-supplier-purchases__lines">{otherLines.map(line => <li key={line.key}><strong>{line.description}</strong><span>{money(line.amount, selected.currency)}</span></li>)}</ul></> : null}
        </>}
      </div> : <div className="janso-supplier-purchases">
        <p className="janso-supplier-purchases__intro">Recent supplier bills, newest first. Open an invoice to review its saved lines.</p>
        {failure ? <Notice tone="danger" title="Purchase history unavailable">{failure}<Button variant="ghost" onClick={() => void load()}>Try again</Button></Notice> : null}
        {!rows.length && loading ? <p role="status">Loading purchases…</p> : null}
        {rows.length ? <><div className="janso-supplier-purchases__head" aria-hidden="true"><span>Invoice</span><span>Invoice date</span><span>Purchase amount</span><span>Status</span></div><ul className="janso-supplier-purchases__list" aria-label="Supplier purchases">{rows.map(row => <li key={row.id}><button type="button" aria-label={`Open invoice ${row.invoice || 'without a number'}, ${row.date ? format.date(row.date) : 'date unavailable'}, ${money(row.amount, row.currency)}, ${row.status.toLowerCase()}`} onClick={() => void openBill(row)}><span className="janso-supplier-purchases__invoice" data-label="Invoice">{row.invoice || 'Invoice number unavailable'}</span><span data-label="Invoice date">{row.date ? format.date(row.date) : 'Date unavailable'}</span><strong data-label="Purchase amount">{money(row.amount, row.currency)}</strong><small className="janso-supplier-purchases__status" data-label="Status">{row.status.toLowerCase()}</small></button></li>)}</ul></>
          : !loading && !failure ? <EmptyState title="No purchases from this supplier" body="Saved purchase bills will appear here." /> : null}
        {next ? <Button variant="ghost" disabled={loading} onClick={() => void load(next)}>{loading ? 'Loading…' : 'Show more purchases'}</Button> : null}
      </div>}
    </Drawer>
  </>;
}
