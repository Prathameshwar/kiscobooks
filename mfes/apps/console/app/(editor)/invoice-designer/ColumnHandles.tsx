'use client';

import { type PointerEvent as ReactPointerEvent, useRef, useState } from 'react';
import { PX_PER_MM, formatMm } from '@janso/ui';
import { COLUMN_LABELS, type CanvasElement, type ColumnKey } from './layout-model';
import type { Target } from './selection';

/**
 * Column dividers, draggable on the table itself.
 *
 * The inspector can already set a width to the tenth of a millimetre; this is for the
 * other way of working — seeing that "Description" is too narrow for the longest line and
 * pulling its edge until it is not. Both exist because they answer different questions:
 * one is "make it 52mm", the other is "make it fit that text".
 *
 * **Pointer capture, not mouse-move-on-window.** `setPointerCapture` keeps the drag with
 * this divider even when the pointer outruns it — which it will, because the pointer moves
 * in screen pixels and the divider moves in scaled millimetres.
 *
 * **Deltas are converted once.** Screen pixels divided by `PX_PER_MM × zoom` gives paper
 * millimetres, so a drag at 50% zoom moves the same paper distance as at 200%.
 *
 * Keyboard users are served by the inspector's measure field, which is why these carry no
 * tab stop: eight focusable dividers that each need an arrow-key protocol would duplicate
 * a control that already exists and reads better.
 */

type ColumnHandlesProps = {
  /** The selected item-table element and its absolute page rectangle. */
  target: Target;
  element: CanvasElement;
  zoom: number;
  /** Called with the boundary's new width; the shell trades it against the next column. */
  onResize: (elementId: string, key: ColumnKey, widthMm: number) => void;
};

export function ColumnHandles({ target, element, zoom, onResize }: ColumnHandlesProps) {
  const shown = (element.columns ?? []).filter((column) => column.show);
  const dragging = useRef<{ key: ColumnKey; startX: number; startWidth: number } | null>(null);
  const [live, setLive] = useState<{ key: ColumnKey; widthMm: number } | null>(null);

  if (shown.length === 0) return null;

  function onPointerDown(event: ReactPointerEvent<HTMLSpanElement>, key: ColumnKey, widthMm: number) {
    event.preventDefault();
    event.stopPropagation();
    event.currentTarget.setPointerCapture(event.pointerId);
    dragging.current = { key, startX: event.clientX, startWidth: widthMm };
    setLive({ key, widthMm });
  }

  function onPointerMove(event: ReactPointerEvent<HTMLSpanElement>) {
    const drag = dragging.current;
    if (!drag) return;
    const deltaMm = (event.clientX - drag.startX) / (PX_PER_MM * zoom);
    const widthMm = Math.max(1, Math.round((drag.startWidth + deltaMm) * 10) / 10);
    setLive({ key: drag.key, widthMm });
    onResize(element.id, drag.key, widthMm);
  }

  function onPointerUp(event: ReactPointerEvent<HTMLSpanElement>) {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    dragging.current = null;
    setLive(null);
  }

  let offsetMm = 0;
  return (
    <div
      className="janso-canvas__columns"
      style={{
        left: `${target.rect.xMm}mm`,
        top: `${target.rect.yMm}mm`,
        width: `${target.rect.widthMm}mm`,
        height: `${target.rect.heightMm}mm`,
      }}
      data-testid="column-handles"
      /*
       * A pointer affordance, and only that: every width here is also a labelled field in
       * the inspector, so the layer is hidden rather than presenting eleven nameless
       * elements that cannot be operated without a pointer anyway.
       */
      aria-hidden="true"
    >
      {shown.map((column) => {
        offsetMm += column.widthMm;
        const name = column.label ?? COLUMN_LABELS[column.key];
        const isLive = live?.key === column.key;
        return (
          <span
            key={column.key}
            className="janso-canvas__column-grip"
            style={{ left: `${offsetMm}mm` }}
            data-column={column.key}
            data-dragging={isLive || undefined}
            title={`${name} — drag to resize`}
            onPointerDown={(event) => onPointerDown(event, column.key, column.widthMm)}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerCancel={onPointerUp}
          >
            {isLive ? (
              <span className="janso-canvas__badge" data-testid="column-width-readout">
                {name} {formatMm(live.widthMm)} mm
              </span>
            ) : null}
          </span>
        );
      })}
    </div>
  );
}
