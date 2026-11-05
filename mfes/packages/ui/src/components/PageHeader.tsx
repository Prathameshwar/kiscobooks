import type { ReactNode } from 'react';

type PageHeaderProps = {
  /** Letterspaced uppercase label above the title — where you are, not what this is. */
  overline?: ReactNode;
  title: ReactNode;
  lede?: ReactNode;
  /**
   * Chips that describe the thing this page is about — its status, its type, its currency — in a
   * wrapping strip under the lede. Facts about the record, not things to do: those are `actions`.
   */
  meta?: ReactNode;
  /** Primary/secondary actions for the whole page, right-aligned on the title's band. */
  actions?: ReactNode;
};

/**
 * The top of every page. It owns the page's single `<h1>` (design-system §7), which is why
 * no other primitive here renders one — a screen with two `h1`s has no outline.
 */
export function PageHeader({ overline, title, lede, meta, actions }: PageHeaderProps) {
  return (
    <header className="janso-page-header">
      <div className="janso-page-header__text">
        {overline ? <p className="janso-overline">{overline}</p> : null}
        <h1 className="janso-h1">{title}</h1>
        {lede ? <p className="janso-lede">{lede}</p> : null}
        {meta ? <div className="janso-page-header__meta">{meta}</div> : null}
      </div>
      {actions ? <div className="janso-page-header__actions">{actions}</div> : null}
    </header>
  );
}
