/**
 * The set operations, with no DOM at all.
 *
 * The load-bearing properties: a group move stops when its *first* member would leave its
 * zone, so the arrangement survives the gesture; alignment is against the box around the
 * selection, and against the zone when there is only one thing to align; distribution
 * equalises gaps and leaves the outermost two alone; a restack writes array order and
 * `zIndex` together; a duplicate lands on top of its source with an id nobody else has;
 * and nothing ever leaves its zone.
 */
import { describe, expect, it } from 'vitest';
import {
  MIN_DISTRIBUTE,
  alignElements,
  deleteElements,
  depthOf,
  distributeElements,
  duplicateElements,
  moveSelection,
  pageRect,
  refsOf,
  reorderElements,
  selectionBounds,
} from '../app/(editor)/invoice-designer/layout-arrange';
import type { CanvasDefinition, CanvasElement } from '../app/(editor)/invoice-designer/layout-model';
import { SCHEMA_VERSION } from '../app/(editor)/invoice-designer/layout-model';

function element(
  id: string,
  box: [number, number, number, number],
  extra: Partial<CanvasElement> = {},
): CanvasElement {
  const [xMm, yMm, widthMm, heightMm] = box;
  return { id, type: 'TEXT', xMm, yMm, widthMm, heightMm, content: id, ...extra };
}

/**
 * Two zones, because every one of these operations is defined in page coordinates and the
 * interesting cases cross a zone boundary — a total lined up with a column above it.
 */
function layoutOf(): CanvasDefinition {
  return {
    schemaVersion: SCHEMA_VERSION,
    page: {
      size: 'A4',
      orientation: 'PORTRAIT',
      margins: { top: 10, right: 10, bottom: 10, left: 10, unit: 'mm' },
      gridSnap: true,
      gridStepMm: 5,
    },
    theme: { primaryColor: '#1e40af', fontFamily: 'Inter, sans-serif', fontSizePt: 9 },
    print: { copies: ['ORIGINAL_FOR_RECIPIENT'] },
    sections: [
      {
        id: 'sec-head',
        type: 'HEADER',
        xMm: 10,
        yMm: 10,
        widthMm: 100,
        heightMm: 40,
        elements: [
          element('a', [0, 0, 20, 10]),
          element('b', [30, 12, 40, 6]),
          element('c', [10, 24, 10, 8]),
        ],
      },
      {
        id: 'sec-foot',
        type: 'FOOTER',
        xMm: 10,
        yMm: 60,
        widthMm: 100,
        heightMm: 30,
        elements: [element('d', [50, 0, 30, 10])],
      },
    ],
  };
}

const at = (layout: CanvasDefinition, id: string) =>
  layout.sections.flatMap((section) => section.elements).find((element) => element.id === id);

const page = (layout: CanvasDefinition, id: string) => pageRect(refsOf(layout, [id])[0]!);

describe('refsOf and bounds', () => {
  it('finds elements in page order and ignores an id that names a zone', () => {
    const layout = layoutOf();
    const refs = refsOf(layout, ['d', 'a', 'sec-head', 'nope']);
    expect(refs.map((ref) => ref.element.id)).toEqual(['a', 'd']);
    expect(refs[0]?.section.id).toBe('sec-head');
  });

  it('puts an element in page coordinates, zone offset included', () => {
    expect(page(layoutOf(), 'b')).toEqual({ xMm: 40, yMm: 22, widthMm: 40, heightMm: 6 });
  });

  it('boxes a selection that crosses two zones', () => {
    // a is at 10,10 and 20 × 10; d is at 60,60 and 30 × 10.
    expect(selectionBounds(layoutOf(), ['a', 'd'])).toEqual({
      xMm: 10,
      yMm: 10,
      widthMm: 80,
      heightMm: 60,
    });
  });

  it('has no box for an empty selection', () => {
    expect(selectionBounds(layoutOf(), [])).toBeNull();
  });
});

