/**
 * Named starting points: "make this an 80mm receipt", "make this an A4 invoice".
 *
 * **A preset reshapes a layout; it does not redesign one.** That distinction is the whole
 * honesty of this file. Changing the paper from A4 to an 80mm roll through the inspector
 * leaves every zone 190mm wide on 74mm of printable width — the layout is still there and
 * none of it prints. A preset instead applies the typed settings *and* fits the geometry
 * to the new paper, so what comes back is a receipt a designer can start adjusting rather
 * than a ruin they have to rebuild.
 *
 * What it will not do is rethink the arrangement. A two-column "Bill to / Ship to" header
 * becomes two narrow columns, not the stacked pair a real receipt uses, because deciding
 * that is design and this is arithmetic. The warnings panel stays quiet about it — it
 * fits — and the designer moves it. Claiming otherwise would be the sort of preset that
 * produces something plausible and wrong.
 *
 * **Reshaping is lossy, and undo is the way back.** Widths pass through the model's
 * storage scale, so A4 → 58mm → A4 does not return the layout you started with. Every
 * preset is one `edit()`, so one `ctrl+Z` is the honest reverse.
 *
 * **It fits the width and the paper; it does not shrink heights.** Text does not get
 * smaller because the page did, so a layout whose zones are taller than the new sheet
 * cannot be made to fit by arithmetic — which is exactly what a long receipt converted to
 * A4 is. The preset does the part it can state, and the problems panel reports the page
 * break rather than this file pretending the content shrank.
 */

import { pageGeometry, printableArea, roundMm } from '@janso/ui';

import { fit, setPage, setPrint, setTheme } from './layout-edit';
import {
  type CanvasDefinition,
  type CanvasPage,
  type CanvasSection,
  type ColumnKey,
  type ItemColumn,
  NUMERIC_COLUMNS,
} from './layout-model';
import { isLineTable } from './layout-model';

export type PresetId = 'a4-invoice' | 'thermal-80' | 'thermal-58';

export type Preset = {
  readonly id: PresetId;
  readonly label: string;
  /** What it will do to this layout, in one sentence, before it is pressed. */
  readonly hint: string;
};

export const PRESETS: readonly Preset[] = [
  {
    id: 'a4-invoice',
    label: 'A4 invoice',
    hint: 'A4 portrait, 10mm margins, 9pt, three GST copies and the full column set.',
  },
  {
    id: 'thermal-80',
    label: '80mm receipt',
    hint: 'An 80mm roll, 3mm margins, 7pt, one copy and four columns. Zones are stacked.',
  },
  {
    id: 'thermal-58',
    label: '58mm receipt',
    hint: 'A 58mm roll, 2mm margins, 6.5pt, one copy and three columns. Zones are stacked.',
  },
];

/** The gap left between stacked zones on a roll: enough to read, not enough to waste. */
const STACK_GAP_MM = 2;

type Shape = {
  readonly page: Partial<CanvasPage>;
  readonly fontSizePt: number;
  readonly columns: readonly ColumnKey[];
  /** A roll is one continuous strip, so its zones are stacked rather than left in place. */
  readonly stack: boolean;
};

const SHAPES: Record<PresetId, Shape> = {
  'a4-invoice': {
    page: {
      size: 'A4',
      orientation: 'PORTRAIT',
      margins: { unit: 'mm', top: 10, right: 10, bottom: 10, left: 10 },
    },
    fontSizePt: 9,
    columns: [
      'serial_no',
      'description',
      'hsn_sac',
      'quantity',
      'unit',
      'rate',
      'taxable_value',
      'cgst_amount',
      'sgst_amount',
      'amount',
    ],
    stack: false,
  },
  'thermal-80': {
    page: {
      size: 'THERMAL_80MM',
      orientation: 'PORTRAIT',
      margins: { unit: 'mm', top: 3, right: 3, bottom: 3, left: 3 },
    },
    fontSizePt: 7,
    // Four columns is what 74mm carries legibly. A receipt that lists HSN and both GST
    // components per line is a receipt nobody can read.
    columns: ['description', 'quantity', 'rate', 'amount'],
    stack: true,
  },
  'thermal-58': {
    page: {
      size: 'THERMAL_58MM',
      orientation: 'PORTRAIT',
      margins: { unit: 'mm', top: 2, right: 2, bottom: 2, left: 2 },
    },
    fontSizePt: 6.5,
    columns: ['description', 'quantity', 'amount'],
    stack: true,
  },
};

