/**
 * Editing the layout: pure functions in, new layout out.
 *
 * No framework, no mutation, no component state. Three reasons that matters here:
 *
 *   **The rules live in one place.** "A margin cannot eat the page", "an element stays
 *   inside its zone", "a column set cannot exceed its table" are the kind of rule that
 *   gets re-implemented slightly differently in each control that touches it. Here they
 *   are written once and tested without rendering anything.
 *
 *   **Undo is a list of these.** Phase 5 adds history; a reducer over immutable layouts
 *   gets it almost free, while in-place mutation would make it a rewrite.
 *
 *   **The service will validate the same shapes.** Clamping here means the editor cannot
 *   compose a layout the API would reject — the designer finds out at the control, not at
 *   the save.
 */

import { pageGeometry, roundMm } from '@janso/ui';

import {
  type BindingPath,
  type CanvasDefinition,
  type CanvasElement,
  type CanvasMargins,
  type CanvasPage,
  type CanvasSection,
  type CanvasTheme,
  COLUMN_KEYS,
  type ElementStyle,
  type ItemColumn,
  type CopyLabel,
  COPY_LABELS,
  type PrintOptions,
  TOTALS_ROWS,
  type TotalsRow,
  type LineProfile,
  DEFAULT_COLUMNS,
  DEFAULT_ACCOUNT_COLUMNS,
} from './layout-model';

/** Paper dimensions the page size implies, in millimetres. */
/**
 * The page's box after its size, custom dimensions and orientation.
 *
 * Delegated to `@janso/ui`, which owns the paper table — a second list of sheet
 * dimensions is a list that can disagree with the one the canvas draws, and "the editor
 * says 210mm but the preview is 215.9mm" is not a bug anyone finds by looking. It also
 * carries `continuous`, so the roll rule (a roll has a fixed width and never rotates)
 * is stated once rather than hand-coded per caller.
 */
export function pageBox(page: CanvasPage): { widthMm: number; heightMm: number } {
  const { widthMm, heightMm } = pageGeometry(page);
  return { widthMm, heightMm };
}

export function clamp(value: number, min: number, max: number): number {
  if (!Number.isFinite(value)) return min;
  return Math.min(max, Math.max(min, roundMm(value)));
}

/* ---------------------------------------------------------------- page */

export function setPage(layout: CanvasDefinition, patch: Partial<CanvasPage>): CanvasDefinition {
  const page = { ...layout.page, ...patch };
  const box = pageBox(page);
  return {
    ...layout,
    page: {
      ...page,
      gridStepMm: clamp(page.gridStepMm, 1, 50),
      // Margins are re-clamped against the new paper: switching A4 → 58mm roll with 20mm
      // side margins would otherwise leave a printable width of 18mm and no warning.
      margins: clampMargins(page.margins, box),
    },
  };
}

export function setMargins(
  layout: CanvasDefinition,
  patch: Partial<Omit<CanvasMargins, 'unit'>>,
): CanvasDefinition {
  const box = pageBox(layout.page);
  return {
    ...layout,
    page: {
      ...layout.page,
      margins: clampMargins({ ...layout.page.margins, ...patch }, box),
    },
  };
}

/**
 * Margins must leave something to print on. Each pair is capped so the printable area
 * keeps at least 10mm — a page with a 2mm printable strip is not a layout, it is a bug
 * that only shows up on paper.
 */
function clampMargins(
  margins: CanvasMargins,
  box: { widthMm: number; heightMm: number },
): CanvasMargins {
  const maxSide = Math.max(0, (box.widthMm - 10) / 2);
  const maxEnd = Math.max(0, (box.heightMm - 10) / 2);
  return {
    unit: 'mm',
    top: clamp(margins.top, 0, maxEnd),
    bottom: clamp(margins.bottom, 0, maxEnd),
    left: clamp(margins.left, 0, maxSide),
    right: clamp(margins.right, 0, maxSide),
  };
}

export function setTheme(layout: CanvasDefinition, patch: Partial<CanvasTheme>): CanvasDefinition {
  return {
    ...layout,
    theme: {
      ...layout.theme,
      ...patch,
      fontSizePt: clamp(patch.fontSizePt ?? layout.theme.fontSizePt, 4, 24),
    },
  };
}