describe('moveSelection', () => {
  it('moves every member by the same delta', () => {
    const next = moveSelection(layoutOf(), ['a', 'b'], { dxMm: 5, dyMm: 4 });
    expect(at(next, 'a')).toMatchObject({ xMm: 5, yMm: 4 });
    expect(at(next, 'b')).toMatchObject({ xMm: 35, yMm: 16 });
    // Untouched.
    expect(at(next, 'c')).toMatchObject({ xMm: 10, yMm: 24 });
  });

  it('stops the whole group when one member would leave its zone', () => {
    const layout = layoutOf();
    // b ends at 70 in a 100mm zone, so the group can only go 30mm right — even though a
    // has 80mm of room. Clamping each separately would close the 30mm gap between them.
    const next = moveSelection(layout, ['a', 'b'], { dxMm: 500, dyMm: 0 });
    expect(at(next, 'a')).toMatchObject({ xMm: 30 });
    expect(at(next, 'b')).toMatchObject({ xMm: 60 });
    expect(page(next, 'b').xMm - page(next, 'a').xMm).toBe(30);
  });

  it('keeps the gap when the group is pushed the other way too', () => {
    const next = moveSelection(layoutOf(), ['a', 'b'], { dxMm: -500, dyMm: -500 });
    // a sits at 0,0 already, so nothing can move at all.
    expect(at(next, 'a')).toMatchObject({ xMm: 0, yMm: 0 });
    expect(at(next, 'b')).toMatchObject({ xMm: 30, yMm: 12 });
  });

  it('snaps the anchor, not each member, so the group is never pulled apart', () => {
    // b is at 30 and would snap to itself; c is at 10. With c as the anchor a 2mm push
    // lands it on 10 (snap of 12 is 10), so nothing moves and b does not drift.
    const next = moveSelection(layoutOf(), ['b', 'c'], { dxMm: 2, dyMm: 0 }, {
      snapMm: 5,
      anchorId: 'c',
    });
    expect(at(next, 'c')).toMatchObject({ xMm: 10 });
    expect(at(next, 'b')).toMatchObject({ xMm: 30 });

    const further = moveSelection(layoutOf(), ['b', 'c'], { dxMm: 4, dyMm: 0 }, {
      snapMm: 5,
      anchorId: 'c',
    });
    // The anchor snapped to 15, a 5mm step, and b took the same 5mm.
    expect(at(further, 'c')).toMatchObject({ xMm: 15 });
    expect(at(further, 'b')).toMatchObject({ xMm: 35 });
  });

  it('falls back to the first member when the named anchor is not in the set', () => {
    const next = moveSelection(layoutOf(), ['b', 'c'], { dxMm: 1, dyMm: 0 }, { anchorId: 'zzz' });
    expect(at(next, 'b')).toMatchObject({ xMm: 31 });
  });

  it('returns the same layout when nothing can move', () => {
    const layout = layoutOf();
    expect(moveSelection(layout, ['a'], { dxMm: 0, dyMm: 0 })).toBe(layout);
    expect(moveSelection(layout, [], { dxMm: 5, dyMm: 5 })).toBe(layout);
  });
});

