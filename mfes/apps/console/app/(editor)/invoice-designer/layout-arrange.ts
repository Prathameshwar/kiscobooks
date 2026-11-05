/**
 * Editing a *set* of elements: move together, line up, space evenly, restack, copy, remove.
 *
 * Separate from `layout-edit.ts` because these are not the single-element operations run in
 * a loop, and treating them that way is the bug:
 *
 *   **Aligning each element on its own aligns each to itself** — six buttons that do
 *   nothing. Alignment is against the box around the whole selection.
 *
 *   **Moving each element on its own lets one stop at its zone edge while the rest carry
 *   on**, silently destroying the arrangement the designer had just made. A group move
 *   reduces the delta until every member can take it.
 *
 * Page coordinates throughout, because a designer lines a total up with a column and those
 * live in different zones. Every result is converted back into its own zone and clamped
 * there by `fit`, so the rule that an element never leaves its zone still holds.
 *
 * Pure functions, no framework, no mutation — the same contract as `layout-edit.ts`, so
 * each one is tested without rendering anything and undo gets them free.
 */

import { roundMm, snapMm as snapToStep } from '@janso/ui';

import { elementIds, fit, freeId } from './layout-edit';
import type { CanvasDefinition, CanvasElement, CanvasSection } from './layout-model';

export type MmRect = { xMm: number; yMm: number; widthMm: number; heightMm: number };

/** An element with the zone that owns it, which is what any of this needs to be correct. */
export type ElementRef = { section: CanvasSection; element: CanvasElement };

/** The selected elements, in page order, ignoring ids that name a zone or nothing. */
export function refsOf(layout: CanvasDefinition, ids: readonly string[]): ElementRef[] {
  const wanted = new Set(ids);
  const refs: ElementRef[] = [];
  for (const section of layout.sections) {
    for (const element of section.elements) {
      if (wanted.has(element.id)) refs.push({ section, element });
    }
  }
  return refs;
}

/** An element's box in page millimetres. */
export function pageRect(ref: ElementRef): MmRect {
  return {
    xMm: roundMm(ref.section.xMm + ref.element.xMm),
    yMm: roundMm(ref.section.yMm + ref.element.yMm),
    widthMm: ref.element.widthMm,
    heightMm: ref.element.heightMm,
  };
}

/** The box around a set of elements, in page millimetres; `null` for an empty set. */
export function selectionBounds(layout: CanvasDefinition, ids: readonly string[]): MmRect | null {
  const rects = refsOf(layout, ids).map(pageRect);
  if (rects.length === 0) return null;
  const left = Math.min(...rects.map((rect) => rect.xMm));
  const top = Math.min(...rects.map((rect) => rect.yMm));
  const right = Math.max(...rects.map((rect) => rect.xMm + rect.widthMm));
  const bottom = Math.max(...rects.map((rect) => rect.yMm + rect.heightMm));
  return {
    xMm: roundMm(left),
    yMm: roundMm(top),
    widthMm: roundMm(right - left),
    heightMm: roundMm(bottom - top),
  };
}

/** Write new zone-relative positions for a set of elements in one pass. */
function placeAll(
  layout: CanvasDefinition,
  moves: ReadonlyMap<string, { xMm: number; yMm: number }>,
): CanvasDefinition {
  if (moves.size === 0) return layout;
  return {
    ...layout,
    sections: layout.sections.map((section) => {
      if (!section.elements.some((element) => moves.has(element.id))) return section;
      return {
        ...section,
        elements: section.elements.map((element) => {
          const move = moves.get(element.id);
          return move ? fit({ ...element, ...move }, section) : element;
        }),
      };
    }),
  };
}

/**
 * Move a set of elements by one delta.
 *
 * The delta is reduced until *every* member can take it, rather than clamping each element
 * separately: the group stops when its first member would leave its zone, so the
 * arrangement survives the gesture.
 *
 * Snapping applies to the anchor — the element under the pointer. Snapping each member
 * separately would pull them apart by up to a grid step each.
 */