export function setPrint(
  layout: CanvasDefinition,
  patch: Partial<PrintOptions>,
): CanvasDefinition {
  return { ...layout, print: { ...layout.print, ...patch } };
}

/* ---------------------------------------------------------------- zones */

export function updateSection(
  layout: CanvasDefinition,
  sectionId: string,
  patch: Partial<Omit<CanvasSection, 'id' | 'elements'>>,
): CanvasDefinition {
  const box = pageBox(layout.page);
  return {
    ...layout,
    sections: layout.sections.map((section) => {
      if (section.id !== sectionId) return section;
      const next = { ...section, ...patch };
      // A zone stays on the page; its elements are re-clamped against its new box below.
      const widthMm = clamp(next.widthMm, 1, box.widthMm);
      const heightMm = clamp(next.heightMm, 1, box.heightMm);
      const xMm = clamp(next.xMm, 0, box.widthMm - widthMm);
      const yMm = clamp(next.yMm, 0, box.heightMm - heightMm);
      return {
        ...next,
        xMm,
        yMm,
        widthMm,
        heightMm,
        elements: next.elements.map((element) => fit(element, { widthMm, heightMm })),
      };
    }),
  };
}

/* ---------------------------------------------------------------- elements */

export function updateElement(
  layout: CanvasDefinition,
  elementId: string,
  patch: Partial<Omit<CanvasElement, 'id' | 'type'>>,
): CanvasDefinition {
  return {
    ...layout,
    sections: layout.sections.map((section) => {
      if (!section.elements.some((element) => element.id === elementId)) return section;
      return {
        ...section,
        elements: section.elements.map((element) =>
          element.id === elementId ? fit({ ...element, ...patch }, section) : element,
        ),
      };
    }),
  };
}

/** Merge a style patch, dropping a property the caller clears rather than storing `null`. */
export function setElementStyle(
  layout: CanvasDefinition,
  elementId: string,
  patch: ElementStyle,
): CanvasDefinition {
  return {
    ...layout,
    sections: layout.sections.map((section) => ({
      ...section,
      elements: section.elements.map((element) => {
        if (element.id !== elementId) return element;
        const style: ElementStyle = { ...element.style, ...patch };
        for (const [key, value] of Object.entries(patch)) {
          if (value === undefined) delete style[key as keyof ElementStyle];
        }
        return { ...element, style };
      }),
    })),
  };
}

/**
 * An element stays inside its zone.
 *
 * Not a cosmetic rule: a zone is what the renderer lays out and clips, so an element that
 * leaves it is invisible on screen and absent on paper — the worst class of layout bug,
 * because the editor looks correct.
 */
export function fit(
  element: CanvasElement,
  zone: { widthMm: number; heightMm: number },
): CanvasElement {
  const widthMm = clamp(element.widthMm, 1, zone.widthMm);
  const heightMm = clamp(element.heightMm, 1, zone.heightMm);
  return {
    ...element,
    widthMm,
    heightMm,
    xMm: clamp(element.xMm, 0, zone.widthMm - widthMm),
    yMm: clamp(element.yMm, 0, zone.heightMm - heightMm),
  };
}

/* ---------------------------------------------------------------- columns */

/**
 * Change one column of an item table.
 *
 * Widths are capped to what is left of the table, so a column set can never overflow —
 * the error that looks right on screen and comes out of a printer with a missing column.
 */
export function updateColumn(
  layout: CanvasDefinition,
  elementId: string,
  columnKey: ItemColumn['key'],
  patch: Partial<Omit<ItemColumn, 'key'>>,
): CanvasDefinition {
  return {
    ...layout,
    sections: layout.sections.map((section) => ({
      ...section,
      elements: section.elements.map((element) => {
        if (element.id !== elementId || !element.columns) return element;
        // What the *other* shown columns already spend. Their own `show` decides that —
        // the patch belongs to the target column alone.
        const others = element.columns
          .filter((column) => column.key !== columnKey && column.show)
          .reduce((sum, column) => sum + column.widthMm, 0);
        const headroom = Math.max(1, element.widthMm - others);
        return {
          ...element,
          columns: element.columns.map((column) =>
            column.key === columnKey
              ? {
                  ...column,
                  ...patch,
                  widthMm: clamp(patch.widthMm ?? column.widthMm, 1, headroom),
                }
              : column,
          ),
        };
      }),
    })),
  };
}