/**
 * The relative width each column gets when a preset refits the table.
 *
 * A description needs three times what a quantity does, and no amount of available paper
 * changes that ratio — which is why these are weights and not millimetres.
 */
const COLUMN_WEIGHT: Partial<Record<ColumnKey, number>> = {
  serial_no: 0.5,
  description: 3,
  hsn_sac: 1,
  batch: 1,
  expiry: 1,
  quantity: 0.9,
  unit: 0.6,
  rate: 1.1,
  mrp: 1,
  discount: 0.9,
  taxable_value: 1.3,
  cgst_rate: 0.7,
  cgst_amount: 0.9,
  sgst_rate: 0.7,
  sgst_amount: 0.9,
  igst_rate: 0.7,
  igst_amount: 0.9,
  cess: 0.8,
  amount: 1.3,
};

/**
 * Widths for a column set inside a given table width, by weight, with the rounding drift
 * landing on the last column so the set sums to the table **exactly**. An overflowing
 * column set is the error this whole phase exists to catch, so a preset must not create
 * one — `checkLayout` is run against every preset in the tests for that reason.
 */
function fitColumns(keys: readonly ColumnKey[], tableMm: number): ItemColumn[] {
  const weights = keys.map((key) => COLUMN_WEIGHT[key] ?? 1);
  const total = weights.reduce((sum, weight) => sum + weight, 0);
  const columns: ItemColumn[] = keys.map((key, index) => ({
    key,
    widthMm: Math.max(1, roundMm((tableMm * (weights[index] ?? 1)) / total)),
    align: NUMERIC_COLUMNS.has(key) ? 'right' : undefined,
    show: true,
  }));
  const drift = roundMm(tableMm - columns.reduce((sum, column) => sum + column.widthMm, 0));
  const last = columns[columns.length - 1];
  if (last && drift !== 0) last.widthMm = Math.max(1, roundMm(last.widthMm + drift));
  return columns;
}

/**
 * Fit every zone, and the elements inside it, to a new printable width.
 *
 * Widths scale because the paper is narrower; heights do not, because text does not get
 * shorter when the page does — scaling a 4mm field to 1.5mm would produce a layout that
 * fits and cannot be read. Vertical *positions* follow the margin by translation, for the
 * same reason: stretching the gaps around boxes that kept their size is a different
 * arrangement from the one the designer made.
 *
 * On a roll the zones are stacked from the top margin down instead, since a roll is one
 * strip and the gaps an A4 sheet needs are nothing but roll to pay for.
 */
function reflow(
  layout: CanvasDefinition,
  previous: { xMm: number; yMm: number; widthMm: number },
  stack: boolean,
): CanvasDefinition {
  const area = printableArea(pageGeometry(layout.page), layout.page.margins);
  const scale = previous.widthMm > 0 ? area.widthMm / previous.widthMm : 1;

  const sections: CanvasSection[] = [];
  let cursor = area.yMm;

  for (const section of layout.sections) {
    // Capped at the printable width, not merely scaled: a layout that was *already*
    // overflowing — the state the inspector leaves behind when the paper is changed by
    // hand — would otherwise come out of a preset still overflowing, and the whole
    // promise of a preset is that what it hands back fits.
    const widthMm = Math.max(1, Math.min(roundMm(section.widthMm * scale), area.widthMm));
    const xMm = roundMm(area.xMm + (section.xMm - previous.xMm) * scale);

    sections.push({
      ...section,
      widthMm,
      xMm: Math.min(Math.max(area.xMm, xMm), roundMm(area.xMm + area.widthMm - widthMm)),
      /*
       * Translated with the printable area, not scaled. Scaling vertical positions while
       * leaving heights alone would stretch the gaps and not the boxes, which is a
       * different arrangement from the one the designer made. Translating keeps it and
       * only follows the margin: a roll's 3mm top margin becoming A4's 10mm would
       * otherwise leave the first zone 7mm above the paper's printable edge.
       */
      yMm: stack ? roundMm(cursor) : roundMm(area.yMm + (section.yMm - previous.yMm)),
      elements: section.elements.map((element) =>
        fit(
          {
            ...element,
            xMm: roundMm(element.xMm * scale),
            widthMm: Math.max(1, roundMm(element.widthMm * scale)),
            // An item table is as wide as its zone, and its columns are refitted below.
            ...(isLineTable(element.type) ? { xMm: 0, widthMm } : {}),
          },
          { widthMm, heightMm: section.heightMm },
        ),
      ),
    });

    cursor += section.heightMm + STACK_GAP_MM;
  }

  return { ...layout, sections };
}

