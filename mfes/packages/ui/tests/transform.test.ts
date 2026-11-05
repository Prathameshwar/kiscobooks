/**
 * Moving, resizing and aiming.
 *
 * The load-bearing properties: a north or west handle moves the edge *and* the origin, a
 * rectangle stops at its minimum rather than inverting, nothing leaves its bounds, the
 * *position* is snapped rather than the delta, and a guide only ever matches like with
 * like.
 */
import { describe, expect, it } from 'vitest';
import { HANDLES, alignmentGuides, moveRect, resizeRect } from '../src/lib/transform';

const RECT = { xMm: 20, yMm: 30, widthMm: 40, heightMm: 20 };
const ZONE = { widthMm: 190, heightMm: 100 };

describe('moveRect', () => {
  it('moves by the delta', () => {
    expect(moveRect(RECT, { dxMm: 10, dyMm: -5 })).toMatchObject({ xMm: 30, yMm: 25 });
  });

  it('snaps the position, not the delta, so an off-grid rectangle lands on the grid', () => {
    const offGrid = { ...RECT, xMm: 12.3, yMm: 7.4 };
    // A 1mm nudge from 12.3 would stay off-grid forever if the delta were snapped.
    expect(moveRect(offGrid, { dxMm: 1, dyMm: 1 }, { snapMm: 5 })).toMatchObject({
      xMm: 15,
      yMm: 10,
    });
  });

  it('keeps the rectangle inside its bounds', () => {
    expect(moveRect(RECT, { dxMm: 500, dyMm: 500 }, { bounds: ZONE })).toMatchObject({
      xMm: 150,
      yMm: 80,
    });
    expect(moveRect(RECT, { dxMm: -500, dyMm: -500 }, { bounds: ZONE })).toMatchObject({
      xMm: 0,
      yMm: 0,
    });
  });

  it('pins a rectangle larger than its bounds to the origin rather than negative', () => {
    const huge = { xMm: 5, yMm: 5, widthMm: 300, heightMm: 300 };
    expect(moveRect(huge, { dxMm: 10, dyMm: 10 }, { bounds: ZONE })).toMatchObject({
      xMm: 0,
      yMm: 0,
    });
  });

  it('leaves the size alone', () => {
    const moved = moveRect(RECT, { dxMm: 7, dyMm: 7 }, { bounds: ZONE });
    expect(moved.widthMm).toBe(40);
    expect(moved.heightMm).toBe(20);
  });
});

describe('resizeRect', () => {
  it('offers eight handles, clockwise from the top-left', () => {
    expect(HANDLES).toEqual(['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w']);
  });

  it('grows from the east and south without moving the origin', () => {
    expect(resizeRect(RECT, 'e', { dxMm: 10, dyMm: 0 })).toMatchObject({
      xMm: 20,
      widthMm: 50,
    });
    expect(resizeRect(RECT, 's', { dxMm: 0, dyMm: 10 })).toMatchObject({
      yMm: 30,
      heightMm: 30,
    });
  });

  it('moves the origin *and* the size from the west and north', () => {
    // Dragging the left edge right must not move the right edge.
    expect(resizeRect(RECT, 'w', { dxMm: 10, dyMm: 0 })).toMatchObject({
      xMm: 30,
      widthMm: 30,
    });
    expect(resizeRect(RECT, 'n', { dxMm: 0, dyMm: 10 })).toMatchObject({
      yMm: 40,
      heightMm: 10,
    });
  });

  it('resizes both axes from a corner', () => {
    expect(resizeRect(RECT, 'se', { dxMm: 10, dyMm: 10 })).toMatchObject({
      xMm: 20,
      yMm: 30,
      widthMm: 50,
      heightMm: 30,
    });
    expect(resizeRect(RECT, 'nw', { dxMm: 5, dyMm: 5 })).toMatchObject({
      xMm: 25,
      yMm: 35,
      widthMm: 35,
      heightMm: 15,
    });
  });

  it('stops at the minimum rather than inverting the rectangle', () => {
    const squashed = resizeRect(RECT, 'w', { dxMm: 500, dyMm: 0 }, { minMm: 1 });
    expect(squashed.widthMm).toBe(1);
    // The far edge stayed where it was: 20 + 40 = 60, minus the 1mm that is left.
    expect(squashed.xMm).toBe(59);

    const flattened = resizeRect(RECT, 'n', { dxMm: 0, dyMm: 500 }, { minMm: 2 });
    expect(flattened.heightMm).toBe(2);
    expect(flattened.yMm).toBe(48);
  });

  it('never grows past its bounds', () => {
    expect(resizeRect(RECT, 'e', { dxMm: 500, dyMm: 0 }, { bounds: ZONE }).widthMm).toBe(170);
    expect(resizeRect(RECT, 's', { dxMm: 0, dyMm: 500 }, { bounds: ZONE }).heightMm).toBe(70);
    expect(resizeRect(RECT, 'w', { dxMm: -500, dyMm: 0 }, { bounds: ZONE })).toMatchObject({
      xMm: 0,
      widthMm: 60,
    });
  });

  it('snaps the edge being dragged to the grid', () => {
    expect(resizeRect(RECT, 'e', { dxMm: 3, dyMm: 0 }, { snapMm: 5 }).widthMm).toBe(45);
    expect(resizeRect(RECT, 'w', { dxMm: 3, dyMm: 0 }, { snapMm: 5 })).toMatchObject({
      xMm: 25,
      widthMm: 35,
    });
  });

  it('ignores the axis a side handle does not control', () => {
    expect(resizeRect(RECT, 'e', { dxMm: 10, dyMm: 50 })).toMatchObject({
      heightMm: 20,
      yMm: 30,
    });
    expect(resizeRect(RECT, 'n', { dxMm: 50, dyMm: 5 })).toMatchObject({
      widthMm: 40,
      xMm: 20,
    });
  });
});