/** Millimetres a table's shown columns use, and what it has to spend. */
export function columnBudget(element: CanvasElement): { usedMm: number; totalMm: number } {
  const usedMm = (element.columns ?? [])
    .filter((column) => column.show)
    .reduce((sum, column) => sum + column.widthMm, 0);
  return { usedMm: roundMm(usedMm), totalMm: element.widthMm };
}

/* ---------------------------------------------------------------- column designer */

/** Sixteen is already more columns than an A4 invoice can read; a guard, not a goal. */
export const MAX_COLUMNS = 16;

/** Width a newly added column starts at, by what its heading usually needs. */
const COLUMN_DEFAULT_MM: Partial<Record<ItemColumn['key'], number>> = {
  serial_no: 8,
  description: 50,
  hsn_sac: 16,
  batch: 18,
  expiry: 16,
  quantity: 14,
  unit: 10,
  rate: 18,
  mrp: 18,
  discount: 14,
  taxable_value: 22,
  cgst_rate: 12,
  cgst_amount: 14,
  sgst_rate: 12,
  sgst_amount: 14,
  igst_rate: 12,
  igst_amount: 14,
  cess: 12,
  amount: 22,
};

function withColumns(
  layout: CanvasDefinition,
  elementId: string,
  change: (columns: ItemColumn[], element: CanvasElement) => ItemColumn[],
): CanvasDefinition {
  return {
    ...layout,
    sections: layout.sections.map((section) => ({
      ...section,
      elements: section.elements.map((element) =>
        element.id === elementId && element.columns
          ? { ...element, columns: change([...element.columns], element) }
          : element,
      ),
    })),
  };
}

/**
 * Add a column the table does not already carry.
 *
 * It arrives **hidden when there is no room**, rather than being refused or silently
 * shrinking its neighbours: a designer who adds Batch to a full table wants to see it in
 * the list and decide what to give up, not watch five other columns change width.
 */
export function addColumn(
  layout: CanvasDefinition,
  elementId: string,
  key: ItemColumn['key'],
): CanvasDefinition {
  return withColumns(layout, elementId, (columns, element) => {
    if (columns.some((column) => column.key === key)) return columns;
    if (columns.length >= MAX_COLUMNS) return columns;
    const spent = columns
      .filter((column) => column.show)
      .reduce((sum, column) => sum + column.widthMm, 0);
    const wanted = COLUMN_DEFAULT_MM[key] ?? 16;
    const headroom = element.widthMm - spent;
    const fits = headroom >= wanted;
    return [
      ...columns,
      { key, widthMm: fits ? wanted : Math.max(1, Math.min(wanted, headroom)), show: fits },
    ];
  });
}

/**
 * Remove a column from the design.
 *
 * Distinct from hiding one: hiding keeps its width and heading for later, removing forgets
 * both. "Not on this invoice" and "not in this design" are different decisions.
 */
export function removeColumn(
  layout: CanvasDefinition,
  elementId: string,
  key: ItemColumn['key'],
): CanvasDefinition {
  return withColumns(layout, elementId, (columns) =>
    // Never leave a table with nothing in it: the renderer would print an empty frame and
    // the inspector would have no row to add one back from.
    columns.length <= 1 ? columns : columns.filter((column) => column.key !== key),
  );
}

/** Move a column one place. The list order is the printed order. */
export function moveColumn(
  layout: CanvasDefinition,
  elementId: string,
  key: ItemColumn['key'],
  direction: 'left' | 'right',
): CanvasDefinition {
  return withColumns(layout, elementId, (columns) => {
    const index = columns.findIndex((column) => column.key === key);
    const target = direction === 'left' ? index - 1 : index + 1;
    if (index < 0 || target < 0 || target >= columns.length) return columns;
    const next = [...columns];
    const [moved] = next.splice(index, 1);
    if (moved) next.splice(target, 0, moved);
    return next;
  });
}

/**
 * Scale the shown columns to fill the table exactly.
 *
 * Proportional, so the designer's relative choices survive — widening a table should not
 * make every column equal. The rounding drift lands on the widest column, where a tenth of
 * a millimetre is least visible.
 */
