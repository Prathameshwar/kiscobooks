/**
 * Moving and resizing a rectangle on paper, and the guides that help you aim.
 *
 * Pure millimetre arithmetic, deliberately framework-free: a drag is the one interaction
 * where "it felt wrong" is hard to debug through a component, and every rule here —
 * which edges a handle moves, when a snap wins, what counts as aligned — is a decision
 * worth stating once and testing without a pointer.
 */

import { roundMm, snapMm as snapToStep } from './paper';

export type Handle = 'nw' | 'n' | 'ne' | 'e' | 'se' | 's' | 'sw' | 'w';

/** The eight handles, clockwise from the top-left, as the ring draws them. */
export const HANDLES: readonly Handle[] = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'];

export type MmRect = {
  readonly xMm: number;
  readonly yMm: number;
  readonly widthMm: number;
  readonly heightMm: number;
};

export type TransformBounds = {
  /** The box the rectangle must stay inside — its zone, or the page. */
  readonly widthMm: number;
  readonly heightMm: number;
};

export type TransformOptions = {
  readonly bounds?: TransformBounds;
  /** Millimetres to snap to, or `0` for free movement. */
  readonly snapMm?: number;
  readonly minMm?: number;
};

/**
 * Move a rectangle by a delta, snapped and kept inside its bounds.
 *
 * The *position* is snapped, not the delta: snapping a delta lets a rectangle that started
 * at 12.3mm stay forever off-grid, which is the thing a grid exists to prevent.
 */
export function moveRect(
  rect: MmRect,
  deltaMm: { readonly dxMm: number; readonly dyMm: number },
  { bounds, snapMm = 0 }: TransformOptions = {},
): MmRect {
  let xMm = snapToStep(rect.xMm + deltaMm.dxMm, snapMm);
  let yMm = snapToStep(rect.yMm + deltaMm.dyMm, snapMm);
  if (bounds) {
    xMm = Math.min(Math.max(0, xMm), roundMm(Math.max(0, bounds.widthMm - rect.widthMm)));
    yMm = Math.min(Math.max(0, yMm), roundMm(Math.max(0, bounds.heightMm - rect.heightMm)));
  }
  return { ...rect, xMm, yMm };
}

/**
 * Resize a rectangle by dragging one handle.
 *
 * A north or west handle moves the edge *and* the origin, which is the part that is easy
 * to get wrong: dragging the top edge down must not move the bottom edge up. Below the
 * minimum the rectangle stops rather than inverting — a negative height is not a smaller
 * box, it is a different one.
 */
export function resizeRect(
  rect: MmRect,
  handle: Handle,
  deltaMm: { readonly dxMm: number; readonly dyMm: number },
  { bounds, snapMm = 0, minMm = 1 }: TransformOptions = {},
): MmRect {
  const west = handle === 'nw' || handle === 'w' || handle === 'sw';
  const east = handle === 'ne' || handle === 'e' || handle === 'se';
  const north = handle === 'nw' || handle === 'n' || handle === 'ne';
  const south = handle === 'sw' || handle === 's' || handle === 'se';

  const right = rect.xMm + rect.widthMm;
  const bottom = rect.yMm + rect.heightMm;

  let xMm = rect.xMm;
  let yMm = rect.yMm;
  let widthMm = rect.widthMm;
  let heightMm = rect.heightMm;

  if (west) {
    // The far edge is fixed, so the near edge is what the snap applies to.
    const limit = bounds ? Math.max(0, right - minMm) : right - minMm;
    xMm = Math.min(Math.max(0, snapToStep(rect.xMm + deltaMm.dxMm, snapMm)), roundMm(limit));
    widthMm = roundMm(right - xMm);
  } else if (east) {
    const maximum = bounds ? bounds.widthMm - rect.xMm : Number.POSITIVE_INFINITY;
    widthMm = Math.min(
      Math.max(minMm, snapToStep(rect.xMm + rect.widthMm + deltaMm.dxMm, snapMm) - rect.xMm),
      roundMm(maximum),
    );
  }

  if (north) {
    const limit = bounds ? Math.max(0, bottom - minMm) : bottom - minMm;
    yMm = Math.min(Math.max(0, snapToStep(rect.yMm + deltaMm.dyMm, snapMm)), roundMm(limit));
    heightMm = roundMm(bottom - yMm);
  } else if (south) {
    const maximum = bounds ? bounds.heightMm - rect.yMm : Number.POSITIVE_INFINITY;
    heightMm = Math.min(
      Math.max(minMm, snapToStep(rect.yMm + rect.heightMm + deltaMm.dyMm, snapMm) - rect.yMm),
      roundMm(maximum),
    );
  }

  return {
    xMm: roundMm(xMm),
    yMm: roundMm(yMm),
    widthMm: roundMm(Math.max(minMm, widthMm)),
    heightMm: roundMm(Math.max(minMm, heightMm)),
  };
}

