import { layoutToWire } from '../../lib/design-canvas';
import { trackingId } from '../../lib/stock-tracking-resources';
import type { CanvasDefinition } from './layout-model';
import type { LayoutWarning } from './layout-warnings';

/**
 * What a voucher kind's printer prints from a designed layout, checked before a layout is
 * published for it (designer plan P0/P3, 2026-11-03).
 *
 * The rules are not written here: Vouchers publishes one manifest per kind
 * (`GET /print-capabilities`, `apis/vouchers/src/vouchers/domain/print_capabilities.py`) and its
 * renderer refuses a layout against that same manifest. This reads it and says, in the same
 * words and before publishing, what the printer would refuse — so the designer and the printer
 * cannot disagree.
 */
export type PrintManifest = {
  kind: string;
  version: string;
  paper_sizes: string[];
  orientations: string[];
  element_types: string[];
  bindings: string[];
  item_columns: string[];
  totals_rows: string[];
  tax_groupings: string[];
  line_tables: { min: number; max_each: number };
  options: { copies: boolean; copy_marks: boolean; pre_printed_stationery: boolean; free_placement: boolean; styles: boolean; images: boolean; components: boolean };
  /** How large the pictures a printed layout embeds may be (plan R2), when the kind prints images. */
  images?: { max_bytes: number; total_max_bytes: number; media_types: string[] };
};
export type PrintCapabilities = { version: string; kinds: PrintManifest[] };

const list = (value: unknown) => Array.isArray(value) && value.every((entry) => typeof entry === 'string');
/** The service's answer, checked: a manifest that is not one blocks nothing rather than everything. */
export function verifyPrintCapabilities(value: PrintCapabilities): PrintCapabilities {
  const sound = !!value && typeof value.version === 'string' && Array.isArray(value.kinds) && value.kinds.every((kind) =>
    /^[A-Z_]{2,40}$/.test(kind?.kind ?? '') && ['paper_sizes', 'orientations', 'element_types', 'bindings', 'item_columns', 'totals_rows', 'tax_groupings'].every((key) => list(kind[key as keyof PrintManifest]))
    && Number.isInteger(kind.line_tables?.min) && Number.isInteger(kind.line_tables?.max_each) && typeof kind.options === 'object' && kind.options !== null
    && (kind.images === undefined || (Number.isInteger(kind.images?.max_bytes) && Number.isInteger(kind.images?.total_max_bytes) && list(kind.images?.media_types))));
  if (!sound) throw { status: 502, message: 'The print capabilities could not be verified.' };
  return value;
}

/** Headings and names, as the designer's catalogues show them. */
const COLUMN_LABELS: Record<string, string> = {
  serial_no: '#', description: 'Description', hsn_sac: 'HSN/SAC', batch: 'Batch', expiry: 'Expiry', quantity: 'Qty', unit: 'Unit',
  rate: 'Rate', mrp: 'MRP', discount: 'Discount', taxable_value: 'Taxable value', cgst_rate: 'CGST %', cgst_amount: 'CGST',
  sgst_rate: 'SGST %', sgst_amount: 'SGST', igst_rate: 'IGST %', igst_amount: 'IGST', cess: 'Cess', amount: 'Amount', account: 'Account',
};
const TOTALS_LABELS: Record<string, string> = {
  subtotal: 'Subtotal', discount: 'Discount', taxable_value: 'Taxable value', cgst: 'CGST', sgst: 'SGST', igst: 'IGST', cess: 'Cess',
  round_off: 'Round off', grand_total: 'Grand total', amount_in_words: 'Amount in words', outstanding_balance: 'Outstanding balance',
};
const TYPE_NAMES: Record<string, string> = {
  IMAGE: 'images', QR_CODE: 'QR codes', BARCODE: 'barcodes', TAX_SUMMARY: 'tax summaries', SHAPE: 'boxes', SIGNATURE: 'signatures',
  TOTALS_BLOCK: 'totals blocks',
};
const title = (kind: string) => kind.charAt(0) + kind.slice(1).toLowerCase();
const problem = (targetId: string, message: string): LayoutWarning => ({ code: 'print-unsupported', severity: 'error', targetId, message });

/** The printer's own sentences for a picture it will not embed (`print_capabilities.py`, `_IMAGE_REFUSALS`). */
export const NO_PICTURE = 'An image on this layout has no picture chosen.';
export const WITHDRAWN_PICTURE = 'An image on this layout has been withdrawn; choose another picture.';
const kb = (bytes: number) => `${Math.floor(bytes / 1024)} KB`;
const tooLarge = (max: number) => `An image on this layout is larger than ${kb(max)}; upload a smaller picture.`;
const overBudget = (max: number) => `The images on this layout are larger than ${kb(max)} together; use smaller pictures.`;

/** What the designer knows about a saved picture: the asset list it already reads carries both. */
export type KnownAsset = { id: string; file_size_bytes: number; is_active: boolean };

/**
 * The pictures the printer would refuse, judged from the asset list (plan R2/R4).
 *
 * Only what the list shows is judged: a picture the list does not hold — another page of assets,
 * a list still loading, one that failed — is left to the printer, which refuses it at print with
 * its own reason. A picture placed twice is one picture to the size budget, as it is to the PDF.
 */