export function moveSelection(
  layout: CanvasDefinition,
  ids: readonly string[],
  deltaMm: { dxMm: number; dyMm: number },
  options: { snapMm?: number; anchorId?: string | null } = {},
): CanvasDefinition {
  const refs = refsOf(layout, ids);
  const anchor = refs.find((ref) => ref.element.id === options.anchorId) ?? refs[0];
  if (!anchor) return layout;
  const snapMm = options.snapMm ?? 0;
  const anchorElement = anchor.element;

  function reduce(requested: number, axis: 'x' | 'y'): number {
    const anchorAt = axis === 'x' ? anchorElement.xMm : anchorElement.yMm;
    const snapped = snapMm > 0 ? snapToStep(anchorAt + requested, snapMm) - anchorAt : requested;
    let lower = Number.NEGATIVE_INFINITY;
    let upper = Number.POSITIVE_INFINITY;
    for (const ref of refs) {
      const at = axis === 'x' ? ref.element.xMm : ref.element.yMm;
      const size = axis === 'x' ? ref.element.widthMm : ref.element.heightMm;
      const room = axis === 'x' ? ref.section.widthMm : ref.section.heightMm;
      lower = Math.max(lower, -at);
      upper = Math.min(upper, Math.max(0, room - size) - at);
    }
    // Zero is inside every member's range, so the window is never empty.
    return roundMm(Math.min(Math.max(snapped, lower), upper));
  }

  const dxMm = reduce(deltaMm.dxMm, 'x');
  const dyMm = reduce(deltaMm.dyMm, 'y');
  if (dxMm === 0 && dyMm === 0) return layout;

  return placeAll(
    layout,
    new Map(
      refs.map((ref) => [
        ref.element.id,
        { xMm: roundMm(ref.element.xMm + dxMm), yMm: roundMm(ref.element.yMm + dyMm) },
      ]),
    ),
  );
}

export type AlignEdge = 'left' | 'centreX' | 'right' | 'top' | 'middleY' | 'bottom';

export const ALIGN_LABELS: Record<AlignEdge, string> = {
  left: 'Align left',
  centreX: 'Align centres',
  right: 'Align right',
  top: 'Align top',
  middleY: 'Align middles',
  bottom: 'Align bottom',
};

/**
 * Line a set of elements up on one edge, or on their shared centre line.
 *
 * **One element aligns to its zone, not to itself.** Aligning a single element against its
 * own bounding box is a no-op, and a button that does nothing teaches a designer to stop
 * pressing it; "put this against the left edge of its zone" is what they meant.
 */
export function alignElements(
  layout: CanvasDefinition,
  ids: readonly string[],
  edge: AlignEdge,
): CanvasDefinition {
  const refs = refsOf(layout, ids);
  if (refs.length === 0) return layout;

  const group = refs.length > 1 ? selectionBounds(layout, ids) : null;
  const moves = new Map<string, { xMm: number; yMm: number }>();

  for (const ref of refs) {
    // With one element the frame is its zone, in page coordinates, so both cases run
    // through one piece of arithmetic.
    const frame: MmRect = group ?? {
      xMm: ref.section.xMm,
      yMm: ref.section.yMm,
      widthMm: ref.section.widthMm,
      heightMm: ref.section.heightMm,
    };
    const rect = pageRect(ref);
    let xMm = rect.xMm;
    let yMm = rect.yMm;
    if (edge === 'left') xMm = frame.xMm;
    if (edge === 'centreX') xMm = frame.xMm + (frame.widthMm - rect.widthMm) / 2;
    if (edge === 'right') xMm = frame.xMm + frame.widthMm - rect.widthMm;
    if (edge === 'top') yMm = frame.yMm;
    if (edge === 'middleY') yMm = frame.yMm + (frame.heightMm - rect.heightMm) / 2;
    if (edge === 'bottom') yMm = frame.yMm + frame.heightMm - rect.heightMm;
    moves.set(ref.element.id, {
      xMm: roundMm(xMm - ref.section.xMm),
      yMm: roundMm(yMm - ref.section.yMm),
    });
  }
  return placeAll(layout, moves);
}

