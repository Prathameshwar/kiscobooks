'use client';
import type { components } from '@janso/api-client/vouchers';
import { productFieldRequest as lookup } from './product-fields';
import type { FieldSet } from './voucher-fields';
import { initialStockDraft } from './voucher-stock';
import { trackingId } from './stock-tracking-resources';
import {
  validateAllocation,
  owned,
  type Control,
  type Manifest,
  type Allocation,
  type ImportStage,
} from './opening-stock';

// Native owners compare canonical ASCII keys, independent of browser locale.
function compare(left: string, right: string): number {
  return left < right ? -1 : left > right ? 1 : 0;
}

/** Build only native drafts. Import validation remains the owner of field/configuration rules. */
export async function openingDraftDocument(
  company: string,
  control: Control,
  manifest: Manifest,
  typeId: string,
  onProgress?: (done: number, total: number) => void,
): Promise<ImportStage['document']> {
  owned(company)(control);
  if (
    control.status !== 'OPEN' ||
    manifest.stock_date !== control.books_begin_date ||
    manifest.currency !== control.currency
  )
    throw new Error(
      'Reload the current company opening before preparing drafts.',
    );
  const base = `/v1/companies/${company}`;
  const metadata = await lookup<FieldSet>(
    'vouchers',
    'GET',
    `${base}/voucher-types/${typeId}/field-set?date=${manifest.stock_date}`,
  );
  const profile = initialStockDraft(metadata, manifest.stock_date);
  if (
    profile?.action !== 'OPENING' ||
    profile.openingMode !== manifest.opening_mode
  )
    throw new Error(
      'Choose a published opening-stock type with the same accounting treatment as this worksheet.',
    );
  if (
    !metadata.native.properties?.stock_date ||
    metadata.native.properties.stock_date.readOnly
  )
    throw new Error('Stock date write access is required.');
  const cohorts = [...(manifest.lines ?? [])].sort(
    (a, b) =>
      compare((a.item_id + a.warehouse_id).toLowerCase(), (b.item_id + b.warehouse_id).toLowerCase()) ||
      compare(a.opening?.received_on ?? manifest.stock_date,
        b.opening?.received_on ?? manifest.stock_date,
      ) ||
      (a.opening?.cohort_order ?? 1) - (b.opening?.cohort_order ?? 1) ||
      compare((a.opening?.source_key ?? '').toLowerCase(), (b.opening?.source_key ?? '').toLowerCase()),
  );
  if (!cohorts.length) throw new Error('Add at least one opening allocation.');
  const chunks: Allocation[][] = [];
  let chunk: Allocation[] = [],
    serialCount = 0;
  for (const line of cohorts) {
    const problem = validateAllocation(line, manifest.opening_mode);
    if (problem) throw new Error(problem);
    if (
      chunk.length === 100 ||
      serialCount + (line.unit_ids?.length ?? 0) > 1000
    ) {
      chunks.push(chunk);
      chunk = [];
      serialCount = 0;
    }
    chunk.push(line);
    serialCount += line.unit_ids?.length ?? 0;
  }
  if (chunk.length) chunks.push(chunk);
  const vouchers: components['schemas']['VoucherInput'][] = [];
  const items = new Map<
    string,
    {
      id: string;
      company_id: string;
      status: string;
      row_version: number;
      base_unit_id: string;
    }
  >();
  const totalItems = new Set(cohorts.map((row) => row.item_id)).size;
  for (const stockLines of chunks) {
    const lines: components['schemas']['LineInput'][] = [];
    for (const row of stockLines) {
      let item = items.get(row.item_id);
      if (!item) {
        item = await lookup('catalog', 'GET', `${base}/items/${row.item_id}`);
        if (
          !item ||
          item.id !== row.item_id ||
          item.company_id !== company ||
          item.status !== 'ACTIVE' ||
          !Number.isSafeInteger(item.row_version) ||
          !trackingId.test(item.base_unit_id)
        )
          throw new Error(
            'A worksheet product is no longer active or its current version cannot be verified. Review product setup.',
          );
        items.set(row.item_id, item);
        onProgress?.(items.size, totalItems);
      }
      lines.push({
        line_key: row.line_id,
        line_kind: 'ITEM',
        item: {
          item_id: item.id,
          item_version: item.row_version,
          unit_id: item.base_unit_id,
          actual_quantity: row.quantity,
          billed_quantity: '0',
          custom_fields: {},
        },
      });
    }
    vouchers.push({
      type_revision_id: metadata.configuration.type_revision_id,
      document_date: manifest.stock_date,
      posting_date: manifest.stock_date,
      stock_date: manifest.stock_date,
      currency: manifest.currency,
      mode: 'ITEMS',
      narration: manifest.reason,
      lines,
      stock: {
        action: 'OPENING',
        stock_date: manifest.stock_date,
        currency: manifest.currency,
        reason: manifest.reason,
        opening_mode: manifest.opening_mode,
        opening_control_id: control.id,
        lines: stockLines,
      },
    });
  }
  return { vouchers };
}
