import { MAX_ZOOM, MIN_ZOOM, zoomIn, zoomOut } from '../lib/paper';

type ZoomControlProps = {
  zoom: number;
  onChange: (zoom: number) => void;
  /** Fit the page to the viewport. Absent when the viewport has not been measured yet. */
  onFit?: () => void;
  /** Labels the group for assistive technology; the editor supplies "Canvas zoom". */
  label?: string;
};

/**
 * Stepped zoom, not a slider.
 *
 * A designer checks a layout at specific sizes — 100% to judge type, 50% to see the whole
 * page, 200% to place a 1mm rule — and a slider makes those exact stops the hardest thing
 * to hit. "Fit" is the fourth stop everyone actually wants.
 *
 * The percentage is a live region: zoom also changes by `ctrl`+wheel on the canvas, and a
 * keyboard user needs to hear the new value when they did not press the button.
 */
export function ZoomControl({ zoom, onChange, onFit, label = 'Canvas zoom' }: ZoomControlProps) {
  const percent = Math.round(zoom * 100);

  return (
    <div className="janso-zoom" role="group" aria-label={label}>
      <button
        type="button"
        className="janso-zoom__btn"
        onClick={() => onChange(zoomOut(zoom))}
        disabled={zoom <= MIN_ZOOM}
        aria-label="Zoom out"
      >
        −
      </button>
      <span className="janso-zoom__value" aria-live="polite" aria-atomic="true">
        {percent}%
      </span>
      <button
        type="button"
        className="janso-zoom__btn"
        onClick={() => onChange(zoomIn(zoom))}
        disabled={zoom >= MAX_ZOOM}
        aria-label="Zoom in"
      >
        +
      </button>
      {onFit ? (
        <button type="button" className="janso-zoom__btn" onClick={onFit}>
          Fit
        </button>
      ) : null}
    </div>
  );
}