export type Guide = {
  readonly axis: 'x' | 'y';
  /** Where to draw it, in paper millimetres. */
  readonly atMm: number;
  /** What agreed: an edge with an edge, or two centres. */
  readonly kind: 'edge' | 'centre';
};

export type GuideResult = {
  readonly guides: readonly Guide[];
  /** Millimetres to add to the rectangle so it lands exactly on the guide it is near. */
  readonly snapDxMm: number;
  readonly snapDyMm: number;
};

/**
 * Alignment guides between a moving rectangle and the ones it is near.
 *
 * Why this exists rather than relying on the grid: a designer aligning a total to the
 * column above it does not care where the grid is, they care that the two edges agree.
 * Guides find that agreement and offer the small correction that makes it exact.
 *
 * Within the tolerance, the *nearest* candidate wins per axis, and a centre beats an edge
 * at equal distance — centring is the more deliberate act, so it should feel stickier.
 */
export function alignmentGuides(
  rect: MmRect,
  others: readonly MmRect[],
  toleranceMm = 1,
): GuideResult {
  const guides: Guide[] = [];
  let best: Record<'x' | 'y', { delta: number; distance: number; kind: Guide['kind'] } | null> = {
    x: null,
    y: null,
  };

  const linesOf = (box: MmRect) => ({
    x: [
      { at: box.xMm, kind: 'edge' as const },
      { at: roundMm(box.xMm + box.widthMm / 2), kind: 'centre' as const },
      { at: roundMm(box.xMm + box.widthMm), kind: 'edge' as const },
    ],
    y: [
      { at: box.yMm, kind: 'edge' as const },
      { at: roundMm(box.yMm + box.heightMm / 2), kind: 'centre' as const },
      { at: roundMm(box.yMm + box.heightMm), kind: 'edge' as const },
    ],
  });

  const moving = linesOf(rect);

  for (const other of others) {
    const lines = linesOf(other);
    for (const axis of ['x', 'y'] as const) {
      for (const mine of moving[axis]) {
        for (const theirs of lines[axis]) {
          const distance = Math.abs(mine.at - theirs.at);
          if (distance > toleranceMm) continue;
          // Only ever compare like with like: an edge lining up with a centre is a
          // coincidence, not an alignment, and drawing it would be noise.
          if (mine.kind !== theirs.kind) continue;

          guides.push({ axis, atMm: theirs.at, kind: theirs.kind });
          const candidate = { delta: roundMm(theirs.at - mine.at), distance, kind: theirs.kind };
          const champion = best[axis];
          const better =
            !champion ||
            candidate.distance < champion.distance ||
            (candidate.distance === champion.distance &&
              candidate.kind === 'centre' &&
              champion.kind === 'edge');
          if (better) best = { ...best, [axis]: candidate };
        }
      }
    }
  }

  // One line per position: three edges against three edges can agree twice over.
  const unique = guides.filter(
    (guide, index) =>
      guides.findIndex(
        (candidate) =>
          candidate.axis === guide.axis &&
          candidate.atMm === guide.atMm &&
          candidate.kind === guide.kind,
      ) === index,
  );

  return {
    guides: unique,
    snapDxMm: best.x?.delta ?? 0,
    snapDyMm: best.y?.delta ?? 0,
  };
}