export function imageProblems(layout: CanvasDefinition, manifest: PrintManifest, assets: readonly KnownAsset[]): LayoutWarning[] {
  const bounds = manifest.images;
  if (!manifest.options.images || !bounds) return [];
  const byId = new Map(assets.map((asset) => [asset.id, asset]));
  const found: LayoutWarning[] = [];
  const counted = new Set<string>();
  let total = 0;
  let firstTarget: string | undefined;
  for (const section of layout.sections) {
    for (const element of section.elements) {
      const asset = element.assetId ? byId.get(element.assetId) : undefined;
      if (!asset) continue;
      firstTarget ??= element.id;
      if (!asset.is_active) found.push(problem(element.id, WITHDRAWN_PICTURE));
      else if (asset.file_size_bytes > bounds.max_bytes) found.push(problem(element.id, tooLarge(bounds.max_bytes)));
      if (!counted.has(asset.id)) { counted.add(asset.id); total += asset.file_size_bytes; }
    }
  }
  if (firstTarget && total > bounds.total_max_bytes) found.push(problem(firstTarget, overBudget(bounds.total_max_bytes)));
  return found;
}

/** Everything in `layout` the kind's printer would refuse, each as a publish-blocking error. */
export function printProblems(layout: CanvasDefinition, manifest: PrintManifest): LayoutWarning[] {
  const wire = layoutToWire(layout);
  const first = layout.sections[0]?.id ?? '';
  const found: LayoutWarning[] = [];
  const refuse = (target: string | undefined, reason: string) =>
    found.push({ code: 'print-unsupported', severity: 'error', targetId: target || first, message: `${title(manifest.kind)} printing does not support ${reason} yet.` });

  if (!manifest.paper_sizes.includes(layout.page.size)) refuse(first, `${layout.page.size.replace(/_/g, ' ').toLowerCase()} paper`);
  if (!manifest.orientations.includes(layout.page.orientation)) refuse(first, 'this page orientation');
  const options = manifest.options, print = wire.print_options;
  if ((print?.copies?.length ?? 0) > 1 && !options.copies) refuse(first, 'more than one printed copy');
  if (print?.copy_mark_position && !options.copy_marks) refuse(first, 'copy marks');
  if (print?.pre_printed_stationery && !options.pre_printed_stationery) refuse(first, 'pre-printed stationery');
  const tables: Record<string, number> = { ITEM_TABLE: 0, ACCOUNT_TABLE: 0 };
  for (const section of wire.sections ?? []) {
    if (section.component_code && !options.components) refuse(section.id, 'shared components in a zone');
    if (section.free_placement && !options.free_placement) refuse(section.id, 'freely placed zones');
    if ((section.elements ?? []).filter((element) => element.type in tables).length > 1) refuse(section.id, 'two line tables in the same zone');
    for (const element of section.elements ?? []) {
      if (!manifest.element_types.includes(element.type)) { refuse(element.id, TYPE_NAMES[element.type] ?? element.type.toLowerCase()); continue; }
      // The printer refuses an empty picture frame rather than printing a hole in the page.
      if (element.type === 'IMAGE' && !element.asset_id) found.push(problem(element.id, NO_PICTURE));
      if (element.asset_id && !options.images) refuse(element.id, 'images in a signature');
      if (!options.styles && Object.values(element.style ?? {}).some((value) => value != null)) refuse(element.id, 'element styles');
      if (element.type === 'FIELD_BINDING' && !manifest.bindings.includes(element.binding_path ?? '')) refuse(element.id, `the field ${element.binding_path}`);
      if (element.type in tables) {
        tables[element.type]! += 1;
        for (const column of element.columns ?? []) {
          if ((column.show ?? true) && !manifest.item_columns.includes(column.key)) refuse(element.id, `the ${COLUMN_LABELS[column.key] ?? column.key} column`);
        }
      }
      if (element.type === 'TOTALS_BLOCK') {
        for (const row of element.totals_rows ?? []) if (!manifest.totals_rows.includes(row)) refuse(element.id, `the ${(TOTALS_LABELS[row] ?? row).toLowerCase()} total`);
      }
      if (element.type === 'TAX_SUMMARY' && !manifest.tax_groupings.includes(element.tax_grouping ?? 'by_rate')) refuse(element.id, 'a tax summary grouped by HSN');
    }
  }
  if (tables.ITEM_TABLE! + tables.ACCOUNT_TABLE! < manifest.line_tables.min) refuse(first, "a layout without a line table, which is where the bill's lines print");
  if (tables.ITEM_TABLE! > manifest.line_tables.max_each) refuse(first, 'more than one product table');
  if (tables.ACCOUNT_TABLE! > manifest.line_tables.max_each) refuse(first, 'more than one accounts table');
  return found;
}

/** The manifest for a kind, if the service publishes one. */
export function manifestFor(capabilities: PrintCapabilities | null | undefined, kind: string | undefined): PrintManifest | undefined {
  return kind ? capabilities?.kinds.find((entry) => entry.kind === kind) : undefined;
}

/** The capabilities path for a company. */
export function printCapabilitiesPath(company: string): string | undefined {
  return trackingId.test(company) ? `/v1/companies/${company}/print-capabilities` : undefined;
}
