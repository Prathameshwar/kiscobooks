/**
 * The layout edit model: pure functions, and the rules they refuse to break.
 *
 * No rendering here on purpose. These are the rules a control would otherwise
 * re-implement slightly differently each time — margins that leave something to print on,
 * an element that stays inside its zone, a column set that cannot overflow its table —
 * and the whole point of putting them in one tested function is that the editor cannot
 * compose a layout the service would reject.
 */
import { describe, expect, it } from 'vitest';
import {
  clamp,
  columnBudget,
  pageBox,
  setElementStyle,
  setMargins,
  setPage,
  setPrint,
  setTheme,
  updateColumn,
  updateElement,
  updateSection,
} from '../app/(editor)/invoice-designer/layout-edit';
import { templateById } from '../app/(editor)/invoice-designer/sample-templates';
import type { CanvasDefinition } from '../app/(editor)/invoice-designer/layout-model';

const GST = templateById('tpl-gst-a4')!.layout;
const THERMAL = templateById('tpl-thermal-80')!.layout;

function element(layout: CanvasDefinition, id: string) {
  return layout.sections.flatMap((section) => section.elements).find((el) => el.id === id)!;
}

function section(layout: CanvasDefinition, id: string) {
  return layout.sections.find((candidate) => candidate.id === id)!;
}

describe('page geometry', () => {
  it('resolves the paper the page names', () => {
    expect(pageBox(GST.page)).toEqual({ widthMm: 210, heightMm: 297 });
    expect(pageBox({ ...GST.page, size: 'A5' })).toEqual({ widthMm: 148, heightMm: 210 });
  });

  it('swaps the axes for landscape, but never for a roll', () => {
    expect(pageBox({ ...GST.page, orientation: 'LANDSCAPE' })).toEqual({
      widthMm: 297,
      heightMm: 210,
    });
    expect(pageBox({ ...THERMAL.page, orientation: 'LANDSCAPE' })).toEqual({
      widthMm: 80,
      heightMm: 200,
    });
  });

  it('uses the stated dimensions for a custom size, and A4 when there are none', () => {
    expect(pageBox({ ...GST.page, size: 'CUSTOM', widthMm: 100, heightMm: 150 })).toEqual({
      widthMm: 100,
      heightMm: 150,
    });
    expect(pageBox({ ...GST.page, size: 'CUSTOM', widthMm: undefined, heightMm: undefined })).toEqual(
      { widthMm: 210, heightMm: 297 },
    );
  });

  it('rounds to a tenth and treats any non-finite value as the floor', () => {
    expect(clamp(12.34, 0, 100)).toBe(12.3);
    // NaN and Infinity both mean something upstream miscomputed. The floor is the safe
    // answer — clamping Infinity to the maximum would silently produce a plausible value.
    expect(clamp(Number.NaN, 5, 100)).toBe(5);
    expect(clamp(Number.POSITIVE_INFINITY, 5, 100)).toBe(5);
  });
});

describe('page and margins', () => {
  it('returns a new layout and leaves the original untouched', () => {
    const next = setPage(GST, { gridStepMm: 10 });
    expect(next.page.gridStepMm).toBe(10);
    expect(GST.page.gridStepMm).toBe(5);
    expect(next).not.toBe(GST);
    expect(next.sections).toBe(GST.sections);
  });

  it('keeps the grid step usable rather than letting it reach zero', () => {
    expect(setPage(GST, { gridStepMm: 0 }).page.gridStepMm).toBe(1);
    expect(setPage(GST, { gridStepMm: 999 }).page.gridStepMm).toBe(50);
  });

  it('re-clamps the margins when the paper shrinks under them', () => {
    // A4 with 20mm side margins moved onto 58mm roll stock would otherwise leave an 18mm
    // printable strip — a layout that only fails on paper.
    const wide = setMargins(GST, { left: 30, right: 30 });
    const roll = setPage(wide, { size: 'THERMAL_58MM' });
    expect(roll.page.margins.left).toBe(24);
    expect(pageBox(roll.page).widthMm - roll.page.margins.left - roll.page.margins.right).toBe(10);
  });

  it('never lets margins eat the whole page', () => {
    const next = setMargins(GST, { top: 400, left: 400 });
    expect(next.page.margins.top).toBe(143.5);
    expect(next.page.margins.left).toBe(100);
  });

  it('keeps a margin of zero, which pre-printed stationery needs', () => {
    expect(setMargins(GST, { top: 0 }).page.margins.top).toBe(0);
  });

  it('bounds the theme’s base size to something a printer can set', () => {
    expect(setTheme(GST, { fontSizePt: 1 }).theme.fontSizePt).toBe(4);
    expect(setTheme(GST, { fontSizePt: 99 }).theme.fontSizePt).toBe(24);
    expect(setTheme(GST, { primaryColor: '#c28412' }).theme.primaryColor).toBe('#c28412');
  });

  it('changes the print options without touching the rest of the layout', () => {
    const next = setPrint(GST, { prePrintedStationery: true });
    expect(next.print.prePrintedStationery).toBe(true);
    expect(next.print.copies).toBe(GST.print.copies);
  });
});