describe('alignElements', () => {
  it('lines a group up on the left edge of its own box', () => {
    const next = alignElements(layoutOf(), ['a', 'b', 'c'], 'left');
    // a is leftmost at page 10, so everything goes there.
    for (const id of ['a', 'b', 'c']) expect(page(next, id).xMm).toBe(10);
  });

  it('lines a group up on the right edge, each by its own width', () => {
    const next = alignElements(layoutOf(), ['a', 'b'], 'right');
    // b is widest and rightmost: its right edge, page 80, is the target.
    expect(page(next, 'a').xMm + page(next, 'a').widthMm).toBe(80);
    expect(page(next, 'b').xMm + page(next, 'b').widthMm).toBe(80);
  });

  it('centres a group on the centre of its box', () => {
    const next = alignElements(layoutOf(), ['a', 'b'], 'centreX');
    const centre = (id: string) => page(next, id).xMm + page(next, id).widthMm / 2;
    expect(centre('a')).toBeCloseTo(centre('b'), 5);
  });

  it('aligns on the vertical axis too, and leaves the other axis alone', () => {
    const before = page(layoutOf(), 'b').xMm;
    const next = alignElements(layoutOf(), ['a', 'b', 'c'], 'top');
    for (const id of ['a', 'b', 'c']) expect(page(next, id).yMm).toBe(10);
    expect(page(next, 'b').xMm).toBe(before);
  });

  it('works across zones, which is the whole point of page coordinates', () => {
    const next = alignElements(layoutOf(), ['b', 'd'], 'left');
    expect(page(next, 'b').xMm).toBe(40);
    expect(page(next, 'd').xMm).toBe(40);
    // d is in the footer zone, so its own coordinate changed to suit.
    expect(at(next, 'd')).toMatchObject({ xMm: 30 });
  });

  it('aligns a lone element to its zone, because aligning it to itself does nothing', () => {
    const next = alignElements(layoutOf(), ['b'], 'right');
    // The zone is 100mm wide and b is 40mm, so its own coordinate is 60.
    expect(at(next, 'b')).toMatchObject({ xMm: 60 });

    const bottom = alignElements(layoutOf(), ['b'], 'bottom');
    expect(at(bottom, 'b')).toMatchObject({ yMm: 34 });
  });

  it('never pushes an element out of its zone', () => {
    const next = alignElements(layoutOf(), ['a', 'd'], 'bottom');
    // The group's bottom is page 70, which is inside the footer but below the header's
    // own 50mm bottom, so a stops at its zone edge rather than vanishing.
    expect(at(next, 'a')!.yMm).toBeLessThanOrEqual(30);
    expect(page(next, 'd').yMm + 10).toBe(70);
  });

  it('leaves an empty selection alone', () => {
    const layout = layoutOf();
    expect(alignElements(layout, [], 'left')).toBe(layout);
  });
});

describe('distributeElements', () => {
  it('equalises the gaps and leaves the outermost two where they were', () => {
    const layout = layoutOf();
    // Page x: a 10 (w 20), c 20 (w 10), b 40 (w 40). Span 10 → 80 = 70mm for 70mm of
    // element, so the gaps come out at zero and they butt together.
    const next = distributeElements(layout, ['a', 'b', 'c'], 'x');
    expect(page(next, 'a').xMm).toBe(10);
    expect(page(next, 'c').xMm).toBe(30);
    expect(page(next, 'b').xMm).toBe(40);
  });

  it('shares real space when there is some', () => {
    const layout = layoutOf();
    const wide = {
      ...layout,
      sections: layout.sections.map((section) =>
        section.id === 'sec-head'
          ? {
              ...section,
              elements: [
                element('a', [0, 0, 10, 10]),
                element('c', [20, 0, 10, 10]),
                element('b', [70, 0, 10, 10]),
              ],
            }
          : section,
      ),
    };
    // Span 10 → 90 = 80mm, holding 30mm of element, so each of the two gaps is 25mm.
    const next = distributeElements(wide, ['a', 'b', 'c'], 'x');
    expect(page(next, 'a').xMm).toBe(10);
    expect(page(next, 'c').xMm).toBe(45);
    expect(page(next, 'b').xMm).toBe(80);
  });

  it('distributes down the page, leaving the across positions alone', () => {
    const before = page(layoutOf(), 'b').xMm;
    // Page y: a 10 (h 10), b 22 (h 6), c 34 (h 8). Span 10 → 42 is 32mm holding 24mm of
    // element, so each of the two gaps becomes 4mm and only the middle one moves.
    const next = distributeElements(layoutOf(), ['a', 'b', 'c'], 'y');
    expect(page(next, 'a').yMm).toBe(10);
    expect(page(next, 'b').yMm).toBe(24);
    expect(page(next, 'c').yMm).toBe(34);
    expect(page(next, 'b').xMm).toBe(before);
  });

  it('refuses below three — there is no "between" to space out', () => {
    const layout = layoutOf();
    expect(MIN_DISTRIBUTE).toBe(3);
    expect(distributeElements(layout, ['a', 'b'], 'x')).toBe(layout);
    expect(distributeElements(layout, [], 'x')).toBe(layout);
  });
});

