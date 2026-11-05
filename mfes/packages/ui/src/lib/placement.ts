'use client';

import {
  useCallback,
  useLayoutEffect,
  useState,
  type CSSProperties,
  type RefObject,
} from 'react';

/**
 * Places a portalled panel against an anchor, in the viewport rather than in the anchor's parent.
 *
 * Absolute positioning inside the parent is what made `UserMenu` render as a clipped sliver
 * inside the top bar: any ancestor with `overflow` clips a descendant popover. A picker, a menu
 * and a row kebab all sit inside cards, toolbars and scroll regions — and `DataTable`'s own
 * horizontal scroller is exactly such an ancestor — so a panel cannot depend on its ancestors.
 * Hence a portal, `position: fixed`, and re-placing on **capture-phase** scroll so an ancestor
 * scrolling counts too.
 *
 * Shared because this is the second control that needs it (`SearchSelect`, then `Menu`), and two
 * copies of viewport flipping is how they drift apart (CLAUDE.md §3).
 */

/** Geometry only — no token can express a rectangle measured at runtime. */
export type Placement = { style: CSSProperties; flipped: boolean };

export type PlacementOptions = {
  /** The intrinsic-width panel, measured after its portal mounts to prevent edge overflow. */
  panel?: RefObject<HTMLElement | null>;
  /**
   * The panel spans the anchor's width — a dropdown *list*, whose rows belong to the field above
   * them. A menu instead takes its own width and lines up by `align`.
   */
  matchWidth?: boolean;
  /** Which anchor edge an intrinsic-width panel lines up with. Ignored when `matchWidth`. */
  align?: 'start' | 'end';
  gap?: number;
  /** Preferred room when choosing a side; never forces overflow in a short viewport. */
  minHeight?: number;
  maxHeight?: number;
  /** Below this much room beneath the anchor, the panel may flip above it. */
  flipBelow?: number;
};

/**
 * Whether two measurements would paint the same panel.
 *
 * `place()` runs on every capture-phase scroll event, and returning a fresh object each time is a
 * fresh render of the anchor *and* every row on screen — for a rectangle that, while someone
 * scrolls a page with the panel open, usually has not moved. Comparing six numbers is far cheaper
 * than re-rendering two hundred options per scroll frame.
 */
function samePlacement(a: Placement, b: Placement): boolean {
  return (
    a.flipped === b.flipped &&
    a.style.left === b.style.left &&
    a.style.right === b.style.right &&
    a.style.width === b.style.width &&
    a.style.maxHeight === b.style.maxHeight &&
    a.style.top === b.style.top &&
    a.style.bottom === b.style.bottom
  );
}

export function usePlacement(
  anchor: RefObject<HTMLElement | null>,
  open: boolean,
  options: PlacementOptions = {},
): Placement | null {
  const {
    panel,
    matchWidth = false,
    align = 'start',
    gap = 6,
    minHeight = 120,
    maxHeight = 340,
    flipBelow = 200,
  } = options;
  const [placement, setPlacement] = useState<Placement | null>(null);

  const place = useCallback(() => {
    const node = anchor.current;
    if (!open || !node) {
      setPlacement(null);
      return;
    }

    const rect = node.getBoundingClientRect();
    // Focus can precede a scroll container bringing its row into view. Anchor to
    // the visible viewport edge until that scroll finishes, never to a negative
    // bottom offset that puts the portalled panel outside the screen.
    const edge = 8;
    const anchorTop = Math.max(edge, Math.min(rect.top, window.innerHeight - edge));
    const anchorBottom = Math.max(edge, Math.min(rect.bottom, window.innerHeight - edge));
    const below = Math.max(0, window.innerHeight - edge - anchorBottom - gap);
    const above = Math.max(0, anchorTop - gap - edge);
    // Flip only when below is genuinely too tight and above is roomier — flipping on a
    // near-tie makes the panel appear to jump as the page scrolls.
    const flipped = below < Math.max(flipBelow, minHeight) && above > below;
    const room = Math.min(maxHeight, flipped ? above : below);

    // Measure intrinsic menus and clamp both edges. Before the portal mounts, use
    // the requested anchor alignment; the next layout pass resolves its actual width.
    const panelWidth = panel?.current?.getBoundingClientRect().width;
    const left = align === 'end' ? rect.right - (panelWidth ?? 0) : rect.left;
    const across: CSSProperties = matchWidth
      ? { left: rect.left, width: rect.width }
      : panelWidth
        ? {
            left: Math.max(
              8,
              Math.min(left, window.innerWidth - panelWidth - 8),
            ),
          }
        : align === 'end'
          ? { right: Math.max(8, window.innerWidth - rect.right) }
          : { left: Math.max(8, rect.left) };

    const next: Placement = {
      flipped,
      style: {
        position: 'fixed',
        ...across,
        maxHeight: room,
        ...(flipped
          ? { bottom: window.innerHeight - anchorTop + gap }
          : { top: anchorBottom + gap }),
      },
    };
    setPlacement((prev) => (prev && samePlacement(prev, next) ? prev : next));
  }, [
    anchor,
    open,
    matchWidth,
    align,
    gap,
    minHeight,
    maxHeight,
    flipBelow,
    panel,
  ]);

  useLayoutEffect(() => {
    const node = anchor.current;
    if (!open || !node) {
      setPlacement(null);
      return;
    }
    place();
    /* Passive, because nothing in here calls `preventDefault`: a non-passive scroll listener on
     * the document keeps the browser from scrolling until it has run. */
    window.addEventListener('scroll', place, { capture: true, passive: true });
    window.addEventListener('resize', place, { passive: true });
    // jsdom has no ResizeObserver, and an anchor that never resizes is not worth a polyfill.
    const observer =
      typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(place);
    observer?.observe(node);

    return () => {
      window.removeEventListener('scroll', place, { capture: true });
      window.removeEventListener('resize', place);
      observer?.disconnect();
    };
  }, [anchor, open, place]);

  // The first placement mounts the portal. Measure its actual width before paint, and
  // repeat after content changes; unchanged geometry does not schedule another render.
  useLayoutEffect(() => {
    if (open && panel?.current) place();
  });

  return placement;
}
