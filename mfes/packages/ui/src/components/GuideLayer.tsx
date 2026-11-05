import type { Guide } from '../lib/transform';

type GuideLayerProps = {
  guides: readonly Guide[];
};

/**
 * The alignment guides, while a drag is in progress.
 *
 * Drawn only during the gesture and never left behind: a page permanently criss-crossed
 * with lines is a worse page than one with no guides at all. Purely decorative — the
 * snapped position is reported as text in the status bar and in the inspector, which is
 * what a screen-reader user reads.
 *
 * A centre line and an edge line are styled apart because they say different things:
 * "these two line up" and "this is the middle of that".
 */
export function GuideLayer({ guides }: GuideLayerProps) {
  if (guides.length === 0) return null;

  return (
    <div className="janso-canvas__guides" aria-hidden="true" data-testid="guide-layer">
      {guides.map((guide) => (
        <span
          key={`${guide.axis}-${guide.atMm}-${guide.kind}`}
          className="janso-canvas__guide"
          data-axis={guide.axis}
          data-kind={guide.kind}
          style={guide.axis === 'x' ? { left: `${guide.atMm}mm` } : { top: `${guide.atMm}mm` }}
        />
      ))}
    </div>
  );
}
