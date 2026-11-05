/**
 * Selection: what can be selected on a page, and how the keyboard moves between them.
 *
 * Framework-free on purpose — it is a model over the layout, so it is tested without
 * rendering anything and the editor cannot grow a second, divergent idea of what "next"
 * means.
 *
 * **Two levels, not a flat list.** A page is zones, and each zone holds elements. Flatten
 * that into one sequence and `Down` walks out of the header into a table cell, which
 * matches no mental model anyone has of a document. So: `Down`/`Up` move between siblings,
 * `Right` enters a zone's elements, `Left` goes back out to the zone. That is the tree
 * convention, and it is learnable in one try.
 */

import { rectsOverlap } from '@janso/ui';

import type { CanvasDefinition, CanvasElement, CanvasSection } from './layout-model';

export type TargetKind = 'zone' | 'element';

export type Target = {
  id: string;
  kind: TargetKind;
  label: string;
  /** Absolute paper millimetres: an element's own box is relative to its zone. */
  rect: { xMm: number; yMm: number; widthMm: number; heightMm: number };
  /** The owning zone for an element; `null` for a zone. */
  zoneId: string | null;
  /** The underlying model row, for the inspector. */
  section: CanvasSection;
  element: CanvasElement | null;
};

/** A readable name for a zone: its title if it has one, else its type. */
export function zoneLabel(section: CanvasSection): string {
  if (section.title) return section.title;
  const words = section.type.toLowerCase().replace(/_/g, ' ');
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/**
 * A readable name for an element. The binding path or the first few words of its content
 * identify it far better than its type does — a page has eleven `FIELD_BINDING`s and a
 * designer thinks of them as "Invoice no." and "Place of supply".
 */
export function elementLabel(element: CanvasElement): string {
  if (element.label) return element.label;
  if (element.bindingPath) return element.bindingPath;
  if (element.content) {
    const trimmed = element.content.trim().replace(/\s+/g, ' ');
    return trimmed.length > 28 ? `${trimmed.slice(0, 27)}…` : trimmed;
  }
  return element.type.toLowerCase().replace(/_/g, ' ');
}

/** Every selectable thing on the page, zones first, each followed by its elements. */
export function targetsOf(layout: CanvasDefinition): Target[] {
  const targets: Target[] = [];
  for (const section of layout.sections) {
    targets.push({
      id: section.id,
      kind: 'zone',
      label: zoneLabel(section),
      rect: {
        xMm: section.xMm,
        yMm: section.yMm,
        widthMm: section.widthMm,
        heightMm: section.heightMm,
      },
      zoneId: null,
      section,
      element: null,
    });
    for (const element of section.elements) {
      targets.push({
        id: element.id,
        kind: 'element',
        label: elementLabel(element),
        rect: {
          xMm: section.xMm + element.xMm,
          yMm: section.yMm + element.yMm,
          widthMm: element.widthMm,
          heightMm: element.heightMm,
        },
        zoneId: section.id,
        section,
        element,
      });
    }
  }
  return targets;
}

export function targetById(targets: readonly Target[], id: string | null): Target | null {
  if (!id) return null;
  return targets.find((target) => target.id === id) ?? null;
}

export type SelectionCommand = 'next' | 'previous' | 'parent' | 'child' | 'first' | 'last' | 'clear';

/**
 * The id a command selects, given where the selection is now.
 *
 * Returns `null` to mean "nothing selected" and the current id to mean "no move" — so a
 * `Down` at the end of a zone's elements stays put rather than wrapping into the next
 * zone's header, which would feel like the page moved under the user.
 */
export function navigate(
  targets: readonly Target[],
  currentId: string | null,
  command: SelectionCommand,
): string | null {
  if (command === 'clear') return null;

  const zones = targets.filter((target) => target.kind === 'zone');
  if (zones.length === 0) return null;

  const current = targetById(targets, currentId);

  if (command === 'first') return (current?.kind === 'element' ? siblings(targets, current)[0]?.id : zones[0]?.id) ?? null;
  if (command === 'last') {
    const list = current?.kind === 'element' ? siblings(targets, current) : zones;
    return list[list.length - 1]?.id ?? null;
  }

  // Nothing selected yet: the first zone is the way in, whichever arrow was pressed.
  if (!current) return zones[0]?.id ?? null;

  if (command === 'child') {
    if (current.kind === 'zone') return firstElement(targets, current.id)?.id ?? current.id;
    return current.id;
  }

  if (command === 'parent') {
    return current.kind === 'element' ? (current.zoneId ?? current.id) : current.id;
  }

  const list = current.kind === 'zone' ? zones : siblings(targets, current);
  const index = list.findIndex((target) => target.id === current.id);
  const nextIndex = command === 'next' ? index + 1 : index - 1;
  if (nextIndex < 0 || nextIndex >= list.length) return current.id;
  return list[nextIndex]?.id ?? current.id;
}

function siblings(targets: readonly Target[], element: Target): Target[] {
  return targets.filter((target) => target.kind === 'element' && target.zoneId === element.zoneId);
}

function firstElement(targets: readonly Target[], zoneId: string): Target | null {
  return targets.find((target) => target.kind === 'element' && target.zoneId === zoneId) ?? null;
}

/** The elements of one zone, for the tree. */
export function elementsOf(targets: readonly Target[], zoneId: string): Target[] {
  return targets.filter((target) => target.kind === 'element' && target.zoneId === zoneId);
}

/**
 * The elements a rubber band caught.
 *
 * **Touching counts, not containing.** Every design tool works this way and for a good
 * reason: a 190mm-wide divider or an item table spanning the page can only be caught by a
 * band that covers the whole thing, so a containment rule would make the most awkward
 * elements to click the hardest to marquee as well. Zones are excluded — a band is for
 * picking up objects, and a zone that happens to sit under them is not what was aimed at.
 */
export function targetsInRect(
  targets: readonly Target[],
  rect: { xMm: number; yMm: number; widthMm: number; heightMm: number },
): string[] {
  return targets
    .filter((target) => target.kind === 'element' && rectsOverlap(target.rect, rect))
    .map((target) => target.id);
}
