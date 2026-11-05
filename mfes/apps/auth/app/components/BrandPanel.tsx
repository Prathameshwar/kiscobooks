import { Wordmark, ReceiptIcon, ScaleIcon, BoxIcon, ShieldIcon } from '@janso/ui';

/**
 * The brand / value panel. What KiscoBooks does, written for the business owner signing in
 * — meaningful before login (unlike a fake account balance), one icon-led row per
 * domain, separated by the account-book rule. Named by the benefit the reader gets,
 * not the machinery behind it.
 *
 * The panel is a sheet of account-book paper: a double margin rule down the left, faint ruled
 * lines across, and the logomark's own two strokes — the rising rule over the flat base that
 * is "the books balance" — drawn very large and cropped by the edge. It is decoration only
 * (`aria-hidden`); every word on the panel is real content.
 */
const FEATURES = [
  {
    Icon: ReceiptIcon,
    title: 'Invoice in seconds',
    body: 'GST-ready bills and quotes, sent from any device.',
  },
  {
    Icon: ScaleIcon,
    title: 'Books that always balance',
    body: 'Every sale, payment and adjustment posts to double-entry accounts for you.',
  },
  {
    Icon: BoxIcon,
    title: 'Stock you can trust',
    body: 'Live quantities across every store and godown, down to the batch.',
  },
];

/**
 * The logomark's two strokes at sheet scale, drawn as outlines — the rising rule over the flat
 * base, each a capsule of the mark's own proportions (a 3.4-unit stroke with round ends) — and its
 * settled point as a ring. `pathLength` is normalised so one dash animation draws every outline.
 */
function BalanceMark() {
  return (
    <svg className="auth__balance" viewBox="0 0 40 40" aria-hidden="true" focusable="false">
      <rect
        className="auth__balance-rise"
        x="7.475"
        y="12.5"
        width="21.55"
        height="3.4"
        rx="1.7"
        transform="rotate(-15.3 18.25 14.2)"
        pathLength={1}
      />
      <rect className="auth__balance-base" x="7.8" y="23.9" width="24.9" height="3.4" rx="1.7" pathLength={1} />
      <circle className="auth__balance-point" cx="30.2" cy="15" r="2.7" pathLength={1} />
    </svg>
  );
}

export function BrandPanel() {
  return (
    <aside className="auth__brand">
      <div className="auth__sheet" aria-hidden="true">
        <BalanceMark />
      </div>

      <div className="auth__brand-head">
        <Wordmark size={40} nameSize="1.375rem" strapline="always balances" />
        <p className="auth__tagline">Billing, accounting and inventory.</p>
      </div>

      <div className="auth__features">
        {FEATURES.map(({ Icon, title, body }) => (
          <div className="auth__feature" key={title}>
            <span className="auth__feature__icon" aria-hidden="true">
              <Icon size={18} />
            </span>
            <div>
              <p className="auth__feature__title">{title}</p>
              <p className="auth__feature__body">{body}</p>
            </div>
          </div>
        ))}
      </div>

      <p className="auth__trust">
        <ShieldIcon size={15} />
        Private to your business — only people you invite can open your workspace.
      </p>
    </aside>
  );
}
