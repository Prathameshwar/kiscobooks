'use client';

import type { KeyboardEvent as ReactKeyboardEvent } from 'react';
import type { CanvasDefinition } from './layout-model';
import { type Target, elementsOf, navigate, zoneLabel } from './selection';

/**
 * The page's structure, as a tree in the rail.
 *
 * It exists for two reasons the canvas cannot cover. A designer needs to find an element
 * that is behind another one or two millimetres tall, and a keyboard user needs a list
 * they can read rather than a surface they must probe. Both views drive the same selection,
 * so neither can disagree about what is selected.
 *
 * Roving tabindex, as the tree pattern requires: one tab stop for the whole tree, arrows
 * move within it. The arrow keys resolve through the same `navigate` model the canvas uses,
 * so `Down` means the same thing in both places.
 *
 * Multi-selection reads the same way here as on the canvas: `aria-selected` marks every
 * member, and shift or ctrl adds. `aria-multiselectable` on the tree says so once.
 */

type ElementTreeProps = {
  layout: CanvasDefinition;
  targets: readonly Target[];
  /** The active node: where the tab stop sits and where the arrows move from. */
  selectedId: string | null;
  /** The whole selection. Defaults to just the active one. */
  selectedIds?: readonly string[];
  onSelect: (id: string | null, intent?: { additive?: boolean }) => void;
  onHover: (id: string | null) => void;
};

export function ElementTree({
  layout,
  targets,
  selectedId,
  selectedIds,
  onSelect,
  onHover,
}: ElementTreeProps) {
  const chosen = new Set(selectedIds ?? (selectedId ? [selectedId] : []));
  /** Shift and ctrl both add, the same two keys the canvas accepts. */
  const intentOf = (event: { shiftKey: boolean; ctrlKey: boolean; metaKey: boolean }) => ({
    additive: event.shiftKey || event.ctrlKey || event.metaKey,
  });
  function onKeyDown(event: ReactKeyboardEvent<HTMLUListElement>) {
    const commands = {
      ArrowDown: 'next',
      ArrowUp: 'previous',
      ArrowRight: 'child',
      ArrowLeft: 'parent',
      Home: 'first',
      End: 'last',
      Escape: 'clear',
    } as const;
    const command = commands[event.key as keyof typeof commands];
    if (!command) return;
    event.preventDefault();
    onSelect(navigate(targets, selectedId, command), {
      additive: event.shiftKey && command !== 'clear',
    });
  }

  /** The one node that holds the tab stop: the selection, or the first zone. */
  const roving = selectedId ?? layout.sections[0]?.id ?? null;

  return (
    <ul
      className="janso-editor__tree"
      role="tree"
      aria-label="Page structure"
      aria-multiselectable={true}
      onKeyDown={onKeyDown}
    >
      {layout.sections.map((section) => {
        const children = elementsOf(targets, section.id);
        return (
          <li key={section.id} role="none">
            <button
              type="button"
              className="janso-editor__node janso-editor__node--zone"
              role="treeitem"
              aria-selected={chosen.has(section.id)}
              data-active={section.id === selectedId || undefined}
              /* Only when there is something to expand: `false` on a leaf tells a
               * screen reader there is hidden content, and there is none. */
              aria-expanded={children.length > 0 ? true : undefined}
              aria-level={1}
              tabIndex={roving === section.id ? 0 : -1}
              onClick={(event) => onSelect(section.id, intentOf(event))}
              onPointerEnter={() => onHover(section.id)}
              onPointerLeave={() => onHover(null)}
              onFocus={() => onHover(section.id)}
              onBlur={() => onHover(null)}
            >
              <span className="janso-editor__twisty" aria-hidden="true">
                {children.length > 0 ? '▾' : '·'}
              </span>
              {zoneLabel(section)}
              <span className="janso-editor__node-kind">{children.length}</span>
            </button>

            {children.length > 0 ? (
              <ul className="janso-editor__tree" role="group">
                {children.map((child) => (
                  <li key={child.id} role="none">
                    <button
                      type="button"
                      className="janso-editor__node"
                      role="treeitem"
                      aria-selected={chosen.has(child.id)}
                      data-active={child.id === selectedId || undefined}
                      aria-level={2}
                      tabIndex={roving === child.id ? 0 : -1}
                      onClick={(event) => onSelect(child.id, intentOf(event))}
                      onPointerEnter={() => onHover(child.id)}
                      onPointerLeave={() => onHover(null)}
                      onFocus={() => onHover(child.id)}
                      onBlur={() => onHover(null)}
                    >
                      {child.label}
                      <span className="janso-editor__node-kind">
                        {child.element?.type.toLowerCase().replace(/_/g, ' ')}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}
