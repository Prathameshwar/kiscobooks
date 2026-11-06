/**
 * The standard Purchase layout, as a canvas a person can start from (plan R4, 2026-11-04).
 *
 * Purchase prints on a built-in layout until a design is chosen for it: `purchase-a4@7`,
 * rendered by Vouchers' `domain/purchase_print.py::render_html` with `purchase_print.css`.
 * *Customize layout* used to open an empty page because there was no canvas to copy
 * (invoice-design.md §9 item 7). This starter carries the core blocks on the same paper and
 * margins: company, status, supplier, lines, bill summary and narration. The built-in print
 * has more detail, which the create dialog names before a person publishes a custom layout.
 *
 * **A copy to start from, not the built-in layout itself.** The standard PDF also prints things
 * a design cannot bind to yet (the state note under the title, settlements, adjustments, the
 * evidence footer); those are left out rather than imitated with static text that would print
 * the same words on every bill. A design printed for Purchase still carries the bill's identity
 * and status in every page footer, which the renderer adds on its own.
 *
 * Geometry is millimetres on A4 portrait with the standard layout's margins (18/15/22/15), so
 * the printable area is 180 × 257mm and every table's columns sum to exactly 180mm.
 */

import { pageGeometry } from '@janso/ui';

import {
  type CanvasDefinition,
  type CanvasElement,
  type CanvasPage,
  type CanvasSection,
  type ItemColumn,
  type LineProfile,
  SCHEMA_VERSION,
} from './layout-model';

type Box = [xMm: number, yMm: number, widthMm: number, heightMm: number];

const INK = '#172334';
const MUTED = '#4a5c70';
const RULE = '#263c58';

const LEFT = 15;
const WIDTH = 180;

function text(id: string, content: string, [xMm, yMm, widthMm, heightMm]: Box, style: CanvasElement['style'] = {}): CanvasElement {
  return { id, type: 'TEXT', xMm, yMm, widthMm, heightMm, content, style };
}

function field(
  id: string,
  bindingPath: NonNullable<CanvasElement['bindingPath']>,
  [xMm, yMm, widthMm, heightMm]: Box,
  options: { label?: string; style?: CanvasElement['style'] } = {},
): CanvasElement {
  return {
    id,
    type: 'FIELD_BINDING',
    xMm,
    yMm,
    widthMm,
    heightMm,
    bindingPath,
    ...(options.label ? { label: options.label } : {}),
    style: options.style ?? {},
  };
}

function zone(id: string, type: CanvasSection['type'], [xMm, yMm, widthMm, heightMm]: Box, elements: CanvasElement[], title?: string): CanvasSection {
  return { id, type, xMm, yMm, widthMm, heightMm, elements, ...(title ? { title } : {}) };
}

function columns(spec: [ItemColumn['key'], number, ItemColumn['align']?][]): ItemColumn[] {
  return spec.map(([key, widthMm, align]) => ({ key, widthMm, ...(align ? { align } : {}), show: true }));
}

/** A product line: what was bought, its HSN/SAC, quantity, unit and rate, then the amounts. */
export const STANDARD_PRODUCT_COLUMNS: ItemColumn[] = columns([
  ['serial_no', 8, 'right'],
  ['description', 56],
  ['hsn_sac', 18],
  ['quantity', 18, 'right'],
  ['unit', 14],
  ['rate', 22, 'right'],
  ['taxable_value', 22, 'right'],
  ['amount', 22, 'right'],
]);

/** An account line: the ledger it posts to, what it was for, and its amount. */
export const STANDARD_ACCOUNT_COLUMNS: ItemColumn[] = columns([
  ['serial_no', 8, 'right'],
  ['account', 54],
  ['description', 80],
  ['amount', 38, 'right'],
]);

const label = { fontSizePt: 8, uppercase: true, color: MUTED } as const;
const detail = { fontSizePt: 9 } as const;

function header(): CanvasSection {
  return zone('sec-header', 'HEADER', [LEFT, 18, WIDTH, 30], [
    { id: 'el-header-rule', type: 'DIVIDER', xMm: 0, yMm: 0, widthMm: WIDTH, heightMm: 1, style: { borderWidthMm: 1.5, borderColor: RULE } },
    field('el-company', 'company.name', [0, 4, 120, 6], { style: { fontSizePt: 11, fontWeight: 'bold', color: INK } }),
    text('el-title', 'Purchase voucher', [0, 11, 130, 11], { fontSizePt: 22, fontWeight: 'bold', color: INK }),
    field('el-status', 'voucher.status', [140, 13, 40, 6], {
      style: { fontSizePt: 8, fontWeight: 'bold', textAlign: 'center', borderWidthMm: 0.25, borderStyle: 'solid', borderColor: '#8491a1' },
    }),
    text('el-subtitle', 'Internal purchase record · Not a supplier tax invoice', [0, 23, WIDTH, 5], { fontSizePt: 8.5, color: MUTED }),
  ]);
}

function parties(): CanvasSection {
  return zone('sec-parties', 'BILLING_SHIPPING', [LEFT, 52, WIDTH, 34], [
    text('el-supplier-label', 'Supplier', [0, 0, 85, 4], label),
    field('el-supplier', 'party.name', [0, 5, 85, 6], { style: { fontSizePt: 12, fontWeight: 'bold' } }),
    field('el-bill-reference', 'voucher.bill_reference', [0, 13, 85, 5], { label: 'Supplier invoice no.', style: detail }),
    field('el-bill-date', 'voucher.document_date', [0, 19, 85, 5], { label: 'Supplier invoice date', style: detail }),
    text('el-record-label', 'Our purchase record', [95, 0, 85, 4], label),
    field('el-number', 'voucher.document_number', [95, 5, 85, 5], { label: 'Voucher no.', style: detail }),
    field('el-posting-date', 'voucher.posting_date', [95, 11, 85, 5], { label: 'Posting date', style: detail }),
    field('el-due-date', 'voucher.due_date', [95, 17, 85, 5], { label: 'Payment due', style: detail }),
    field('el-currency', 'voucher.currency', [95, 23, 85, 5], { label: 'Currency', style: detail }),
  ]);
}

