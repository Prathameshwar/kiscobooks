/**
 * Paper geometry for the invoice designer.
 *
 * Everything here is in **millimetres**, which is also how the layout model stores
 * geometry and how CSS's own `mm` unit works — so a page declared at `210mm` and an
 * element at `left: 12mm` need no arithmetic to be print-accurate. The only conversion
 * that exists is for the rulers, which draw in pixels.
 *
 * The CSS reference pixel is 1/96 inch, so 1mm is 96/25.4 px at 100% zoom. That is a
 * constant of the CSS object model, not a device property: it is what the browser will
 * use when it lays the page out, which is exactly what a WYSIWYG canvas must agree with.
 */

/** CSS reference pixels per millimetre at 100% zoom. */
export const PX_PER_MM = 96 / 25.4;

export type PaperSize = 'A4' | 'LETTER' | 'A5' | 'THERMAL_80MM' | 'THERMAL_58MM' | 'CUSTOM';
export type Orientation = 'PORTRAIT' | 'LANDSCAPE';

export type PaperDefinition = {
  /** Short label for a control: "A4", "80mm roll". */
  readonly label: string;
  readonly widthMm: number;
  readonly heightMm: number;
  /**
   * A roll, not a sheet. Height is whatever the content needs, so the editor shows a
   * nominal length and never draws a page break.
   */
  readonly continuous: boolean;
};

export const PAPER_SIZES: Record<Exclude<PaperSize, 'CUSTOM'>, PaperDefinition> = {
  A4: { label: 'A4', widthMm: 210, heightMm: 297, continuous: false },
  LETTER: { label: 'Letter', widthMm: 215.9, heightMm: 279.4, continuous: false },
  A5: { label: 'A5', widthMm: 148, heightMm: 210, continuous: false },
  // Roll stock is quoted by its width; the nominal length is a screenful of receipt.
  THERMAL_80MM: { label: '80mm roll', widthMm: 80, heightMm: 200, continuous: true },
  THERMAL_58MM: { label: '58mm roll', widthMm: 58, heightMm: 160, continuous: true },
};

export type Margins = {
  readonly top: number;
  readonly right: number;
  readonly bottom: number;
  readonly left: number;
};

export const DEFAULT_MARGINS: Margins = { top: 10, right: 10, bottom: 10, left: 10 };

export type PaperSpec = {
  readonly size: PaperSize;
  readonly orientation?: Orientation;
  /** Required for `CUSTOM`; ignored otherwise. */
  readonly widthMm?: number;
  readonly heightMm?: number;
};

export type PageGeometry = {
  readonly widthMm: number;
  readonly heightMm: number;
  readonly continuous: boolean;
  readonly label: string;
};

/**
 * The page's millimetre box, after orientation.
 *
 * A landscape *roll* is refused rather than silently rotated: 80mm thermal stock has a
 * fixed width by definition, and a rotated roll is a different product.
 */
export function pageGeometry(spec: PaperSpec): PageGeometry {
  const definition =
    spec.size === 'CUSTOM'
      ? {
          label: 'Custom',
          widthMm: spec.widthMm ?? PAPER_SIZES.A4.widthMm,
          heightMm: spec.heightMm ?? PAPER_SIZES.A4.heightMm,
          continuous: false,
        }
      : PAPER_SIZES[spec.size];

  const landscape = spec.orientation === 'LANDSCAPE' && !definition.continuous;
  return {
    label: definition.label,
    continuous: definition.continuous,
    widthMm: landscape ? definition.heightMm : definition.widthMm,
    heightMm: landscape ? definition.widthMm : definition.heightMm,
  };
}

export type Rect = {
  readonly xMm: number;
  readonly yMm: number;
  readonly widthMm: number;
  readonly heightMm: number;
};

/**
 * Whether two millimetre boxes share any area at all.
 *
 * Touching edge to edge is *not* overlapping — the comparison is strict on every side.
 * That is the rule a marquee needs (a band of zero width catches nothing) and the rule a
 * layout check needs (two zones stacked flush are correct, not a collision), and having
 * them agree is the point of there being one of these.
 */
export function rectsOverlap(a: Rect, b: Rect): boolean {
  return (
    a.xMm < b.xMm + b.widthMm &&
    a.xMm + a.widthMm > b.xMm &&
    a.yMm < b.yMm + b.heightMm &&
    a.yMm + a.heightMm > b.yMm
  );
}

