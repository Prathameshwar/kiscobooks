import { rulerTicks } from '../lib/paper';

type CanvasRulerProps = {
  /** Which edge this ruler runs along. */
  axis: 'horizontal' | 'vertical';
  /** The page's length on this axis, in millimetres. */
  lengthMm: number;
  zoom: number;
  /**
   * Where the pointer is on this axis, in paper millimetres, or `null` when it is off the
   * page. A marker that stays behind after the pointer leaves is worse than no marker.
   */
  cursorMm?: number | null;
  /** Distance from the scroller's edge to the page, so ticks line up with the paper. */
  offsetPx?: number;
  /** Millimetres between ticks; a numeral lands every second tick. */
  stepMm?: number;
};

/**
 * A millimetre ruler for the design canvas.
 *
 * Millimetres rather than pixels because that is the unit the layout is stored in and the
 * unit a printer works in — a designer placing a logo 12mm from the edge is describing
 * something physical, and a ruler in CSS pixels would make them convert in their head.
 *
 * Presentational: the numerals are for the eye, so the whole band is `aria-hidden` and the
 * position it reports also appears as text in the editor's status bar, which is what a
 * screen-reader user reads.
 */
export function CanvasRuler({
  axis,
  lengthMm,
  zoom,
  cursorMm = null,
  offsetPx = 0,
  stepMm = 5,
}: CanvasRulerProps) {
  const horizontal = axis === 'horizontal';
  const ticks = rulerTicks(lengthMm, stepMm);
  // One multiplication per tick, so the band and the paper cannot disagree about scale.
  const scale = (mm: number) => `${mm}mm`;

  return (
    <div
      className={`janso-canvas__ruler janso-canvas__ruler--${horizontal ? 'h' : 'v'}`}
      aria-hidden="true"
    >
      <div
        className="janso-canvas__ruler-band"
        style={{
          [horizontal ? 'width' : 'height']: scale(lengthMm),
          [horizontal ? 'marginLeft' : 'marginTop']: `${offsetPx}px`,
          transform: `scale${horizontal ? 'X' : 'Y'}(${zoom})`,
          transformOrigin: horizontal ? 'left' : 'top',
        }}
      >
        {ticks.map(({ mm, major }) => (
          <span
            key={mm}
            className={`janso-canvas__tick${major ? ' janso-canvas__tick--major' : ''}`}
            style={{ [horizontal ? 'left' : 'top']: scale(mm) }}
          />
        ))}
      </div>
      {/* Numerals sit outside the scaled band: at 25% zoom a scaled 11px numeral is
       * unreadable, and at 200% it is comically large. Their *position* follows the zoom;
       * their size does not. */}
      {ticks
        .filter(({ major }) => major)
        .map(({ mm }) => (
          <span
            key={`n${mm}`}
            className="janso-canvas__numeral"
            style={{
              [horizontal ? 'left' : 'top']: `${offsetPx + mm * zoom * (96 / 25.4)}px`,
            }}
          >
            {mm}
          </span>
        ))}
      {cursorMm === null ? null : (
        <span
          className="janso-canvas__marker"
          data-testid={`ruler-marker-${axis}`}
          style={{
            [horizontal ? 'left' : 'top']: `${offsetPx + cursorMm * zoom * (96 / 25.4)}px`,
          }}
        />
      )}
    </div>
  );
}
