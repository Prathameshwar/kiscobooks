import type { ReactNode } from 'react';
import type { Tone } from './Badge';

type CardProps = {
  children: ReactNode;
  /** Tints the whole card with a signal triplet — for a card that *is* a warning. */
  tone?: Tone;
  /** A card sitting inside another card: `--janso-surface-2`, so the nesting reads. */
  nested?: boolean;
  className?: string;
};

/** White surface, 6px ledger radius, one hairline, almost no shadow (design-system §3.1). */
export function Card({ children, tone, nested = false, className = '' }: CardProps) {
  const classes = ['janso-card', nested ? 'janso-card--nested' : '', className]
    .filter(Boolean)
    .join(' ');

  return (
    <div className={classes} data-tone={tone}>
      {children}
    </div>
  );
}

type CardHeaderProps = {
  icon?: ReactNode;
  title: ReactNode;
  subtitle?: ReactNode;
  /** A count or status pill, on the title's baseline. */
  badge?: ReactNode;
  /** An interactive affordance — a link, an `IconButton`, a `Select`. */
  action?: ReactNode;
};

/**
 * The title is an `<h3>`: a card sits inside a `SectionHeader`'s `<h2>`, which sits under the
 * page's `<h1>`, so the outline descends without a skipped level (design-system §7).
 */
export function CardHeader({ icon, title, subtitle, badge, action }: CardHeaderProps) {
  return (
    <div className="janso-card__header">
      <div className="janso-card__heading">
        {icon ? (
          <span className="janso-card__icon" aria-hidden="true">
            {icon}
          </span>
        ) : null}
        <div className="janso-card__titles">
          <h3 className="janso-card__title">{title}</h3>
          {subtitle ? <p className="janso-card__subtitle">{subtitle}</p> : null}
        </div>
      </div>
      {badge || action ? (
        <div className="janso-card__aside">
          {badge}
          {action}
        </div>
      ) : null}
    </div>
  );
}

export function CardBody({ children }: { children: ReactNode }) {
  return <div className="janso-card__body">{children}</div>;
}

export function CardFooter({ children }: { children: ReactNode }) {
  return <div className="janso-card__footer">{children}</div>;
}