function lineTable(kind: 'ITEM_TABLE' | 'ACCOUNT_TABLE', yMm: number, heightMm: number): CanvasSection {
  const products = kind === 'ITEM_TABLE';
  return zone(products ? 'sec-items' : 'sec-accounts', products ? 'ITEM_TABLE' : 'CUSTOM', [LEFT, yMm, WIDTH, heightMm], [
    {
      id: products ? 'el-items' : 'el-accounts',
      type: kind,
      xMm: 0,
      yMm: 0,
      widthMm: WIDTH,
      heightMm,
      columns: (products ? STANDARD_PRODUCT_COLUMNS : STANDARD_ACCOUNT_COLUMNS).map((column) => ({ ...column })),
      rowOptions: { repeatHeader: true },
    },
  ], products ? 'Purchase lines' : 'Accounts and expenses');
}

function totals(yMm: number): CanvasSection {
  // The bill summary sits at the right, 88mm wide, as in the standard layout.
  return zone('sec-totals', 'TOTALS', [LEFT + WIDTH - 88, yMm, 88, 46], [
    text('el-totals-label', 'Bill summary', [0, 0, 88, 4], label),
    {
      id: 'el-totals',
      type: 'TOTALS_BLOCK',
      xMm: 0,
      yMm: 5,
      widthMm: 88,
      heightMm: 41,
      totalsRows: ['subtotal', 'cgst', 'sgst', 'igst', 'round_off', 'grand_total', 'amount_in_words'],
    },
  ]);
}

function narration(yMm: number): CanvasSection {
  return zone('sec-narration', 'FOOTER', [LEFT, yMm, WIDTH, 15], [
    text('el-narration-label', 'Narration', [0, 0, WIDTH, 4], label),
    field('el-narration', 'voucher.narration', [0, 5, WIDTH, 10], { style: detail }),
  ]);
}

const A4_STANDARD_PAGE: CanvasPage = {
  size: 'A4',
  orientation: 'PORTRAIT',
  margins: { top: 18, right: 15, bottom: 22, left: 15, unit: 'mm' },
  gridSnap: true,
  gridStepMm: 1,
};

/**
 * The standard Purchase layout for a design's lines: one product table, one accounts table, or
 * both (D2: products first, each in its own zone). A design that never said gets products.
 */
export function standardPurchaseLayout(lineProfile: LineProfile | string | undefined): CanvasDefinition {
  // The line tables grow across pages when a bill has more lines than fit; the bands below
  // them move down. Drawn to end by 254mm so the same layout also fits Letter portrait.
  const tables =
    lineProfile === 'MIXED'
      ? [lineTable('ITEM_TABLE', 90, 60), lineTable('ACCOUNT_TABLE', 154, 31)]
      : [lineTable(lineProfile === 'ACCOUNTS' ? 'ACCOUNT_TABLE' : 'ITEM_TABLE', 90, 95)];
  const after = 189;
  return {
    schemaVersion: SCHEMA_VERSION,
    page: { ...A4_STANDARD_PAGE, margins: { ...A4_STANDARD_PAGE.margins } },
    theme: { primaryColor: RULE, fontFamily: 'Arial, Helvetica, sans-serif', fontSizePt: 10 },
    print: { copies: ['ORIGINAL_FOR_RECIPIENT'] },
    sections: [header(), parties(), ...tables, totals(after), narration(after + 50)],
  };
}

/** The paper a new template is created on, as the create form holds it. */
export type StarterPaper = { paperSize: string; orientation: string; widthMm?: string; heightMm?: string };

/**
 * The standard layout on the paper a person chose, or `null` when it does not fit that paper.
 *
 * The service refuses a first version with anything past the edge of its paper, so a starter
 * that does not fit would make the whole create fail. Letter portrait holds A4's layout; a roll,
 * A5 or a landscape sheet does not, and those open on an empty page as before — the designer's
 * presets fit a layout to a roll once it is open.
 */
export function standardPurchaseStarter(lineProfile: LineProfile | string | undefined, paper: StarterPaper): CanvasDefinition | null {
  const layout = standardPurchaseLayout(lineProfile);
  const width = paper.widthMm ? Number(paper.widthMm) : undefined;
  const height = paper.heightMm ? Number(paper.heightMm) : undefined;
  const page: CanvasPage = {
    ...layout.page,
    size: paper.paperSize as CanvasPage['size'],
    orientation: paper.orientation === 'LANDSCAPE' ? 'LANDSCAPE' : 'PORTRAIT',
    ...(paper.paperSize === 'CUSTOM' && width && height ? { widthMm: width, heightMm: height } : {}),
  };
  if (paper.paperSize === 'CUSTOM' && !(width && height && width > 0 && height > 0)) return null;
  const sheet = pageGeometry(page);
  const right = sheet.widthMm - page.margins.right;
  const bottom = sheet.heightMm - page.margins.bottom;
  const fits = layout.sections.every(
    (section) => section.xMm + section.widthMm <= right + 0.05 && (sheet.continuous || section.yMm + section.heightMm <= bottom + 0.05),
  );
  // A roll is narrower than any sheet this layout is drawn for, so it never fits on width alone.
  return fits ? { ...layout, page } : null;
}