/** Distributing needs a first, a last, and something between them to space out. */
export const MIN_DISTRIBUTE = 3;

/**
 * Space a set evenly along one axis, equalising the *gaps* rather than the centres.
 *
 * Gaps are what the eye reads on a document: three fields of different widths with equal
 * centres look wrong, and with equal gaps look deliberate. The outermost two stay where
 * they are — they are the frame the designer already chose.
 */
export function distributeElements(
  layout: CanvasDefinition,
  ids: readonly string[],
  axis: 'x' | 'y',
): CanvasDefinition {
  const refs = refsOf(layout, ids);
  if (refs.length < MIN_DISTRIBUTE) return layout;

  const sized = refs
    .map((ref) => ({ ref, rect: pageRect(ref) }))
    .sort((left, right) =>
      axis === 'x' ? left.rect.xMm - right.rect.xMm : left.rect.yMm - right.rect.yMm,
    );

  const first = sized[0];
  const last = sized[sized.length - 1];
  if (!first || !last) return layout;

  const start = axis === 'x' ? first.rect.xMm : first.rect.yMm;
  const end =
    axis === 'x' ? last.rect.xMm + last.rect.widthMm : last.rect.yMm + last.rect.heightMm;
  const occupied = sized.reduce(
    (sum, entry) => sum + (axis === 'x' ? entry.rect.widthMm : entry.rect.heightMm),
    0,
  );
  // Already overlapping: there is no space to share, so butt them together rather than
  // computing a negative gap and scattering them.
  const gap = Math.max(0, (end - start - occupied) / (sized.length - 1));

  const moves = new Map<string, { xMm: number; yMm: number }>();
  let cursor = start;
  for (const entry of sized) {
    const size = axis === 'x' ? entry.rect.widthMm : entry.rect.heightMm;
    const zoneAt = axis === 'x' ? entry.ref.section.xMm : entry.ref.section.yMm;
    moves.set(entry.ref.element.id, {
      xMm: axis === 'x' ? roundMm(cursor - zoneAt) : entry.ref.element.xMm,
      yMm: axis === 'y' ? roundMm(cursor - zoneAt) : entry.ref.element.yMm,
    });
    cursor += size + gap;
  }
  return placeAll(layout, moves);
}

export type ZOrder = 'front' | 'forward' | 'backward' | 'back';

export const ZORDER_LABELS: Record<ZOrder, string> = {
  front: 'Bring to front',
  forward: 'Bring forward',
  backward: 'Send backward',
  back: 'Send to back',
};

/**
 * Change what is painted over what, within each zone.
 *
 * **Array order and `zIndex` are written together, by this one function.** The preview
 * paints in DOM order, the schema carries `zIndex`, and the rail's tree shows the array —
 * so a reorder that set only one of the three would leave the editor disagreeing with
 * itself about which thing is in front. They cannot drift while this is the only writer.
 *
 * Stacking is per zone: zones are laid out in sequence, and an element cannot rise above
 * the zone that contains it.
 */