export function distributeColumns(layout: CanvasDefinition, elementId: string): CanvasDefinition {
  return withColumns(layout, elementId, (columns, element) => {
    const shown = columns.filter((column) => column.show);
    const spent = shown.reduce((sum, column) => sum + column.widthMm, 0);
    if (shown.length === 0 || spent <= 0) return columns;

    const factor = element.widthMm / spent;
    const scaled = columns.map((column) =>
      column.show
        ? { ...column, widthMm: Math.max(1, roundMm(column.widthMm * factor)) }
        : column,
    );
    const drift =
      element.widthMm -
      scaled.filter((column) => column.show).reduce((sum, column) => sum + column.widthMm, 0);
    if (Math.abs(drift) < 0.05) return scaled;

    const widest = scaled
      .filter((column) => column.show)
      .reduce((champion, column) => (column.widthMm > champion.widthMm ? column : champion));
    return scaled.map((column) =>
      column.key === widest.key
        ? { ...column, widthMm: Math.max(1, roundMm(column.widthMm + drift)) }
        : column,
    );
  });
}

/** The keys a table does not carry yet, in catalogue order, for the add menu. */
/** Columns a product line has and an account line does not: they belong to the product table. */
const PRODUCT_ONLY = new Set<ItemColumn['key']>(['hsn_sac', 'batch', 'expiry', 'quantity', 'unit', 'rate', 'mrp']);

export function availableColumns(element: CanvasElement): ItemColumn['key'][] {
  const present = new Set((element.columns ?? []).map((column) => column.key));
  // An account line has a ledger and no quantity; a product line has a quantity and no ledger.
  const fits = (key: ItemColumn['key']) =>
    element.type === 'ACCOUNT_TABLE' ? !PRODUCT_ONLY.has(key) : key !== 'account';
  return COLUMN_KEYS.filter((key) => !present.has(key) && fits(key));
}

/* ---------------------------------------------------------------- totals builder */

function withTotals(
  layout: CanvasDefinition,
  elementId: string,
  change: (rows: TotalsRow[]) => TotalsRow[],
): CanvasDefinition {
  return {
    ...layout,
    sections: layout.sections.map((section) => ({
      ...section,
      elements: section.elements.map((element) =>
        element.id === elementId && element.totalsRows
          ? { ...element, totalsRows: change([...element.totalsRows]) }
          : element,
      ),
    })),
  };
}

export function addTotalsRow(
  layout: CanvasDefinition,
  elementId: string,
  row: TotalsRow,
): CanvasDefinition {
  return withTotals(layout, elementId, (rows) => (rows.includes(row) ? rows : [...rows, row]));
}

/**
 * Remove a totals row.
 *
 * Unlike a column, a totals block may legitimately end up empty — a delivery challan
 * prints no money at all — so there is no floor here.
 */
export function removeTotalsRow(
  layout: CanvasDefinition,
  elementId: string,
  row: TotalsRow,
): CanvasDefinition {
  return withTotals(layout, elementId, (rows) => rows.filter((candidate) => candidate !== row));
}

export function moveTotalsRow(
  layout: CanvasDefinition,
  elementId: string,
  row: TotalsRow,
  direction: 'up' | 'down',
): CanvasDefinition {
  return withTotals(layout, elementId, (rows) => {
    const index = rows.indexOf(row);
    const target = direction === 'up' ? index - 1 : index + 1;
    if (index < 0 || target < 0 || target >= rows.length) return rows;
    const next = [...rows];
    const [moved] = next.splice(index, 1);
    if (moved) next.splice(target, 0, moved);
    return next;
  });
}

/** The rows a totals block does not print yet, in catalogue order. */
export function availableTotalsRows(element: CanvasElement): TotalsRow[] {
  const present = new Set(element.totalsRows ?? []);
  return TOTALS_ROWS.filter((row) => !present.has(row));
}

/**
 * Move the boundary between a column and the next shown one.
 *
 * Different from `updateColumn`, deliberately. Typing a width means "make this column
 * 52mm", so it is capped at the free space. Dragging a divider means "move this boundary",
 * so the millimetres come from the column on the other side — which is what a table
 * divider does everywhere else, and without it a drag on an exactly-full table refuses to
 * move at all.
 *
 * The last shown column has no neighbour to trade with, so its boundary is the table's
 * edge and it falls back to the capped behaviour.
 */