/**
 * Scale every element's own type size by the same ratio the preset applies to the base.
 *
 * Without this a preset is internally inconsistent: `thermal-80` takes the document's base
 * from 9pt to 7pt and a 14pt company name stays 14pt, in a box that just went from 96mm
 * wide to 37mm. Phase 8's screenshots showed exactly that — "Nandini Trading Company"
 * clipped to "Nandini" on the roll — and no geometry check could have caught it, because
 * the *box* fits perfectly; it is the text inside it that does not.
 *
 * Clamped to the same 4-24pt range `setTheme` enforces, so a deep reduction cannot produce
 * type below what a printer resolves.
 */
function rescaleType(layout: CanvasDefinition, ratio: number): CanvasDefinition {
  if (ratio === 1) return layout;
  return {
    ...layout,
    sections: layout.sections.map((section) => ({
      ...section,
      elements: section.elements.map((element) =>
        element.style?.fontSizePt
          ? {
              ...element,
              style: {
                ...element.style,
                fontSizePt: Math.min(24, Math.max(4, roundMm(element.style.fontSizePt * ratio))),
              },
            }
          : element,
      ),
    })),
  };
}

/** Refit the columns of every item table to its new width and the preset's column set. */
function retable(layout: CanvasDefinition, keys: readonly ColumnKey[]): CanvasDefinition {
  return {
    ...layout,
    sections: layout.sections.map((section) => ({
      ...section,
      elements: section.elements.map((element) =>
        element.type === 'ITEM_TABLE'
          ? { ...element, columns: fitColumns(keys, element.widthMm) }
          : element,
      ),
    })),
  };
}

/**
 * Apply a preset, returning the same layout object when nothing would change.
 *
 * Settings first, then geometry: the reflow has to measure against the *new* printable
 * area, and the margins are only clamped to the new paper once `setPage` has seen it.
 */
export function applyPreset(layout: CanvasDefinition, id: PresetId): CanvasDefinition {
  const shape = SHAPES[id];
  if (!shape) return layout;

  const before = printableArea(pageGeometry(layout.page), layout.page.margins);

  let next = setPage(layout, shape.page);
  next = setTheme(next, { fontSizePt: shape.fontSizePt });
  next = setPrint(next, {
    // A roll prints one copy: there is no transporter's copy of a counter receipt.
    copies: shape.stack ? ['ORIGINAL_FOR_RECIPIENT'] : layout.print.copies,
    copyMarkPosition: shape.stack ? 'top-center' : (layout.print.copyMarkPosition ?? 'top-right'),
    prePrintedStationery: shape.stack ? false : layout.print.prePrintedStationery,
  });
  next = rescaleType(next, shape.fontSizePt / layout.theme.fontSizePt);
  next = reflow(next, before, shape.stack);
  next = retable(next, shape.columns);

  return next;
}

/**
 * Which preset's paper this layout is already on, for marking the current one.
 *
 * Paper only. It deliberately does not check margins, type size or columns: a designer who
 * applied the 80mm preset and then set 4mm margins is still working on an 80mm receipt,
 * and a control that stopped saying so would be describing the preset rather than the
 * page. `null` means paper nothing offers — a custom size, or Letter.
 */
export function activePreset(layout: CanvasDefinition): PresetId | null {
  return PRESETS.find((preset) => SHAPES[preset.id].page.size === layout.page.size)?.id ?? null;
}
