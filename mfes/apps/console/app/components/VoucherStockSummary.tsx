'use client';
import { Card, CardBody, DataTable, ReviewList, SectionHeader, useFormatters, type Column } from '@janso/ui';
import type { components } from '@janso/api-client/vouchers';

type Stock = NonNullable<components['schemas']['VoucherDetail']['stock']>;
const labels: Record<Stock['action'], string> = { OPENING: 'Opening stock', RECEIPT: 'Goods received', DISPATCH: 'Goods dispatched', TRANSFER: 'Warehouse transfer', TRANSFER_DISPATCH: 'Transfer dispatch', TRANSFER_RECEIPT: 'Transfer receipt', CUSTOMER_RETURN: 'Customer return', SUPPLIER_RETURN: 'Supplier return', COUNT: 'Physical count', PURCHASE_INVOICE: 'Purchase invoice receipt' };

/** Render only the stock section the service has made readable to this reviewer. */
export function VoucherStockSummary({ stock }: { stock: Stock }) {
  const format = useFormatters();
  const columns: Column<Stock['lines'][number]>[] = [
    { key: 'item_id', header: 'Product', type: 'custom', render: row => <a className="janso-link" href={'/inventory/stock?item_id=' + row.item_id}>View stock</a> },
    { key: 'warehouse_id', header: 'Warehouse', type: 'custom', render: row => <><a className="janso-link" href={'/masters/warehouses/' + row.warehouse_id}>View warehouse</a>{row.bin_id && <p><a className="janso-link" href={'/masters/warehouse-bins/' + row.bin_id}>View bin</a></p>}</> },
    { key: 'quantity', header: stock.action==='COUNT'?'Counted base quantity':'Base-unit quantity', type: 'custom', render: row => stock.action==='COUNT'?row.quantity:format.quantity(row.quantity) },
    { key: 'lot_id', header: 'Tracking', type: 'custom', render: row => <>{row.lot_id ? 'Batch assigned' : 'No batch'}{!!row.unit_ids?.length && <p>Selected serials: {row.unit_ids.length}</p>}</> },
  ];
  if (stock.action === 'RECEIPT' || stock.action === 'OPENING') columns.push({ key: 'received_value', header: 'Inward carrying value', type: 'custom', render: row => row.received_value == null ? 'Unavailable' : <>{format.money(row.received_value, { display: 'none' })} {stock.currency}{row.zero_value_reason && <p>{row.zero_value_reason}</p>}</> });
  if (stock.action === 'TRANSFER' || stock.action === 'TRANSFER_DISPATCH') columns.push({ key: 'destination_warehouse_id', header: 'Destination', type: 'custom', render: row => row.destination_warehouse_id ? <><a className="janso-link" href={'/masters/warehouses/' + row.destination_warehouse_id}>View destination warehouse</a>{row.destination_bin_id && <p><a className="janso-link" href={'/masters/warehouse-bins/' + row.destination_bin_id}>View destination bin</a></p>}</> : 'Unavailable' });
  if (['CUSTOMER_RETURN', 'SUPPLIER_RETURN', 'TRANSFER_RECEIPT'].includes(stock.action)) columns.push({ key: 'source_movement_id', header: 'Source evidence', type: 'custom', render: row => row.source_movement_id ? 'Original movement linked' : 'Unavailable' });
  return <Card><CardBody><div className="janso-flow"><SectionHeader title="Physical stock review" description="Review the captured base quantities, tracking and source evidence before approving or posting." /><ReviewList items={[{ label: 'Movement', value: labels[stock.action] }, { label: 'Stock date', value: format.date(stock.stock_date) }, { label: 'Reason', value: stock.reason }, ...(stock.action === 'OPENING' ? [{ label: 'Opening accounting', value: stock.opening_mode === 'LINKED_GL' ? 'Linked to an existing inventory GL opening' : 'Stock and opening value post together' }] : [])]} /><DataTable caption="Captured physical stock lines" columns={columns} rows={stock.lines} rowId={row => row.line_id} rowLabel={() => 'Physical stock item'} /></div></CardBody></Card>;
}
