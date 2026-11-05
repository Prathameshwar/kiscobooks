'use client';

import { Notice, Select, TextField, useFormatters } from '@janso/ui';
import { blankPurchaseTracking, purchaseSerials } from '../lib/purchase-workspace-details';
import * as D from '../lib/fixed-decimal';
import type { PurchaseDetailEditorProps } from './PurchaseDetailEditor';

export function PurchaseReceiptPanel({ draft, policy, disabled, setDetails, error, number }: PurchaseDetailEditorProps) {
  const { quantity } = useFormatters();
  const items = draft.lines.filter(line => line.kind === 'ITEM' && line.subject);
  const patch = (lineKey: string, sourceId: string, value: string) => setDetails(current => ({ ...current, receipts: [...current.receipts.filter(receipt => receipt.lineKey !== lineKey), { lineKey, sourceId, quantity: value }] }));
  return <>
    <Select label="Goods receipt intent" value={draft.details.receiptIntent} disabled={disabled}
      options={[{ value: 'DIRECT', label: 'Receive with this bill · planned' }, { value: 'REFERENCE', label: 'Match existing receipts · no new receipt' }, { value: 'DEFERRED', label: 'Receive later · pending receipt' }]}
      onChange={value => setDetails(current => ({ ...current, receiptIntent: value as typeof current.receiptIntent }))} />
    <Notice tone="info" title={draft.details.receiptIntent === 'REFERENCE' ? 'Existing receipts will not be received again' : draft.details.receiptIntent === 'DEFERRED' ? 'Receipt remains pending' : 'Receipt quantities are proposals'}>
      {draft.details.receiptIntent === 'REFERENCE' ? 'Match only the billed slice. Remaining quantities are supplied example balances, not live availability.' : 'This preview does not change on-hand stock. Billed quantity determines the commercial line amount.'}</Notice>
    {items.length === 0 ? <p>No item lines to receive. Account and service lines do not create goods receipts.</p> : null}
    {draft.details.receiptIntent === 'REFERENCE' ? items.map((line, index) => {
      const sources = policy.details.receipts.filter(receipt => receipt.supplier === draft.supplier && receipt.currency === policy.currency && receipt.subject === line.subject && receipt.unit === line.unit);
      const allocation = draft.details.receipts.find(receipt => receipt.lineKey === line.key);
      const source = sources.find(receipt => receipt.id === allocation?.sourceId);
      const selected = D.parse(allocation?.quantity ?? '');
      const allocated = draft.details.receipts.filter(receipt => receipt.sourceId === source?.id && items.some(item => item.key === receipt.lineKey)).map(receipt => D.parse(receipt.quantity));
      const remaining = source && allocated.every(value => value !== null) ? D.parse(source.remaining)! - D.add(...allocated as D.Fixed[]) : null;
      return <fieldset key={line.key} className="janso-entry-detail__group"><legend>Line {index + 1} · {line.label}</legend>
        <div data-purchase-detail-field={`receipt-${line.key}`}><Select label={`Existing receipt for line ${index + 1}`} disabled={disabled} value={allocation?.sourceId ?? ''}
          options={[{ value: '', label: sources.length ? 'Choose a receipt' : 'No eligible receipt for this item/supplier' }, ...sources.map(receipt => ({ value: receipt.id, label: receipt.label }))]}
          error={error(`receipt-${line.key}`)} onChange={id => patch(line.key, id, allocation?.quantity ?? line.billed)} /></div>
        {number(`receipt-quantity-${line.key}`, `Matched quantity for line ${index + 1}`, allocation?.quantity ?? '', value => patch(line.key, allocation?.sourceId ?? '', value), { quantity: true, unit: line.unit })}
        <p className="janso-entry-workspace__caption">Billed: {quantity(line.billed)} {line.unit} · Source available: {source ? quantity(source.remaining) : '—'} · Remaining after all selected slices: {remaining === null || selected === null ? '—' : quantity(D.format(remaining))}</p>
        {allocation?.sourceId && !source ? <p className="janso-error">The retained receipt no longer matches this supplier, item or unit. Select an eligible receipt.</p> : null}
      </fieldset>;
    }) : draft.details.receipts.length ? <p className="janso-entry-workspace__caption">Previous receipt selections are retained for review and are inactive in this receipt mode.</p> : null}
    {error('receipt-allocation') ? <p role="alert" className="janso-error" data-purchase-detail-field="receipt-allocation">{error('receipt-allocation')}</p> : null}
  </>;
}

export function PurchaseTrackingPanel({ draft, policy, disabled, setDetails, error }: PurchaseDetailEditorProps) {
  const items = draft.lines.filter(line => line.kind === 'ITEM' && line.subject);
  const locked = disabled || draft.details.receiptIntent !== 'DIRECT';
  const patch = (key: string, values: Partial<ReturnType<typeof blankPurchaseTracking>>) => setDetails(current => ({ ...current, tracking: { ...current.tracking, [key]: { ...(current.tracking[key] ?? blankPurchaseTracking()), ...values } } }));
  return <>
    <p className="janso-entry-workspace__caption">Tracking follows the item’s supplied requirements. Serial numbers are case-sensitive, one per line, and must match the whole units received.</p>
    {draft.details.receiptIntent !== 'DIRECT' ? <Notice tone="info" title="Tracking entries are retained">Existing receipt matching uses source receipt facts. For deferred receipt, complete tracking when receiving goods. These retained details are inactive.</Notice> : null}
    {!items.length ? <p>No item lines need tracking.</p> : null}
    {items.map((line, index) => {
      const value = draft.details.tracking[line.key] ?? blankPurchaseTracking(), rule = policy.details.tracking[line.subject];
      return <fieldset key={line.key} className="janso-entry-detail__group"><legend>Line {index + 1} · {line.label}</legend>
        <div data-purchase-detail-field={`location-${line.key}`}><Select label={`Receipt location for line ${index + 1}`} value={value.location} disabled={locked} required={!!rule}
          options={[{ value: '', label: rule ? 'Choose a receipt location' : 'No location selected' }, ...policy.details.locations]}
          error={error(`location-${line.key}`)} onChange={location => patch(line.key, { location })} /></div>
        {rule?.batch ? <div data-purchase-detail-field={`batch-${line.key}`}><TextField label={`Batch number for line ${index + 1}`} required value={value.batch} disabled={locked} maxLength={80}
          error={error(`batch-${line.key}`)} onChange={event => patch(line.key, { batch: event.target.value })} /></div> : null}
        {rule?.expiry ? <div data-purchase-detail-field={`expiry-${line.key}`}><TextField label={`Expiry date for line ${index + 1}`} required type="date" value={value.expiry} disabled={locked}
          error={error(`expiry-${line.key}`)} onChange={event => patch(line.key, { expiry: event.target.value })} /></div> : null}
        {rule?.serials ? <div className="janso-field" data-purchase-detail-field={`serials-${line.key}`}><label className="janso-label" htmlFor={`purchase-serials-${line.key}`}>Serial numbers for line {index + 1}</label>
          <textarea id={`purchase-serials-${line.key}`} className="janso-input" rows={5} value={value.serials} disabled={locked} maxLength={10000} aria-invalid={!!error(`serials-${line.key}`)} aria-describedby={`purchase-serials-${line.key}-help`}
            onChange={event => patch(line.key, { serials: event.target.value })} />
          <p className="janso-entry-workspace__caption" id={`purchase-serials-${line.key}-help`}>{error(`serials-${line.key}`) ?? `${purchaseSerials(value.serials).length} entered · one per unit received (${line.received || '—'}).`}</p>
        </div> : null}
      </fieldset>;
    })}
  </>;
}