describe('reorderElements', () => {
  const order = (layout: CanvasDefinition, sectionId = 'sec-head') =>
    layout.sections.find((section) => section.id === sectionId)!.elements.map((el) => el.id);

  it('brings one element to the front of its zone', () => {
    const next = reorderElements(layoutOf(), ['a'], 'front');
    expect(order(next)).toEqual(['b', 'c', 'a']);
  });

  it('sends one element to the back', () => {
    const next = reorderElements(layoutOf(), ['c'], 'back');
    expect(order(next)).toEqual(['c', 'a', 'b']);
  });

  it('writes zIndex to match the order, so the two can never disagree', () => {
    const next = reorderElements(layoutOf(), ['a'], 'front');
    const head = next.sections[0]!.elements;
    expect(head.map((el) => el.zIndex)).toEqual([0, 1, 2]);
    expect(head.map((el) => el.id)).toEqual(['b', 'c', 'a']);
  });

  it('moves one step at a time', () => {
    const forward = reorderElements(layoutOf(), ['a'], 'forward');
    expect(order(forward)).toEqual(['b', 'a', 'c']);
    const backward = reorderElements(layoutOf(), ['c'], 'backward');
    expect(order(backward)).toEqual(['a', 'c', 'b']);
  });

  it('keeps two selected neighbours together when they step', () => {
    // a and b are adjacent; a naive swap would exchange them and leave the pair put.
    const next = reorderElements(layoutOf(), ['a', 'b'], 'forward');
    expect(order(next)).toEqual(['c', 'a', 'b']);
  });

  it('holds at the edge rather than wrapping round', () => {
    const start = layoutOf();
    // a is already at the back and c already at the front: both are no-ops, and returning
    // the same layout is what stops them becoming undo entries.
    expect(reorderElements(start, ['a'], 'backward')).toBe(start);
    expect(reorderElements(start, ['c'], 'forward')).toBe(start);
    expect(reorderElements(start, ['a'], 'back')).toBe(start);
    expect(reorderElements(start, ['c'], 'front')).toBe(start);
  });

  it('is a no-op when every element in the zone is selected', () => {
    const layout = layoutOf();
    expect(reorderElements(layout, ['a', 'b', 'c'], 'front')).toBe(layout);
  });

  it('restacks each zone independently', () => {
    const next = reorderElements(layoutOf(), ['a', 'd'], 'front');
    expect(order(next)).toEqual(['b', 'c', 'a']);
    // d is alone in the footer, so there is nothing to move it past.
    expect(order(next, 'sec-foot')).toEqual(['d']);
  });

  it('states where an element sits in its stack', () => {
    expect(depthOf(layoutOf(), 'b')).toEqual({ at: 2, of: 3 });
    expect(depthOf(layoutOf(), 'd')).toEqual({ at: 1, of: 1 });
    expect(depthOf(layoutOf(), 'nope')).toBeNull();
  });
});