describe('zones', () => {
  it('moves a zone and keeps it on the page', () => {
    const next = updateSection(GST, 'sec-header', { xMm: 400, yMm: 400 });
    const zone = section(next, 'sec-header');
    expect(zone.xMm).toBe(210 - zone.widthMm);
    expect(zone.yMm).toBe(297 - zone.heightMm);
  });

  it('re-fits the elements when a zone shrinks, so none is clipped away', () => {
    const next = updateSection(GST, 'sec-header', { widthMm: 60, heightMm: 12 });
    const title = element(next, 'el-title');
    expect(title.xMm + title.widthMm).toBeLessThanOrEqual(60);
    expect(title.yMm + title.heightMm).toBeLessThanOrEqual(12);
  });

  it('switches a zone to free placement without moving anything', () => {
    const next = updateSection(GST, 'sec-header', { freePlacement: true });
    expect(section(next, 'sec-header').freePlacement).toBe(true);
    expect(element(next, 'el-title').xMm).toBe(element(GST, 'el-title').xMm);
  });

  it('leaves every other zone identical, so React can skip them', () => {
    const next = updateSection(GST, 'sec-header', { title: 'Letterhead' });
    expect(section(next, 'sec-items')).toBe(section(GST, 'sec-items'));
  });
});

describe('elements', () => {
  it('moves an element inside its zone', () => {
    const next = updateElement(GST, 'el-title', { xMm: 20, yMm: 2 });
    expect(element(next, 'el-title')).toMatchObject({ xMm: 20, yMm: 2 });
  });

  it('keeps an element inside its zone rather than letting it vanish', () => {
    // The header zone is 190 × 28mm; an element pushed past that would be clipped by the
    // renderer and absent on paper, while the editor looked fine.
    const next = updateElement(GST, 'el-title', { xMm: 500, yMm: 500 });
    const title = element(next, 'el-title');
    expect(title.xMm).toBe(190 - title.widthMm);
    expect(title.yMm).toBe(28 - title.heightMm);
  });

  it('caps a size at the zone and never allows zero', () => {
    const grown = element(updateElement(GST, 'el-title', { widthMm: 900 }), 'el-title');
    expect(grown.widthMm).toBe(190);
    const shrunk = element(updateElement(GST, 'el-title', { widthMm: 0 }), 'el-title');
    expect(shrunk.widthMm).toBe(1);
  });

  it('edits content and a binding without disturbing geometry', () => {
    const next = updateElement(GST, 'el-title', { content: 'INVOICE' });
    expect(element(next, 'el-title').content).toBe('INVOICE');
    expect(element(next, 'el-title').xMm).toBe(element(GST, 'el-title').xMm);
  });

  it('merges a style patch and drops a property that is cleared', () => {
    const bolder = setElementStyle(GST, 'el-title', { fontSizePt: 18 });
    expect(element(bolder, 'el-title').style).toMatchObject({
      fontSizePt: 18,
      fontWeight: 'bold',
    });

    const cleared = setElementStyle(bolder, 'el-title', { fontWeight: undefined });
    expect(element(cleared, 'el-title').style).not.toHaveProperty('fontWeight');
    expect(element(cleared, 'el-title').style?.fontSizePt).toBe(18);
  });

  it('leaves the layout alone when the id is not on the page', () => {
    expect(updateElement(GST, 'el-nope', { xMm: 5 }).sections).toEqual(GST.sections);
  });
});

describe('item table columns', () => {
  it('widens a column only as far as the table has room', () => {
    const items = element(GST, 'el-items');
    const { usedMm, totalMm } = columnBudget(items);
    expect(usedMm).toBe(190);
    expect(totalMm).toBe(190);

    // Already full, so the description cannot take more than it has.
    const next = updateColumn(GST, 'el-items', 'description', { widthMm: 120 });
    expect(columnBudget(element(next, 'el-items')).usedMm).toBeLessThanOrEqual(190);
  });

  it('lets a column grow into the width a hidden column freed', () => {
    const hidden = updateColumn(GST, 'el-items', 'unit', { show: false });
    expect(columnBudget(element(hidden, 'el-items')).usedMm).toBe(180);

    const widened = updateColumn(hidden, 'el-items', 'description', { widthMm: 62 });
    expect(element(widened, 'el-items').columns?.find((c) => c.key === 'description')?.widthMm).toBe(
      62,
    );
    expect(columnBudget(element(widened, 'el-items')).usedMm).toBeLessThanOrEqual(190);
  });

  it('hides and shows a column without losing its width', () => {
    const hidden = updateColumn(GST, 'el-items', 'unit', { show: false });
    const shown = updateColumn(hidden, 'el-items', 'unit', { show: true });
    const unit = element(shown, 'el-items').columns?.find((c) => c.key === 'unit');
    expect(unit).toMatchObject({ show: true, widthMm: 10 });
  });

  it('does not hand a hidden column the whole table’s width', () => {
    // Hiding a column must not make the editor think every other column is hidden too,
    // which would let the next width through unchecked.
    const next = updateColumn(GST, 'el-items', 'description', { show: false, widthMm: 400 });
    const description = element(next, 'el-items').columns?.find((c) => c.key === 'description');
    // 190mm table, 138mm spent by the other shown columns, so 52mm is all there is.
    expect(description?.widthMm).toBe(52);
    expect(description?.show).toBe(false);
  });

  it('patches only columns the table already carries', () => {
    // Adding a column the layout does not list is the column designer's job (phase 4);
    // this function deliberately does not invent one.
    const next = updateColumn(GST, 'el-items', 'mrp', { show: true, widthMm: 20 });
    expect(element(next, 'el-items').columns?.some((c) => c.key === 'mrp')).toBe(false);
  });

  it('renames a column heading', () => {
    const next = updateColumn(GST, 'el-items', 'description', { label: 'Particulars' });
    expect(element(next, 'el-items').columns?.find((c) => c.key === 'description')?.label).toBe(
      'Particulars',
    );
  });

  it('ignores an element with no columns rather than inventing some', () => {
    const next = updateColumn(GST, 'el-title', 'description', { widthMm: 10 });
    expect(element(next, 'el-title').columns).toBeUndefined();
  });
});