export function resizeColumnBoundary(
  layout: CanvasDefinition,
  elementId: string,
  key: ItemColumn['key'],
  widthMm: number,
): CanvasDefinition {
  return withColumns(layout, elementId, (columns, element) => {
    const shown = columns.filter((column) => column.show);
    const index = shown.findIndex((column) => column.key === key);
    if (index < 0) return columns;

    const current = shown[index]!;
    const neighbour = shown[index + 1];
    if (!neighbour) {
      // No one to trade with: cap at what the other columns leave free.
      const others = shown
        .filter((column) => column.key !== key)
        .reduce((sum, column) => sum + column.widthMm, 0);
      const capped = clamp(widthMm, 1, Math.max(1, element.widthMm - others));
      return columns.map((column) => (column.key === key ? { ...column, widthMm: capped } : column));
    }

    // The pair's combined width is fixed, so the table's total never changes.
    const pair = current.widthMm + neighbour.widthMm;
    const next = clamp(widthMm, 1, pair - 1);
    return columns.map((column) => {
      if (column.key === key) return { ...column, widthMm: next };
      if (column.key === neighbour.key) {
        return { ...column, widthMm: roundMm(pair - next) };
      }
      return column;
    });
  });
}

/* ---------------------------------------------------------------- ids */

/**
 * An unused id derived from a readable base, so the tree stays readable.
 *
 * One definition because two would drift: `duplicateElements` needs it for a copy and
 * `placeField` needs it for a new field, and an editor that generates ids two ways
 * eventually generates the same one twice.
 */
export function freeId(taken: ReadonlySet<string>, base: string): string {
  if (!taken.has(base)) return base;
  for (let suffix = 2; ; suffix += 1) {
    const candidate = `${base}-${suffix}`;
    if (!taken.has(candidate)) return candidate;
  }
}

/** Every element id in the layout, for deriving one that is free. */
export function elementIds(layout: CanvasDefinition): Set<string> {
  return new Set(
    layout.sections.flatMap((section) => section.elements.map((element) => element.id)),
  );
}

/* ---------------------------------------------------------------- placing */

/** The size a placed field starts at: a line of text, two thirds of a narrow zone. */
const PLACED_WIDTH_MM = 60;
const PLACED_HEIGHT_MM = 5;

