/**
 * What is wrong with this layout, stated before it reaches a printer.
 *
 * This is the half of a designer that a preview cannot do. The canvas shows you the page
 * you drew; it cannot show you the page you will *get*, because the two differ exactly
 * where the paper runs out — and those are the defects that survive review. A zone 4mm
 * past the printable edge looks finished on a 1400px screen and comes out of the printer
 * with the GSTIN sliced off. A column set that sums to 204mm inside a 190mm table
 * (`invoice-design-ui-todo.md`, phase 1) looked right to everyone who opened it.
 *
 * So: pure checks over the layout, each naming the thing to look at, so the panel can
 * select it and the designer can see what the sentence is about. No check guesses at
 * intent — a warning a designer learns to ignore has made every other warning weaker,
 * which is why an empty zone and an overlapping-by-design watermark are *not* in here.
 *
 * The one judgement that is genuinely in here is **sheet versus roll**. Content past the
 * bottom of a sheet continues on page two, which for a long item table is the whole point
 * and for a totals block is a split invoice. Content past the nominal bottom of a roll is
 * nothing at all: the roll is continuous and simply gets longer. Reporting the second as
 * a problem would teach a receipt designer that this panel is noise.
 */

import { formatMm, pageGeometry, printableArea, rectsOverlap } from '@janso/ui';

import { columnBudget } from './layout-edit';
import type { CanvasDefinition, CanvasElement, CanvasSection } from './layout-model';
import { isLineTable } from './layout-model';
import { sampleValue } from './sample-document';
import { SAMPLE_ASSETS } from './sample-templates';
import { elementLabel, zoneLabel } from './selection';

export type WarningCode =
  | 'zone-outside-printable'
  | 'zones-overlap'
  | 'page-break-inside-zone'
  | 'element-outside-zone'
  | 'columns-overflow'
  | 'binding-unresolved'
  | 'asset-missing'
  /** The voucher kind this layout prints for cannot print it (`print-capabilities.ts`). */
  | 'print-unsupported';

/**
 * `error` prints wrong: something will be clipped, dropped or overlaid. `warning` may be
 * deliberate, and says what will happen rather than asking for a change.
 */
export type WarningSeverity = 'error' | 'warning';

export type LayoutWarning = {
  readonly code: WarningCode;
  readonly severity: WarningSeverity;
  /** The zone or element to select, so the sentence has something to point at. */
  readonly targetId: string;
  readonly message: string;
};

/** A millimetre figure inside a sentence: "4.5mm", never "4.500000000000001mm". */
const mm = (value: number) => `${formatMm(value)}mm`;

type Box = { xMm: number; yMm: number; widthMm: number; heightMm: number };

type Side = 'left' | 'top' | 'right' | 'bottom';

/**
 * How far a zone sticks out of the printable area, per side.
 *
 * A tenth of a millimetre of overhang is rounding, not a defect — zones are placed at the
 * storage scale and an exact fit must read as an exact fit. Anything the model can
 * actually represent as a gap is reported.
 */
const TOLERANCE_MM = 0.1;

function overflow(zone: Box, area: Box): { side: Side; byMm: number }[] {
  const sides: { side: Side; byMm: number }[] = [
    { side: 'left', byMm: area.xMm - zone.xMm },
    { side: 'top', byMm: area.yMm - zone.yMm },
    { side: 'right', byMm: zone.xMm + zone.widthMm - (area.xMm + area.widthMm) },
    { side: 'bottom', byMm: zone.yMm + zone.heightMm - (area.yMm + area.heightMm) },
  ];
  return sides.filter((entry) => entry.byMm > TOLERANCE_MM);
}

/** Checks that need only the zone's own box against the page. */
function checkZoneGeometry(
  layout: CanvasDefinition,
  section: CanvasSection,
  area: Box,
  continuous: boolean,
): LayoutWarning[] {
  const found: LayoutWarning[] = [];
  const name = zoneLabel(section);
  const bottomEdge = area.yMm + area.heightMm;
  const zoneBottom = section.yMm + section.heightMm;

  // On a roll the bottom is nominal, so only the width is a real constraint. On a sheet a
  // zone that *starts* inside and ends past the edge is a page break, which is a different
  // sentence from "this is off the paper" and the one a designer can act on.
  const straddlesBreak =
    !continuous && section.yMm < bottomEdge - TOLERANCE_MM && zoneBottom > bottomEdge + TOLERANCE_MM;

  for (const { side, byMm } of overflow(section, area)) {
    if (side === 'bottom' && (continuous || straddlesBreak)) continue;
    found.push({
      code: 'zone-outside-printable',
      severity: 'error',
      targetId: section.id,
      message: `“${name}” is ${mm(byMm)} past the ${side} edge of the printable area and will be clipped.`,
    });
  }

  if (straddlesBreak) {
    found.push({
      code: 'page-break-inside-zone',
      severity: 'warning',
      targetId: section.id,
      message:
        `“${name}” crosses the bottom of the printable area by ${mm(zoneBottom - bottomEdge)}, ` +
        `so ${layout.print.copies.length > 1 ? 'every copy' : 'the document'} continues on a second page.`,
    });
  }

  return found;
}

/**
 * The saved pictures a layout may name. Absent: the fixture session, whose pictures are
 * `SAMPLE_ASSETS`. `null`: a company's list not read yet, so nothing is claimed about one.
 */
export type KnownAssetIds = ReadonlySet<string> | null | undefined;

