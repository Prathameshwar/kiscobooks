/**
 * Paper geometry for the invoice designer.
 *
 * The load-bearing properties: millimetres are the unit of record, a roll is not a sheet,
 * zoom moves between the presets a designer actually uses, and the fitted zoom can never
 * produce a page larger than the viewport that measured it.
 */
import { describe, expect, it } from 'vitest';
import {
  DEFAULT_MARGINS,
  MAX_ZOOM,
  MIN_ZOOM,
  PAPER_SIZES,
  PX_PER_MM,
  clampZoom,
  fitZoom,
  formatMm,
  pageGeometry,
  printableArea,
  pxPerMm,
  rulerTicks,
  roundMm,
  snapMm,
  toMm,
  zoomIn,
  zoomOut,
} from '../src/lib/paper';

describe('paper geometry', () => {
  it('uses the CSS reference pixel, so the canvas agrees with the print engine', () => {
    expect(PX_PER_MM).toBeCloseTo(3.779527, 5);
    expect(pxPerMm(2)).toBeCloseTo(PX_PER_MM * 2, 5);
    expect(toMm(PX_PER_MM * 10, 1)).toBeCloseTo(10, 5);
    // Round-trips at any zoom: a pointer 10mm into a page scaled 1.5× is still at 10mm.
    expect(toMm(PX_PER_MM * 10 * 1.5, 1.5)).toBeCloseTo(10, 5);
  });

  it('knows the sheet sizes an invoice is printed on', () => {
    expect(pageGeometry({ size: 'A4' })).toMatchObject({ widthMm: 210, heightMm: 297 });
    expect(pageGeometry({ size: 'A5' })).toMatchObject({ widthMm: 148, heightMm: 210 });
    expect(pageGeometry({ size: 'LETTER' })).toMatchObject({ widthMm: 215.9, heightMm: 279.4 });
  });

  it('swaps the axes for landscape', () => {
    expect(pageGeometry({ size: 'A4', orientation: 'LANDSCAPE' })).toMatchObject({
      widthMm: 297,
      heightMm: 210,
    });
  });

  it('refuses to rotate a roll, because 80mm stock has a fixed width', () => {
    const roll = pageGeometry({ size: 'THERMAL_80MM', orientation: 'LANDSCAPE' });
    expect(roll).toMatchObject({ widthMm: 80, continuous: true });
    expect(PAPER_SIZES.THERMAL_58MM.continuous).toBe(true);
    expect(PAPER_SIZES.A4.continuous).toBe(false);
  });

  it('falls back to A4 for a custom size that states no dimensions', () => {
    expect(pageGeometry({ size: 'CUSTOM' })).toMatchObject({ widthMm: 210, heightMm: 297 });
    expect(pageGeometry({ size: 'CUSTOM', widthMm: 100, heightMm: 150 })).toMatchObject({
      widthMm: 100,
      heightMm: 150,
      label: 'Custom',
    });
  });

  it('computes the printable area from the margins', () => {
    const area = printableArea(pageGeometry({ size: 'A4' }), DEFAULT_MARGINS);
    expect(area).toEqual({ xMm: 10, yMm: 10, widthMm: 190, heightMm: 277 });
  });

  it('never reports a negative printable area, however absurd the margins', () => {
    const area = printableArea(pageGeometry({ size: 'THERMAL_58MM' }), {
      top: 200,
      right: 40,
      bottom: 200,
      left: 40,
    });
    expect(area.widthMm).toBe(0);
    expect(area.heightMm).toBe(0);
  });
});

describe('zoom', () => {
  it('steps between the presets a designer works at', () => {
    expect(zoomIn(1)).toBe(1.25);
    expect(zoomOut(1)).toBe(0.75);
    expect(zoomIn(0.26)).toBe(0.5);
    expect(zoomOut(0.74)).toBe(0.5);
  });

  it('stops at the ends rather than wrapping or exceeding them', () => {
    expect(zoomIn(MAX_ZOOM)).toBe(MAX_ZOOM);
    expect(zoomOut(MIN_ZOOM)).toBe(MIN_ZOOM);
    expect(clampZoom(99)).toBe(MAX_ZOOM);
    expect(clampZoom(0)).toBe(MIN_ZOOM);
  });

  it('treats any non-finite zoom as 100% instead of rendering nothing', () => {
    // NaN and Infinity both mean something upstream miscomputed — a division by an
    // unmeasured viewport, most likely. 100% is the honest fallback; clamping Infinity to
    // 200% would show a plausible page and hide the bug.
    expect(clampZoom(Number.NaN)).toBe(1);
    expect(clampZoom(Number.POSITIVE_INFINITY)).toBe(1);
    expect(clampZoom(Number.NEGATIVE_INFINITY)).toBe(1);
  });

  it('fits the page inside the viewport, rounded down so it cannot overflow', () => {
    const page = pageGeometry({ size: 'A4' });
    const zoom = fitZoom(page, { width: 900, height: 700 }, 32);
    expect(zoom).toBeLessThanOrEqual((700 - 64) / (page.heightMm * PX_PER_MM));
    expect(page.heightMm * pxPerMm(zoom)).toBeLessThanOrEqual(700 - 64);
  });

  it('falls back to the smallest zoom when there is no room to measure', () => {
    expect(fitZoom(pageGeometry({ size: 'A4' }), { width: 10, height: 10 })).toBe(MIN_ZOOM);
  });
});

describe('millimetre helpers', () => {
  it('rounds to the storage scale, which is where float drift gets absorbed', () => {
    expect(roundMm(4.999999999999998)).toBe(5);
    expect(roundMm(12.34)).toBe(12.3);
    expect(roundMm(12.35)).toBe(12.4);
    // Already at scale, and so unchanged — the common case.
    expect(roundMm(12.3)).toBe(12.3);
  });

  it('snaps to the grid step and leaves the value alone when there is no step', () => {
    expect(snapMm(12.4, 5)).toBe(10);
    expect(snapMm(12.6, 5)).toBe(15);
    expect(snapMm(12.6, 0)).toBe(12.6);
    // A fractional step is where snapping used to reintroduce the drift it exists to
    // remove: 3 × 2.5 is 7.500000000000001 in binary floating point.
    expect(snapMm(7.4, 2.5)).toBe(7.5);
  });

  it('formats one decimal and never shows negative zero', () => {
    expect(formatMm(12.34)).toBe('12.3');
    expect(formatMm(12)).toBe('12');
    expect(formatMm(-0.01)).toBe('0');
  });

  it('produces a tick per step with a numeral every second one', () => {
    const ticks = rulerTicks(20, 5);
    expect(ticks.map((t) => t.mm)).toEqual([0, 5, 10, 15, 20]);
    expect(ticks.filter((t) => t.major).map((t) => t.mm)).toEqual([0, 10, 20]);
  });

  it('draws no ticks for a page with no length, rather than looping forever', () => {
    expect(rulerTicks(0)).toEqual([]);
    expect(rulerTicks(100, 0)).toEqual([]);
  });
});
