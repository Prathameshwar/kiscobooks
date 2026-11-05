'use client';

import { useMemo, useState } from 'react';

import { ADDABLE_ELEMENTS, type AddableKind, addableFor, bindingLabel } from './layout-edit';
import type { LineProfile } from './layout-model';
import { sampleBindingPaths, sampleValue } from './sample-document';

/**
 * Everything the document can print, as a list you can place from.
 *
 * Why a palette and not a free-text field: binding paths are a **published contract** the
 * service validates against an allowlist (`sample-document.ts`), so a designer typing
 * `voucher.invoice_no` would get a box that previews fine and fails on save. Offering only
 * what resolves makes that mistake unavailable rather than merely discouraged.
 *
 * Why each row carries its sample value: `party.name` and `address.shipping_name` are
 * indistinguishable by name and obvious side by side — "Meridian Wholesale" against
 * "Meridian Wholesale (Nashik depot)". Choosing a field is really choosing between values,
 * so the values are on screen at the moment of choosing.
 *
 * Rows already on the page say so and stay enabled: a document legitimately prints the
 * same field twice — a GSTIN in the header and again beside the signature — and disabling
 * them would be guessing.
 */

/** What a palette row carries when it is dragged onto the page. */
export const DRAG_FIELD = 'application/x-janso-field';
export const DRAG_ELEMENT = 'application/x-janso-element';

type FieldPaletteProps = {
  /** Where a clicked row goes, and the name to say so with. */
  destination: { id: string; label: string } | null;
  /** Paths the layout already prints, so a row can be marked. */
  placed: ReadonlySet<string>;
  onPlace: (path: string) => void;
  /** Add a plain object — text, a line, a box, a signature — to the destination zone. */
  onAdd?: (kind: AddableKind) => void;
  readOnly?: boolean;
  /** What the design's lines are, so it offers the product table, the accounts table, or both. */
  lineProfile?: LineProfile;
};

/** A value on one line, short enough for a 280px rail. */
function preview(path: string): string {
  const value = sampleValue(path) ?? '';
  const flat = value.replace(/\s+/g, ' ').trim();
  return flat.length > 30 ? `${flat.slice(0, 29)}…` : flat;
}

