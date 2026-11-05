import type { ReactNode } from 'react';

export type AppFooterLink = { label: string; href: string; icon?: ReactNode };

/**
 * The page's foot: icon links left, copyright right. It sits inside the scrolling content
 * region. AppShell fills any unused space above it on short pages; on long pages it follows
 * the content and is reached by scrolling.
 *
 * **Render it as a sibling of `<main>`, not inside it** — `AppShell`'s `footer` slot does
 * exactly that. A `<footer>` descended from `main` maps to `generic` rather than to the
 * `contentinfo` landmark, so nesting it silently removes the landmark (design-system §7).
 */
export function AppFooter({
  links,
  copyright,
}: {
  links: AppFooterLink[];
  copyright: string;
}) {
  return (
    <footer className="janso-app-footer">
      <ul className="janso-app-footer__links">
        {links.map((link) => (
          <li key={link.href}>
            <a className="janso-app-footer__link" href={link.href}>
              {link.icon ? (
                <span className="janso-app-footer__icon" aria-hidden="true">
                  {link.icon}
                </span>
              ) : null}
              <span>{link.label}</span>
            </a>
          </li>
        ))}
      </ul>
      <p className="janso-app-footer__copy">{copyright}</p>
    </footer>
  );
}
