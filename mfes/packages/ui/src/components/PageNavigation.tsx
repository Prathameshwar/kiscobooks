import type { MouseEvent } from 'react';
import { ChevronLeftIcon } from './icons-table';
import { isSafeHref } from '../lib/url';

export type BreadcrumbItem = { label: string; href?: string };
export type PageNavigationProps = {
  back?: { href: string; label: string };
  breadcrumbs?: readonly BreadcrumbItem[];
  /**
   * Called before any destination here is followed. An editor with an unsaved draft confirms
   * the discard from one place: every link in this bar leaves the page, so guarding only the
   * back link would let a breadcrumb drop the draft silently.
   */
  onNavigate?: (event: MouseEvent<HTMLAnchorElement>) => void;
};

/** Explicit destinations work on direct visits as well as in-app navigation. */
export function PageNavigation({ back, breadcrumbs = [], onNavigate }: PageNavigationProps) {
  const canGoBack = back && isSafeHref(back.href);
  if (!canGoBack && !breadcrumbs.length) return null;
  return <div className="janso-page-navigation">
    {canGoBack ? <a className="janso-page-navigation__back" href={back.href} aria-label={`Back to ${back.label}`} onClick={onNavigate}><ChevronLeftIcon /><span>Back</span></a> : null}
    {breadcrumbs.length ? <nav className="janso-breadcrumbs" aria-label="Breadcrumb"><ol>
      {breadcrumbs.map((item, index) => <li key={index}>
        {index < breadcrumbs.length - 1 && item.href && isSafeHref(item.href)
          ? <a href={item.href} onClick={onNavigate}>{item.label}</a>
          : <span aria-current={index === breadcrumbs.length - 1 ? 'page' : undefined}>{item.label}</span>}
      </li>)}
    </ol></nav> : null}
  </div>;
}