/** Checks on one element, inside the zone that owns it. */
function checkElement(section: CanvasSection, element: CanvasElement, assets: KnownAssetIds): LayoutWarning[] {
  const found: LayoutWarning[] = [];
  const name = elementLabel(element);

  const outside = overflow(element, {
    xMm: 0,
    yMm: 0,
    widthMm: section.widthMm,
    heightMm: section.heightMm,
  });
  if (outside.length > 0) {
    const worst = outside.reduce((a, b) => (b.byMm > a.byMm ? b : a));
    found.push({
      code: 'element-outside-zone',
      severity: 'error',
      targetId: element.id,
      message:
        `“${name}” is ${mm(worst.byMm)} outside “${zoneLabel(section)}” on the ${worst.side}. ` +
        `A zone clips what it contains, so this will not print.`,
    });
  }

  if (isLineTable(element.type) && element.columns) {
    const { usedMm, totalMm } = columnBudget(element);
    if (usedMm > totalMm + TOLERANCE_MM) {
      found.push({
        code: 'columns-overflow',
        severity: 'error',
        targetId: element.id,
        message:
          `The columns of “${name}” sum to ${mm(usedMm)} inside a ${mm(totalMm)} table, ` +
          `so ${mm(usedMm - totalMm)} of the right-hand column will be cut off.`,
      });
    }
  }

  if (element.type === 'FIELD_BINDING') {
    if (!element.bindingPath) {
      found.push({
        code: 'binding-unresolved',
        severity: 'warning',
        targetId: element.id,
        message: `“${name}” is bound to nothing and prints as a blank box.`,
      });
    } else if (sampleValue(element.bindingPath) === null) {
      found.push({
        code: 'binding-unresolved',
        severity: 'warning',
        targetId: element.id,
        message:
          `The sample document has no value for “${element.bindingPath}”, so the preview ` +
          `prints the path in brackets. A real document may still resolve it.`,
      });
    }
  }

  /*
   * An image with no asset prints an empty frame, which is a defect. A *signature* with
   * no asset is a space someone signs by hand — a delivery challan's "Receiver's
   * signature" is meant to be blank, and so is every invoice signed with a pen. Warning
   * about those would be warning about the normal case, which is how a panel earns the
   * habit of being ignored. Both still have to name an asset the template carries.
   */
  if (element.type === 'IMAGE' && !element.assetId) {
    found.push({
      code: 'asset-missing',
      severity: 'warning',
      targetId: element.id,
      message: `“${name}” has no image assigned and prints as an empty frame.`,
    });
  } else if (
    element.assetId &&
    assets !== null &&
    !(assets ? assets.has(element.assetId) : SAMPLE_ASSETS[element.assetId])
  ) {
    found.push({
      code: 'asset-missing',
      severity: 'warning',
      targetId: element.id,
      message: `“${name}” names an asset this template does not carry.`,
    });
  }

  return found;
}

/** Errors first, then down the page, so the list reads the way the page does. */
function order(layout: CanvasDefinition, warnings: readonly LayoutWarning[]): LayoutWarning[] {
  const position = new Map<string, number>();
  let index = 0;
  for (const section of layout.sections) {
    position.set(section.id, index++);
    for (const element of section.elements) position.set(element.id, index++);
  }
  return [...warnings].sort((a, b) => {
    if (a.severity !== b.severity) return a.severity === 'error' ? -1 : 1;
    return (position.get(a.targetId) ?? 0) - (position.get(b.targetId) ?? 0);
  });
}

/**
 * Every warning this layout earns.
 *
 * Pure, so the panel is a render of it and the tests need no DOM — and so the same
 * function can gate a publish later, when there is a service to publish to.
 */
export function checkLayout(layout: CanvasDefinition, assets?: KnownAssetIds): LayoutWarning[] {
  const geometry = pageGeometry(layout.page);
  const area = printableArea(geometry, layout.page.margins);
  const found: LayoutWarning[] = [];

  for (const section of layout.sections) {
    found.push(...checkZoneGeometry(layout, section, area, geometry.continuous));
    for (const element of section.elements) found.push(...checkElement(section, element, assets));
  }

  // Overlap is a property of a pair, so it is reported once, on the lower of the two:
  // that is the one the designer moved into the other.
  for (let i = 0; i < layout.sections.length; i += 1) {
    for (let j = i + 1; j < layout.sections.length; j += 1) {
      const first = layout.sections[i];
      const second = layout.sections[j];
      if (!first || !second || !rectsOverlap(first, second)) continue;
      found.push({
        code: 'zones-overlap',
        severity: 'warning',
        targetId: second.id,
        message:
          `“${zoneLabel(second)}” overlaps “${zoneLabel(first)}”. Zones print in order, ` +
          `so whichever comes later lands on top.`,
      });
    }
  }

  return order(layout, found);
}

/** A one-line summary for the panel's heading and the status bar. */
export function summarise(warnings: readonly LayoutWarning[]): string {
  const errors = warnings.filter((warning) => warning.severity === 'error').length;
  const others = warnings.length - errors;
  if (errors === 0 && others === 0) return 'Nothing to fix';
  const parts: string[] = [];
  if (errors > 0) parts.push(`${errors} ${errors === 1 ? 'error' : 'errors'}`);
  if (others > 0) parts.push(`${others} ${others === 1 ? 'warning' : 'warnings'}`);
  return parts.join(' · ');
}
