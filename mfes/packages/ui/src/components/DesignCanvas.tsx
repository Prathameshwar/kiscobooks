'use client';

import { type CSSProperties, type DragEvent as ReactDragEvent, type ReactNode, type PointerEvent as ReactPointerEvent, useRef } from 'react';
import { CanvasRuler } from './CanvasRuler';
import {
  DEFAULT_MARGINS,
  type Margins,
  type PaperSpec,
  pageGeometry,
  printableArea,
  toMm,
} from '../lib/paper';

export type CanvasCursor = { readonly xMm: number; readonly yMm: number };

type DesignCanvasProps = {
  paper: PaperSpec;
  margins?: Margins;
  zoom?: number;
  /** Show the millimetre rulers. Off for a thumbnail or a read-only preview. */
  rulers?: boolean;
  /** The layout grid drawn on the paper, in millimetres. `0` hides it. */
  gridStepMm?: number;
  /** Reported in paper millimetres, and `null` once the pointer leaves the page. */
  onCursorChange?: (cursor: CanvasCursor | null) => void;
  /** A chip above the page: the paper label, the copy being previewed. */
  chip?: ReactNode;
  /** Absolutely positioned document content, in millimetres. */
  children?: ReactNode;
  /** Names the page for assistive technology — "Tax invoice template, A4 portrait". */
  label: string;
  /**
   * How much of the page to *draw*, when that is not its nominal length.
   *
   * For continuous stock only. A roll has no page: `PAPER_SIZES` gives an 80mm roll a
   * nominal 200mm because a canvas has to be some size, and a receipt is however long its
   * content is. Drawing 200mm and letting the rest hang onto the backdrop reads as a
   * broken editor rather than as a long receipt. The declared paper is unchanged — this
   * says how much of it is in front of you.
   */
  drawnHeightMm?: number;
  /**
   * The drag types the page accepts — a palette's own MIME types. Without them nothing can be
   * dropped, so a stray file or link dragged over the editor is never taken for content.
   */
  dropTypes?: readonly string[];
  /** Something accepted was let go over the page, at this point in paper millimetres. */
  onDrop?: (point: CanvasCursor, data: DataTransfer) => void;
};

/**
 * The paper, the air around it, and the instruments along its edges.
 *
 * Three decisions worth knowing before changing this:
 *
 * **Millimetres, not pixels.** The page box and every child are declared in CSS `mm`, and
 * zoom is one `transform: scale()` on the page wrapper. Children therefore never learn
 * about zoom — an element at `12mm` is at 12mm at 25% and at 200% — and what you see is
 * what the print engine will lay out. The alternative, converting every coordinate to
 * pixels at the current zoom, puts a rounding error in the middle of a WYSIWYG promise.
 *
 * **The scroller is the only scroll container**, so the rulers can stay pinned while the
 * page moves under them.
 *
 * **Cursor position is reported, not drawn.** The canvas reports millimetres and the
 * editor shows them in its status bar, where a screen reader can read them; the ruler
 * markers are decoration over the same number.
 */
export function DesignCanvas({
  paper,
  margins = DEFAULT_MARGINS,
  zoom = 1,
  rulers = true,
  gridStepMm = 5,
  onCursorChange,
  chip,
  children,
  label,
  drawnHeightMm,
  dropTypes,
  onDrop,
}: DesignCanvasProps) {
  const spec = pageGeometry(paper);
  const page = drawnHeightMm ? { ...spec, heightMm: drawnHeightMm } : spec;
  const printable = printableArea(page, margins);
  const paperRef = useRef<HTMLDivElement | null>(null);

  const pointOf = (event: { clientX: number; clientY: number }): CanvasCursor | null => {
    const box = paperRef.current?.getBoundingClientRect();
    if (!box) return null;
    const xMm = toMm(event.clientX - box.left, zoom);
    const yMm = toMm(event.clientY - box.top, zoom);
    return xMm >= 0 && yMm >= 0 && xMm <= page.widthMm && yMm <= page.heightMm ? { xMm, yMm } : null;
  };
  const report = (event: ReactPointerEvent<HTMLDivElement>) => onCursorChange?.(pointOf(event));
  const accepts = (event: ReactDragEvent<HTMLDivElement>) =>
    !!onDrop && !!dropTypes?.some((type) => event.dataTransfer.types.includes(type));
  const dragOver = (event: ReactDragEvent<HTMLDivElement>) => {
    if (!accepts(event)) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = 'copy';
    onCursorChange?.(pointOf(event));
  };
  const drop = (event: ReactDragEvent<HTMLDivElement>) => {
    if (!accepts(event)) return;
    event.preventDefault();
    const point = pointOf(event);
    if (point) onDrop!(point, event.dataTransfer);
  };

  // `--janso-zoom` rather than a style on each child: the chip reads it to cancel the
  // scale, so the factor has to be available down the tree, not just applied once.
  const pageStyle = { '--janso-zoom': zoom } as CSSProperties;

  return (
    <div className={`janso-canvas${rulers ? '' : ' janso-canvas--plain'}`}>
      {rulers ? (
        <>
          <div className="janso-canvas__corner" aria-hidden="true" />
          <CanvasRuler axis="horizontal" lengthMm={page.widthMm} zoom={zoom} />
          <CanvasRuler axis="vertical" lengthMm={page.heightMm} zoom={zoom} />
        </>
      ) : null}

      <div className="janso-canvas__scroll">
        <div className="janso-canvas__page" style={pageStyle}>
          {chip ? <span className="janso-canvas__chip">{chip}</span> : null}
          <div
            ref={paperRef}
            className="janso-canvas__paper"
            style={{ width: `${page.widthMm}mm`, height: `${page.heightMm}mm` }}
            onPointerMove={report}
            onPointerLeave={() => onCursorChange?.(null)}
            onDragOver={dragOver}
            onDrop={drop}
            /*
             * `group` with a name: this is a canvas, not an image and not a document
             * region. The accessible name says which template and what paper, because
             * that is what a user needs to know before they start moving things on it.
             */
            role="group"
            aria-label={label}
            data-testid="design-canvas-paper"
          >
            {gridStepMm > 0 ? (
              <div
                className="janso-canvas__grid"
                style={{ backgroundSize: `${gridStepMm}mm ${gridStepMm}mm` }}
                data-testid="design-canvas-grid"
              />
            ) : null}

            <div
              className="janso-canvas__margins"
              style={{
                left: `${printable.xMm}mm`,
                top: `${printable.yMm}mm`,
                width: `${printable.widthMm}mm`,
                height: `${printable.heightMm}mm`,
              }}
              data-testid="design-canvas-margins"
            />

            <div className="janso-canvas__content">{children}</div>
          </div>
        </div>
      </div>
    </div>
  );
}