export function FieldPalette({ destination, placed, onPlace, onAdd, readOnly = false, lineProfile }: FieldPaletteProps) {
  const [query, setQuery] = useState('');

  /**
   * Grouped by binding root, in the order the roots are declared, because that order is
   * roughly the order of a document: who issued it, what it is, who it is for.
   */
  const groups = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const buckets = new Map<string, string[]>();
    for (const path of sampleBindingPaths()) {
      // Searching the value as well as the path is the point of showing it: "Nashik" finds
      // the shipping address without anyone knowing it is called `address.shipping`.
      const haystack = `${path} ${sampleValue(path) ?? ''}`.toLowerCase();
      if (needle && !haystack.includes(needle)) continue;
      const root = path.split('.')[0] ?? 'other';
      const bucket = buckets.get(root);
      if (bucket) bucket.push(path);
      else buckets.set(root, [path]);
    }
    return [...buckets.entries()];
  }, [query]);

  const total = groups.reduce((sum, [, paths]) => sum + paths.length, 0);
  /**
   * One tab stop for the whole field list, with the arrows inside it. Fifty-odd fields as
   * fifty stops would put the canvas fifty presses away from the rail.
   */
  const [focusPath, setFocusPath] = useState<string | null>(null);
  const flat = groups.flatMap(([, paths]) => paths);
  const current = focusPath && flat.includes(focusPath) ? focusPath : (flat[0] ?? null);
  const step = (event: React.KeyboardEvent<HTMLDivElement>) => {
    const keys: Record<string, number> = { ArrowDown: 1, ArrowUp: -1 };
    const at = current ? flat.indexOf(current) : -1;
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? flat.length - 1 : event.key in keys ? at + keys[event.key]! : null;
    if (next === null || next < 0 || next >= flat.length) return;
    event.preventDefault();
    setFocusPath(flat[next]!);
    event.currentTarget.querySelector<HTMLButtonElement>(`[data-palette-field="${CSS.escape(flat[next]!)}"]`)?.focus();
  };

  const disabled = readOnly || !destination;
  return (
    <>
    <div className="janso-editor__group">
      <p className="janso-editor__group-label">Add to the page</p>
      <p className="janso-editor__row-hint" data-testid="palette-help">
        {readOnly
          ? 'A shipped template is read-only — copy it to add to it.'
          : destination
            ? `Drag an object or a field onto the page, or click it to add it into “${destination.label}”. Select another zone to add there.`
            : 'This page has no zones yet. Add one in page structure before placing anything.'}
      </p>
      {onAdd ? (
        <ul className="janso-editor__list" aria-label="Objects">
          {addableFor(lineProfile).map((kind) => (
            <li key={kind}>
              <button
                type="button"
                className="janso-editor__item"
                disabled={disabled}
                draggable={!readOnly}
                onDragStart={(event) => {
                  event.dataTransfer.setData(DRAG_ELEMENT, kind);
                  event.dataTransfer.effectAllowed = 'copy';
                }}
                aria-label={`Add ${ADDABLE_ELEMENTS[kind].label.toLowerCase()}${destination ? ` to ${destination.label}` : ''}`}
                onClick={() => onAdd(kind)}
              >
                <span className="janso-editor__palette-name">{ADDABLE_ELEMENTS[kind].label}</span>
                <span className="janso-editor__item-meta">{ADDABLE_ELEMENTS[kind].hint}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
    <div className="janso-editor__group">
      <p className="janso-editor__group-label">Fields</p>

      <label className="janso-editor__search">
        <span className="janso-editor__row-label">Find a field</span>
        <input
          type="search"
          className="janso-editor__input"
          value={query}
          placeholder="name, gstin, Nashik…"
          onChange={(event) => setQuery(event.target.value)}
        />
      </label>

      <p className="janso-editor__row-hint" data-testid="palette-destination">
        {readOnly
          ? 'A shipped template is read-only — copy it to place fields.'
          : destination
            ? `Places into “${destination.label}”`
            : 'Add a zone to the page to place a field into it.'}
      </p>

      {total === 0 ? (
        <p className="janso-editor__empty">Nothing matches “{query}”.</p>
      ) : (
        /* Bounded and scrolled: fifty-odd fields would otherwise push the version panel
         * below it off the rail entirely. */
        <div className="janso-editor__palette-scroll" onKeyDown={step}>
          {groups.map(([root, paths]) => (
          <div key={root} className="janso-editor__palette-group">
            <p className="janso-editor__palette-root">{root}</p>
            {/* Named, so the rail's lists are navigable: a screen-reader user arriving at
              * "company" needs to know which list they are in. */}
            <ul className="janso-editor__list" aria-label={`${root} fields`}>
              {paths.map((path) => (
                <li key={path}>
                  <button
                    type="button"
                    className="janso-editor__item"
                    disabled={disabled}
                    data-palette-field={path}
                    tabIndex={path === current ? 0 : -1}
                    onFocus={() => setFocusPath(path)}
                    draggable={!readOnly}
                    onDragStart={(event) => {
                      event.dataTransfer.setData(DRAG_FIELD, path);
                      event.dataTransfer.effectAllowed = 'copy';
                    }}
                    aria-label={`Place ${bindingLabel(path)} (${path})`}
                    onClick={() => onPlace(path)}
                  >
                    <span className="janso-editor__palette-name">
                      {bindingLabel(path)}
                      {placed.has(path) ? (
                        <span className="janso-editor__palette-mark" title="Already on the page">
                          on the page
                        </span>
                      ) : null}
                    </span>
                    <span className="janso-editor__item-meta">{preview(path)}</span>
                  </button>
                </li>
              ))}
            </ul>
            </div>
          ))}
        </div>
      )}
    </div>
    </>
  );
}
