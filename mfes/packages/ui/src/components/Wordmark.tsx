import { JansoMark } from './JansoMark';

/**
 * Product lockup: the ledger mark + the name as live text (selectable, translatable,
 * crisp at any size — which a rasterised wordmark is not), with an optional strapline
 * beneath the name. The two name parts use semantic theme inks for contrast on
 * the brand panel and paper, without separating the product name.
 */
export function Wordmark({
  size = 40,
  nameSize = '1.55rem',
  showName = true,
  strapline,
  className = '',
}: {
  size?: number;
  nameSize?: string;
  showName?: boolean;
  strapline?: string;
  className?: string;
}) {
  return (
    <span className={`janso-wordmark ${className}`.trim()}>
      <JansoMark size={size} />
      {showName ? (
        <span className="janso-wordmark__text">
          <span className="janso-wordmark__name" style={{ fontSize: nameSize }}>
            <span className="janso-wordmark__first">Kisco</span><span className="janso-wordmark__last">Books</span>
          </span>
          {strapline ? <span className="janso-wordmark__strap">{strapline}</span> : null}
        </span>
      ) : null}
    </span>
  );
}