export function reorderElements(
  layout: CanvasDefinition,
  ids: readonly string[],
  order: ZOrder,
): CanvasDefinition {
  const wanted = new Set(ids);
  let changed = false;

  const sections = layout.sections.map((section) => {
    const picked = section.elements.filter((element) => wanted.has(element.id));
    // Nothing selected here, or everything is: either way there is no relative order to
    // change inside this zone.
    if (picked.length === 0 || picked.length === section.elements.length) return section;

    const stack = [...section.elements];

    if (order === 'front' || order === 'back') {
      const rest = stack.filter((element) => !wanted.has(element.id));
      const moved = order === 'front' ? [...rest, ...picked] : [...picked, ...rest];
      if (moved.every((element, index) => element === stack[index])) return section;
      changed = true;
      return { ...section, elements: moved.map(withDepth) };
    }

    // One step at a time, walking from the edge the elements are moving towards, so two
    // selected neighbours cannot swap with each other and end up where they started.
    const step = order === 'forward' ? 1 : -1;
    const walk = order === 'forward' ? [...picked].reverse() : picked;
    let moved = false;
    for (const element of walk) {
      const from = stack.indexOf(element);
      const to = from + step;
      const neighbour = stack[to];
      if (to < 0 || to >= stack.length || !neighbour || wanted.has(neighbour.id)) continue;
      stack[from] = neighbour;
      stack[to] = element;
      moved = true;
    }
    if (!moved) return section;
    changed = true;
    return { ...section, elements: stack.map(withDepth) };
  });

  return changed ? { ...layout, sections } : layout;
}

/** `zIndex` restated as position, so the two representations always agree. */
function withDepth(element: CanvasElement, index: number): CanvasElement {
  return element.zIndex === index ? element : { ...element, zIndex: index };
}

/** Where an element sits in its zone's stack, for the panel to state. */
export function depthOf(layout: CanvasDefinition, id: string): { at: number; of: number } | null {
  for (const section of layout.sections) {
    const index = section.elements.findIndex((element) => element.id === id);
    if (index >= 0) return { at: index + 1, of: section.elements.length };
  }
  return null;
}

/**
 * Copy a set of elements, offset so the copy is visibly a copy.
 *
 * Each copy lands directly after its source in the stack — where a designer expects to find
 * it in the tree, and the right paint order, since a duplicate belongs on top of the thing
 * it was duplicated from.
 *
 * **The offset turns inwards when there is no room outwards.** An element flush against the
 * right edge of its zone cannot be copied 2mm further right: the copy would be clamped back
 * onto its source and look like nothing happened. So the offset goes the other way instead,
 * and a copy is always visibly a copy.
 */
export function duplicateElements(
  layout: CanvasDefinition,
  ids: readonly string[],
  offsetMm = 2,
): { layout: CanvasDefinition; ids: string[] } {
  const wanted = new Set(ids);
  const taken = elementIds(layout);
  const made: string[] = [];

  const sections = layout.sections.map((section) => {
    if (!section.elements.some((element) => wanted.has(element.id))) return section;
    const elements: CanvasElement[] = [];
    for (const element of section.elements) {
      elements.push(element);
      if (!wanted.has(element.id)) continue;
      const id = freeId(taken, `${element.id}-copy`);
      taken.add(id);
      made.push(id);
      const dxMm =
        element.xMm + element.widthMm + offsetMm <= section.widthMm ? offsetMm : -offsetMm;
      const dyMm =
        element.yMm + element.heightMm + offsetMm <= section.heightMm ? offsetMm : -offsetMm;
      elements.push(
        fit(
          { ...element, id, xMm: roundMm(element.xMm + dxMm), yMm: roundMm(element.yMm + dyMm) },
          section,
        ),
      );
    }
    return { ...section, elements };
  });

  if (made.length === 0) return { layout, ids: [] };
  return { layout: { ...layout, sections }, ids: made };
}

/**
 * Remove a set of elements.
 *
 * A zone is never deleted here — it is structure the renderer lays out, not an object on the
 * page — and an emptied zone stays, because a document that carries no bank details still
 * has a footer.
 */
export function deleteElements(
  layout: CanvasDefinition,
  ids: readonly string[],
): CanvasDefinition {
  const wanted = new Set(ids);
  let changed = false;
  const sections = layout.sections.map((section) => {
    const elements = section.elements.filter((element) => !wanted.has(element.id));
    if (elements.length === section.elements.length) return section;
    changed = true;
    return { ...section, elements };
  });
  return changed ? { ...layout, sections } : layout;
}
