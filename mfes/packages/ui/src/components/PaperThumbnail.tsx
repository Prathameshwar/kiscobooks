import type { CSSProperties, ReactNode } from 'react';
import { PX_PER_MM } from '../lib/paper';

/**
 * A page, shrunk to fit a box, still drawn to scale.
 *
 * **It renders the real document, not a picture of one.** A gallery of invoice templates is
 * useless if the cards do not look like the invoices — "the one with the logo on the left"
 * is how anyone actually finds a template, and a generic page icon makes four templates
 * indistinguishable. So the caller passes the same document tree the editor draws and this
 * scales it, which also means a thumbnail can never go stale against the layout it depicts.
 *
 * The scale comes from the **longest** edge, so an A4 sheet and an 80mm roll both fit the
 * same box and stay visibly different shapes — a roll that was stretched to fill a square
 * would be a lie about the stock it prints on.
 *
 * Decorative by construction: `aria-hidden`, and no interactive content. The card around it
 * carries the name, the status and the link, because a scaled-down 7pt address line is not
 * information any reader can use — it is a shape that says "invoice".
 */

type PaperThumbnailProps = {
  /** The page's millimetre box, after orientation. */
  page: { readonly widthMm: number; readonly heightMm: number };
  /** The longest edge of the box this must fit inside, in CSS pixels. */
  boxPx: number;
  children: ReactNode;
};

export function PaperThumbnail({ page, boxPx, children }: PaperThumbnailProps) {
  const longestMm = Math.max(page.widthMm, page.heightMm) || 1;
  const scale = boxPx / (longestMm * PX_PER_MM);

  const frame: CSSProperties = {
    width: `${page.widthMm * PX_PER_MM * scale}px`,
    height: `${page.heightMm * PX_PER_MM * scale}px`,
  };

  /*
   * `transform: scale` rather than a smaller font size or a CSS zoom: the document's
   * geometry is in millimetres and must shrink *as a whole*, including the hairlines and
   * the gaps between table rows. Re-deriving it at a smaller scale would be a second
   * renderer, and a thumbnail that disagrees with the canvas is worse than none.
   */
  const sheet: CSSProperties = {
    width: `${page.widthMm}mm`,
    height: `${page.heightMm}mm`,
    transform: `scale(${scale})`,
  };

  return (
    <div className="janso-thumb" style={frame} aria-hidden="true">
      <div className="janso-thumb__sheet" style={sheet}>
        {children}
      </div>
    </div>
  );
}