/**
 * The area that actually prints. Content outside it is the single most common reason a
 * designed invoice comes out of a printer wrong, so the canvas draws this and later
 * phases warn about elements that leave it.
 */
export function printableArea(page: PageGeometry, margins: Margins): Rect {
  const widthMm = Math.max(0, page.widthMm - margins.left - margins.right);
  const heightMm = Math.max(0, page.heightMm - margins.top - margins.bottom);
  return { xMm: margins.left, yMm: margins.top, widthMm, heightMm };
}

/** Zoom presets, in the order a control steps through them. */
export const ZOOM_STEPS = [0.25, 0.5, 0.75, 1, 1.25, 1.5, 2] as const;
export const MIN_ZOOM = ZOOM_STEPS[0];
export const MAX_ZOOM = ZOOM_STEPS[ZOOM_STEPS.length - 1] as number;

export function clampZoom(zoom: number): number {
  if (!Number.isFinite(zoom)) return 1;
  return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, zoom));
}

/** The next preset above `zoom`, or `zoom` itself when it is already at the top. */
export function zoomIn(zoom: number): number {
  return ZOOM_STEPS.find((step) => step > zoom + 0.001) ?? clampZoom(zoom);
}

/** The next preset below `zoom`. */
export function zoomOut(zoom: number): number {
  const lower = [...ZOOM_STEPS].reverse().find((step) => step < zoom - 0.001);
  return lower ?? clampZoom(zoom);
}

/**
 * The zoom at which the page fits the viewport, with its padding.
 *
 * Rounded down to 1% so the fitted page cannot overflow by a sub-pixel and introduce a
 * scrollbar, which would shrink the viewport and start the measurement again.
 */
export function fitZoom(
  page: PageGeometry,
  viewport: { readonly width: number; readonly height: number },
  paddingPx = 64,
): number {
  const available = {
    width: viewport.width - paddingPx * 2,
    height: viewport.height - paddingPx * 2,
  };
  if (available.width <= 0 || available.height <= 0) return MIN_ZOOM;
  const scale = Math.min(
    available.width / (page.widthMm * PX_PER_MM),
    available.height / (page.heightMm * PX_PER_MM),
  );
  return clampZoom(Math.floor(scale * 100) / 100);
}

/** Pixels on screen for one millimetre of paper at this zoom. */
export function pxPerMm(zoom: number): number {
  return PX_PER_MM * clampZoom(zoom);
}

/** A pointer offset inside the scaled page, back in paper millimetres. */
export function toMm(px: number, zoom: number): number {
  return px / pxPerMm(zoom);
}

/**
 * The storage scale for every millimetre figure in a layout: a tenth of a millimetre.
 *
 * It exists once because it is a decision, not an idiom. Division by a zoom factor and a
 * pointer delta in CSS pixels both produce values like `4.999999999999998`, and a layout
 * that stores those reads back as a measurement nobody typed. Finer than this is beyond
 * what a printer resolves or a designer means; coarser loses placements they do mean.
 */
export function roundMm(valueMm: number): number {
  return Math.round(valueMm * 10) / 10;
}

/**
 * Snap a millimetre value to a step — the editor's grid, and the coarse nudge keys.
 *
 * The result is rounded to the storage scale, because a snapped value is still a stored
 * one: a step of 2.5mm would otherwise land on 7.500000000000001. A step of zero means
 * free movement, where the rounding is all that applies.
 */
export function snapMm(valueMm: number, stepMm: number): number {
  if (!stepMm || stepMm <= 0) return roundMm(valueMm);
  return roundMm(Math.round(valueMm / stepMm) * stepMm);
}

/**
 * A millimetre figure for the status bar and the on-canvas readouts: one decimal, never
 * exponential, and `-0` normalised away.
 */
export function formatMm(valueMm: number): string {
  const rounded = roundMm(valueMm);
  return `${rounded === 0 ? 0 : rounded}`;
}

/** Ruler ticks for one axis: every `stepMm`, with a numeral every `majorEvery` steps. */
export function rulerTicks(
  lengthMm: number,
  stepMm = 5,
  majorEvery = 2,
): readonly { readonly mm: number; readonly major: boolean }[] {
  if (stepMm <= 0 || lengthMm <= 0) return [];
  const ticks: { mm: number; major: boolean }[] = [];
  const count = Math.floor(lengthMm / stepMm);
  for (let index = 0; index <= count; index += 1) {
    ticks.push({ mm: index * stepMm, major: index % majorEvery === 0 });
  }
  return ticks;
}