/** A readable label from a binding path: `voucher.document_number` → "Document number". */
export function bindingLabel(path: string): string {
  const leaf = path.split('.').pop() ?? path;
  const words = leaf.replace(/_/g, ' ');
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/**
 * Put a bound field into a zone.
 *
 * It lands **below whatever is already there**, because that is where a designer building
 * a block of details is looking, and because dropping it at the origin would hide it under
 * the first element every time. When the zone has no room left it is clamped to the bottom
 * edge and overlaps — deliberately visible rather than silently refused, since it arrives
 * selected and one drag moves it. A zone is never grown to fit: its height is the
 * designer's decision and a palette click is not the place to overrule it.
 *
 * Returns the new id so the caller can select it, and the original layout when the zone
 * does not exist.
 */
export function placeField(
  layout: CanvasDefinition,
  sectionId: string,
  bindingPath: BindingPath,
  options: { label?: string; at?: ZonePoint } = {},
): { layout: CanvasDefinition; id: string | null } {
  const leaf = bindingPath.split('.').pop() ?? 'field';
  return insert(layout, sectionId, `el-${leaf.replace(/_/g, '-')}`, options.at, {
    type: 'FIELD_BINDING',
    widthMm: PLACED_WIDTH_MM,
    heightMm: PLACED_HEIGHT_MM,
    bindingPath,
    label: options.label ?? bindingLabel(bindingPath),
    style: {},
  });
}

/** A point inside a zone, in millimetres from the zone's top-left corner. */
export type ZonePoint = { xMm: number; yMm: number };

/**
 * The plain objects a designer adds by hand, beside the bound fields: words that never
 * change, a rule between blocks, a ruled box, and a place to sign. Each starts at a size
 * that reads as itself on an A4 page and is resized like anything else.
 */
export const ADDABLE_ELEMENTS = {
  TEXT: { label: 'Text', hint: 'Words that print on every document', widthMm: 60, heightMm: 6, content: 'Text', style: {} },
  DIVIDER: { label: 'Line', hint: 'A horizontal rule between blocks', widthMm: 80, heightMm: 1, style: {} },
  SHAPE: { label: 'Box', hint: 'A ruled box to group or frame', widthMm: 40, heightMm: 20, style: { borderWidthMm: 0.3, borderStyle: 'solid' } },
  SIGNATURE: { label: 'Signature', hint: 'The signatory line and its caption', widthMm: 50, heightMm: 18, content: 'Authorised signatory', style: {} },
  ITEM_TABLE: { label: 'Product table', hint: 'The bill’s products, one row each', widthMm: 190, heightMm: 40, style: {} },
  ACCOUNT_TABLE: { label: 'Accounts table', hint: 'Expense and service lines with their ledger', widthMm: 190, heightMm: 30, style: {} },
  TOTALS_BLOCK: { label: 'Totals', hint: 'Subtotal, taxes, round off and total', widthMm: 70, heightMm: 26, style: {} },
  TAX_SUMMARY: { label: 'Tax summary', hint: 'Tax by rate, with its taxable value', widthMm: 100, heightMm: 20, style: {} },
} as const satisfies Record<string, { label: string; hint: string; widthMm: number; heightMm: number; content?: string; style: ElementStyle }>;

/** Which objects a design for these lines offers: products and accounts each have their table. */
export function addableFor(lineProfile: LineProfile | undefined): AddableKind[] {
  return (Object.keys(ADDABLE_ELEMENTS) as AddableKind[]).filter((kind) =>
    kind === 'ITEM_TABLE' ? lineProfile !== 'ACCOUNTS' : kind === 'ACCOUNT_TABLE' ? lineProfile !== 'ITEMS' : true,
  );
}

/** A column set, rescaled to a table's width and never wider than it. */
function fitTo(columns: readonly ItemColumn[], widthMm: number): ItemColumn[] {
  const total = columns.reduce((sum, column) => sum + column.widthMm, 0);
  return columns.map((column) => ({ ...column, widthMm: Math.floor((column.widthMm * widthMm * 10) / total) / 10 }));
}
export type AddableKind = keyof typeof ADDABLE_ELEMENTS;

/** Add one of the plain objects to a zone: at a point when dropped, below the rest when clicked. */
export function placeElement(
  layout: CanvasDefinition,
  sectionId: string,
  kind: AddableKind,
  options: { at?: ZonePoint } = {},
): { layout: CanvasDefinition; id: string | null } {
  const spec: { widthMm: number; heightMm: number; content?: string; style: ElementStyle } = ADDABLE_ELEMENTS[kind];
  const zone = layout.sections.find((section) => section.id === sectionId);
  // A line table spans its zone and its columns fill it; the rest keep their own size.
  const table = kind === 'ITEM_TABLE' || kind === 'ACCOUNT_TABLE';
  const widthMm = table ? (zone?.widthMm ?? spec.widthMm) : spec.widthMm;
  return insert(layout, sectionId, `el-${kind.toLowerCase().replace(/_/g, '-')}`, table && options.at ? { xMm: 0, yMm: options.at.yMm } : options.at, {
    type: kind,
    widthMm,
    heightMm: spec.heightMm,
    ...(spec.content !== undefined ? { content: spec.content } : {}),
    style: { ...spec.style },
    ...(kind === 'ITEM_TABLE' ? { columns: fitTo(DEFAULT_COLUMNS, widthMm) } : {}),
    ...(kind === 'ACCOUNT_TABLE' ? { columns: fitTo(DEFAULT_ACCOUNT_COLUMNS, widthMm) } : {}),
    ...(kind === 'TOTALS_BLOCK' ? { totalsRows: ['subtotal', 'cgst', 'sgst', 'round_off', 'grand_total'] as TotalsRow[] } : {}),
    ...(kind === 'TAX_SUMMARY' ? { taxGrouping: 'by_rate' as const } : {}),
  });
}

/**
 * Put a new element into a zone and return its id, so the caller can select it.
 *
 * Dropped, it lands where it was let go. Clicked, it lands **below whatever is already
 * there**, because that is where a designer building a block of details is looking, and
 * because the origin would hide it under the first element every time. Either way it is
 * clamped inside the zone; a zone is never grown to fit, since its height is the
 * designer's decision.
 */
function insert(
  layout: CanvasDefinition,
  sectionId: string,
  base: string,
  at: ZonePoint | undefined,
  element: Omit<CanvasElement, 'id' | 'xMm' | 'yMm'>,
): { layout: CanvasDefinition; id: string | null } {
  const section = layout.sections.find((candidate) => candidate.id === sectionId);
  if (!section) return { layout, id: null };
  const id = freeId(elementIds(layout), base);
  const below = section.elements.reduce(
    (lowest, existing) => Math.max(lowest, existing.yMm + existing.heightMm),
    0,
  );
  const placed = fit(
    {
      ...element,
      id,
      widthMm: Math.min(element.widthMm, section.widthMm),
      xMm: roundMm(at?.xMm ?? 0),
      yMm: roundMm(at ? at.yMm : below > 0 ? below + 1 : 0),
    },
    section,
  );
  return {
    layout: {
      ...layout,
      sections: layout.sections.map((candidate) =>
        candidate.id === sectionId
          ? { ...candidate, elements: [...candidate.elements, placed] }
          : candidate,
      ),
    },
    id,
  };
}

/** The binding paths a layout already prints, so the palette can say so. */
export function boundPaths(layout: CanvasDefinition): Set<string> {
  const paths = new Set<string>();
  for (const section of layout.sections) {
    for (const element of section.elements) {
      if (element.bindingPath) paths.add(element.bindingPath);
    }
  }
  return paths;
}

/* ---------------------------------------------------------------- copies */

/**
 * Add a printed copy.
 *
 * The order is the order they come off the printer, and the mark on each is what makes a
 * GST invoice set legal — so this is a list, not a count.
 */
export function addCopy(layout: CanvasDefinition, copy: CopyLabel): CanvasDefinition {
  if (layout.print.copies.includes(copy)) return layout;
  return setPrint(layout, { copies: [...layout.print.copies, copy] });
}

/**
 * Remove a printed copy, never the last one.
 *
 * A template that prints no copies prints nothing, and the control that would add one back
 * reads the list it just emptied. Same rule as a table's last column.
 */
export function removeCopy(layout: CanvasDefinition, copy: CopyLabel): CanvasDefinition {
  if (layout.print.copies.length <= 1 || !layout.print.copies.includes(copy)) return layout;
  return setPrint(layout, { copies: layout.print.copies.filter((entry) => entry !== copy) });
}

/** Move a copy one place in the printed order. */
export function moveCopy(
  layout: CanvasDefinition,
  copy: CopyLabel,
  direction: 'up' | 'down',
): CanvasDefinition {
  const copies = layout.print.copies;
  const index = copies.indexOf(copy);
  const target = direction === 'up' ? index - 1 : index + 1;
  if (index < 0 || target < 0 || target >= copies.length) return layout;
  const next = [...copies];
  const [moved] = next.splice(index, 1);
  if (moved) next.splice(target, 0, moved);
  return setPrint(layout, { copies: next });
}

/** The copies this template does not yet print, for the add menu. */
export function availableCopies(layout: CanvasDefinition): CopyLabel[] {
  return (Object.keys(COPY_LABELS) as CopyLabel[]).filter(
    (copy) => !layout.print.copies.includes(copy),
  );
}

/* ---------------------------------------------------------------- roll length */

/**
 * The page height to *draw* for continuous stock.
 *
 * A roll has no page: `PAPER_SIZES` gives it a nominal length because a canvas has to be
 * some size, and a receipt is however long its content is. Drawing the nominal 200mm and
 * letting a stacked layout hang off the bottom reads as a broken editor rather than as a
 * long receipt — phase 8's screenshots showed the tax summary of an 80mm reflow sitting on
 * the backdrop below the sheet.
 *
 * So the sheet grows to the content, plus the bottom margin, and never shrinks below the
 * nominal length. This is a *display* measurement: `layout.page` keeps the nominal height,
 * because the roll's declared stock is what the renderer is told about, and `checkLayout`
 * deliberately asks no question about the bottom of a roll.
 */
export function drawnPageHeightMm(layout: CanvasDefinition): number {
  const geometry = pageGeometry(layout.page);
  if (!geometry.continuous) return geometry.heightMm;
  const content = layout.sections.reduce(
    (lowest, section) => Math.max(lowest, section.yMm + section.heightMm),
    0,
  );
  return Math.max(geometry.heightMm, roundMm(content + layout.page.margins.bottom));
}