describe('alignmentGuides', () => {
  const others = [
    { xMm: 20, yMm: 80, widthMm: 40, heightMm: 10 }, // same left edge, same centre
    { xMm: 100, yMm: 10, widthMm: 20, heightMm: 20 },
  ];

  it('finds an edge that agrees and offers the correction', () => {
    const near = { xMm: 20.6, yMm: 30, widthMm: 40, heightMm: 20 };
    const result = alignmentGuides(near, others, 1);
    expect(result.guides).toEqual(
      expect.arrayContaining([{ axis: 'x', atMm: 20, kind: 'edge' }]),
    );
    expect(result.snapDxMm).toBe(-0.6);
  });

  it('finds agreeing centres', () => {
    // Both are 40mm wide at x=20, so their centres are both 40mm.
    const result = alignmentGuides({ xMm: 19.5, yMm: 30, widthMm: 40, heightMm: 20 }, others, 1);
    expect(result.guides.some((guide) => guide.kind === 'centre')).toBe(true);
  });

  it('never matches an edge against a centre, which is a coincidence not an alignment', () => {
    // This rectangle's left edge sits exactly on the other's centre (40mm).
    const result = alignmentGuides({ xMm: 40, yMm: 200, widthMm: 5, heightMm: 5 }, others, 1);
    expect(result.guides).toEqual([]);
    expect(result.snapDxMm).toBe(0);
  });

  it('offers nothing outside the tolerance', () => {
    const far = { xMm: 24, yMm: 37, widthMm: 40, heightMm: 20 };
    expect(alignmentGuides(far, others, 1).guides).toEqual([]);
    expect(alignmentGuides(far, others, 5).guides.length).toBeGreaterThan(0);
  });

  it('takes the nearest candidate per axis', () => {
    const crowd = [
      { xMm: 10, yMm: 0, widthMm: 5, heightMm: 5 },
      { xMm: 10.8, yMm: 0, widthMm: 5, heightMm: 5 },
    ];
    const result = alignmentGuides({ xMm: 11, yMm: 50, widthMm: 5, heightMm: 5 }, crowd, 2);
    // 10.8 is 0.2 away, 10 is 1.0 away.
    expect(result.snapDxMm).toBeCloseTo(-0.2, 5);
  });

  it('lists one line per position, however many rectangles agree on it', () => {
    const stacked = [
      { xMm: 20, yMm: 0, widthMm: 40, heightMm: 5 },
      { xMm: 20, yMm: 60, widthMm: 40, heightMm: 5 },
      { xMm: 20, yMm: 90, widthMm: 40, heightMm: 5 },
    ];
    const result = alignmentGuides(RECT, stacked, 1);
    const left = result.guides.filter((guide) => guide.axis === 'x' && guide.atMm === 20);
    expect(left).toHaveLength(1);
  });

  it('returns no correction when there is nothing to align to', () => {
    expect(alignmentGuides(RECT, [], 1)).toEqual({ guides: [], snapDxMm: 0, snapDyMm: 0 });
  });
});
