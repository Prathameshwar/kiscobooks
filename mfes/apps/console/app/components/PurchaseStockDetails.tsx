'use client';

import { useCallback, useEffect, useState } from 'react';
import { Button, Modal, Notice, SearchSelect, useFormatters, type SearchSelectLoader } from '@janso/ui';
import { SerialRegistration } from './SerialRegistration';
import { StockReference } from './VoucherStock';
import { PurchaseBatchChooser } from './PurchaseBatchChooser';
import { productFieldRequest as request } from '../lib/product-fields';
import { purchaseBatch, purchaseTracking, type PurchaseBatch, type PurchaseTracking } from '../lib/purchase-stock';
import { blankPurchaseStock, type PurchaseLine, type PurchaseStock } from '../lib/purchase-workspace';
import { trackingId, trackingTitle } from '../lib/stock-tracking-resources';
import type { components as Accounting } from '@janso/api-client/accounting';

type Page<T> = { items: T[]; page: { has_more: boolean; next_cursor: string | null } };

/** One destination and batch per Purchase row. Duplicate the row to split a receipt. */
export function PurchaseStockDetails({ company, line, postingDate, canEdit, access, canReadBatch, canPrepareBatch, canPrepareSerial, promptForItem, onChange }: {
  company: string; line: PurchaseLine; postingDate: string; canEdit: boolean;
  access?: { warehouse: boolean; bin: boolean; batch: boolean; serial: boolean };
  canReadBatch?: boolean; canPrepareBatch?: boolean; canPrepareSerial?: boolean; promptForItem?: string | null;
  onChange: (stock: PurchaseStock) => void;
}) {
  const format = useFormatters();
  const stock = line.stock ?? blankPurchaseStock();
  const [profile, setProfile] = useState<PurchaseTracking | null>(null), [defaultWarehouse, setDefaultWarehouse] = useState('');
  const [failure, setFailure] = useState(''), [loading, setLoading] = useState(false);
  const [batch, setBatch] = useState<PurchaseBatch | null>(null), [batchError, setBatchError] = useState('');
  const [chooserOpen, setChooserOpen] = useState(false);
  const [serialChooserOpen, setSerialChooserOpen] = useState(false), [serialRevision, setSerialRevision] = useState(0);

  useEffect(() => {
    const abort = new AbortController();
    setChooserOpen(false); setSerialChooserOpen(false); setBatch(null); setBatchError(''); setProfile(null); setFailure(''); setLoading(true);
    if (!trackingId.test(line.subject)) { setLoading(false); return () => abort.abort(); }
    void Promise.all([
      purchaseTracking(company, line.subject),
      request<{ company_id: string; default_purchase_warehouse_id?: string | null; main_warehouse_id?: string | null }>(
        'catalog', 'GET', `/v1/companies/${company}/warehouse-configuration`, undefined, undefined, abort.signal),
    ]).then(([next, config]) => {
      if (config.company_id !== company) throw Error('The warehouse configuration could not be verified.');
      const warehouse = config.default_purchase_warehouse_id ?? config.main_warehouse_id ?? '';
      if (!trackingId.test(warehouse)) throw Error('Set up a purchase warehouse before billing goods.');
      if (!abort.signal.aborted) { setProfile(next); setDefaultWarehouse(warehouse); }
    }).catch(error => { if (!abort.signal.aborted) setFailure(error instanceof Error ? error.message : 'Stock details could not be loaded.'); })
      .finally(() => { if (!abort.signal.aborted) setLoading(false); });
    return () => abort.abort();
  }, [company, line.subject]);

  useEffect(() => {
    if (profile?.lotTracking && promptForItem === line.subject && !stock.lotId && canEdit && canReadBatch && access?.batch) setChooserOpen(true);
  }, [profile, promptForItem, line.subject, stock.lotId, canEdit, canReadBatch, access?.batch]);

  useEffect(() => {
    const abort = new AbortController(); setBatch(null); setBatchError('');
    if (stock.lotId && canReadBatch) void purchaseBatch(company, line.subject, stock.lotId, abort.signal)
      .then(value => { if (!abort.signal.aborted) setBatch(value); })
      .catch(error => { if (!abort.signal.aborted) setBatchError(error instanceof Error ? error.message : 'The batch could not be verified.'); });
    return () => abort.abort();
  }, [company, line.subject, stock.lotId, canReadBatch]);

  const serials = useCallback<SearchSelectLoader>(async ({ q, cursor, signal }) => {
    const params = new URLSearchParams({ item_id: line.subject, status: 'ACTIVE', is_held: 'false', receipt_eligible: 'true', limit: '50' });
    if (stock.lotId) params.set('lot_id', stock.lotId);
    if (q.trim()) params.set('q', q.trim());
    if (cursor) params.set('cursor', cursor);
    const page = await request<Page<Accounting['schemas']['SerialListItem']>>('accounting', 'GET', `/v1/companies/${company}/stock-tracking/serials?${params}`, undefined, undefined, signal);
    if (!page.page || !Array.isArray(page.items) || page.items.some(row => !trackingId.test(row.id))) throw Error('Prepared serials could not be verified.');
    return { items: page.items.map(row => ({ id: row.id, label: trackingTitle(row) })), nextCursor: page.page.has_more ? page.page.next_cursor : null };
  }, [company, line.subject, stock.lotId]);

  if (!trackingId.test(line.subject)) return <p className="janso-entry-workspace__caption">Choose a product to set its stock destination.</p>;
  const requested = line.billed || line.received;
  const serialCountWrong = !!profile?.serialTracking && !!requested && (!/^[1-9]\d*(?:\.0{1,4})?$/.test(requested) || BigInt(requested.split('.')[0]!) !== BigInt(stock.unitIds.length));
  return <section className="janso-entry-stock" aria-label="Stock details for this purchase line">
    <h4>Stock destination</h4>
    <p className="janso-entry-workspace__caption">One warehouse and batch per line. Duplicate the line to split this purchase.</p>
    {loading ? <p role="status">Checking product tracking and purchase warehouse…</p> : null}
    {failure ? <Notice tone="danger" title="Stock details unavailable">{failure}</Notice> : null}
    {canEdit && ((profile?.lotTracking && !access?.batch) || (profile?.serialTracking && !access?.serial)) ? <Notice tone="warning">This product requires tracking fields you cannot edit. Ask a company administrator for Purchase stock-line field access.</Notice> : null}
    {profile?.lotTracking && !canReadBatch ? <Notice tone="warning">Batch read access is required to choose a batch for this product.</Notice> : null}
    <div className="janso-form-grid">
      <StockReference company={company} resource="warehouses" label="Receive into warehouse" value={stock.warehouseId || defaultWarehouse} required disabled={!canEdit || !access?.warehouse || !profile || !!failure} physicalOnly onChange={warehouseId => onChange({ ...stock, warehouseId: warehouseId ?? '', binId: '', unitIds: [] })} />
      {access?.bin || stock.binId ? <StockReference company={company} resource="warehouse-bins" parent={stock.warehouseId || defaultWarehouse} label="Bin (optional)" value={stock.binId} disabled={!canEdit || !access?.bin || !profile || !!failure || !(stock.warehouseId || defaultWarehouse)} onChange={binId => onChange({ ...stock, binId: binId ?? '' })} /> : null}
      {profile?.lotTracking ? <div>
        {canEdit && canReadBatch && access?.batch ? <Button type="button" variant="ghost" onClick={() => setChooserOpen(true)}>{stock.lotId ? 'Change batch' : 'Choose or create batch'}</Button> : null}
        {batch ? <p className="janso-entry-workspace__caption">Batch {batch.code ?? 'selected'}{batch.manufactured_on ? ` · Made ${format.date(batch.manufactured_on)}` : ''}{batch.expires_on ? ` · Expires ${format.date(batch.expires_on)}` : ''}</p> : null}
        {batchError ? <p className="janso-error">{batchError}</p> : null}
      </div> : null}
    </div>
    {profile?.serialTracking ? <SearchSelect multiple label="Prepared serials" value={stock.unitIds} loadOptions={serials} scopeKey={[company, line.subject, stock.lotId, String(serialRevision)].join(':')} minQueryLength={0} maxOptions={200} disabled={!canEdit || !access?.serial || !!failure || profile.lotTracking && !stock.lotId} onChange={unitIds => onChange({ ...stock, unitIds })} hint={`Select one serial per received unit. ${stock.unitIds.length} selected${requested ? ` for ${requested} units` : ''}.`} /> : null}
    {profile?.serialTracking && canEdit && access?.serial && canPrepareSerial ? <Button type="button" variant="ghost" disabled={!!failure || profile.lotTracking && !stock.lotId} onClick={() => setSerialChooserOpen(true)}>Create or scan serials for this purchase</Button> : null}
    {serialChooserOpen && profile?.serialTracking && canEdit && canPrepareSerial ? <Modal open title="Register serials for this purchase" size="lg" onClose={() => setSerialChooserOpen(false)}><SerialRegistration key={[company, line.subject, stock.lotId].join(':')} company={company} item={line.subject} lot={stock.lotId || undefined} forReceipt onRegistered={ids => { onChange({ ...stock, unitIds: [...new Set([...stock.unitIds, ...ids])] }); setSerialRevision(value => value + 1); setSerialChooserOpen(false); }} /></Modal> : null}
    {profile?.lotTracking && !stock.lotId ? <p className="janso-error">Select a batch for this product before saving the Purchase.</p> : null}
    {serialCountWrong ? <p className="janso-error">Select exactly one prepared serial for each received unit.</p> : null}
    {profile && !profile.lotTracking && !profile.serialTracking ? <p className="janso-entry-workspace__caption">This product does not require batch or serial tracking.</p> : null}
    {chooserOpen && profile?.lotTracking ? <PurchaseBatchChooser key={`${company}:${line.subject}`} company={company} item={line.subject} name={line.label} postingDate={postingDate} profile={profile}
      canCreate={!!canPrepareBatch} onClose={() => setChooserOpen(false)} onSelect={selected => { onChange({ ...stock, lotId: selected.id, unitIds: [] }); setChooserOpen(false); }} /> : null}
  </section>;
}