describe('duplicateElements', () => {
  it('copies an element, offset, directly after its source', () => {
    const { layout, ids } = duplicateElements(layoutOf(), ['a']);
    expect(ids).toEqual(['a-copy']);
    expect(layout.sections[0]!.elements.map((el) => el.id)).toEqual(['a', 'a-copy', 'b', 'c']);
    expect(at(layout, 'a-copy')).toMatchObject({ xMm: 2, yMm: 2, widthMm: 20, heightMm: 10 });
  });

  it('carries everything else over, so a copy prints the same', () => {
    const source = layoutOf();
    const styled = {
      ...source,
      sections: source.sections.map((section) =>
        section.id === 'sec-head'
          ? {
              ...section,
              elements: section.elements.map((el) =>
                el.id === 'a' ? { ...el, content: 'TAX INVOICE', style: { fontSizePt: 13 } } : el,
              ),
            }
          : section,
      ),
    };
    const { layout } = duplicateElements(styled, ['a']);
    expect(at(layout, 'a-copy')).toMatchObject({
      content: 'TAX INVOICE',
      style: { fontSizePt: 13 },
    });
  });

  it('numbers the second copy rather than colliding', () => {
    const first = duplicateElements(layoutOf(), ['a']);
    const second = duplicateElements(first.layout, ['a']);
    expect(second.ids).toEqual(['a-copy-2']);
    const third = duplicateElements(second.layout, ['a']);
    expect(third.ids).toEqual(['a-copy-3']);
  });

  it('copies a set in one go, each beside its own source', () => {
    const { layout, ids } = duplicateElements(layoutOf(), ['a', 'd']);
    expect(ids).toEqual(['a-copy', 'd-copy']);
    expect(layout.sections[1]!.elements.map((el) => el.id)).toEqual(['d', 'd-copy']);
  });

  it('turns the offset inwards when the source is flush against its zone', () => {
    const layout = layoutOf();
    const edge = {
      ...layout,
      sections: layout.sections.map((section) =>
        section.id === 'sec-foot'
          ? { ...section, elements: [element('d', [70, 20, 30, 10])] }
          : section,
      ),
    };
    const { layout: next } = duplicateElements(edge, ['d']);
    // The element fills the zone's bottom-right corner, so pushing the copy further out
    // would clamp it back on top of its source and look like nothing happened.
    expect(at(next, 'd-copy')).toMatchObject({ xMm: 68, yMm: 18 });
  });

  it('still refuses to let a copy leave its zone', () => {
    const layout = layoutOf();
    const tight = {
      ...layout,
      sections: layout.sections.map((section) =>
        section.id === 'sec-foot'
          ? { ...section, elements: [element('d', [0, 0, 100, 30])] }
          : section,
      ),
    };
    const { layout: next } = duplicateElements(tight, ['d']);
    // The element is the whole zone: there is nowhere to go in either direction.
    expect(at(next, 'd-copy')).toMatchObject({ xMm: 0, yMm: 0 });
  });

  it('does nothing for an empty selection', () => {
    const layout = layoutOf();
    const result = duplicateElements(layout, []);
    expect(result.layout).toBe(layout);
    expect(result.ids).toEqual([]);
  });
});

describe('deleteElements', () => {
  it('removes a set and leaves the rest', () => {
    const next = deleteElements(layoutOf(), ['a', 'd']);
    expect(next.sections[0]!.elements.map((el) => el.id)).toEqual(['b', 'c']);
    expect(next.sections[1]!.elements).toEqual([]);
  });

  it('leaves an emptied zone in place — a footer with no bank details is still a footer', () => {
    const next = deleteElements(layoutOf(), ['d']);
    expect(next.sections).toHaveLength(2);
    expect(next.sections[1]!.id).toBe('sec-foot');
  });

  it('ignores an id that names a zone, which is structure and not an object', () => {
    const layout = layoutOf();
    const next = deleteElements(layout, ['sec-head']);
    expect(next).toBe(layout);
    expect(next.sections).toHaveLength(2);
  });

  it('returns the same layout when there is nothing to remove', () => {
    const layout = layoutOf();
    expect(deleteElements(layout, [])).toBe(layout);
    expect(deleteElements(layout, ['nope'])).toBe(layout);
  });
});
