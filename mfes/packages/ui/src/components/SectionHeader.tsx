import type { ReactNode } from 'react';

type SectionHeaderProps = {
  /** Brand-coloured overline — the section's kind ("REVENUE"), above its name. */
  overline?: ReactNode;
  icon?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
};

/**
 * A band within a page. The title is an `<h2>` so headings descend from the `PageHeader`'s
 * `<h1>` without a skipped level (design-system §7).
 */
export function SectionHeader({ overline, icon, title, description }: SectionHeaderProps) {
  return (
    <header className="janso-section-header">
      {overline ? <p className="janso-overline janso-overline--brand">{overline}</p> : null}
      <div className="janso-section-header__row">
        {icon ? (
          <span className="janso-section-header__icon" aria-hidden="true">
            {icon}
          </span>
        ) : null}
        <h2 className="janso-section-header__title">{title}</h2>
      </div>
      {description ? <p className="janso-section-header__desc">{description}</p> : null}
    </header>
  );
}
