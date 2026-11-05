import type { ReactNode } from 'react';
import { ThemeSwitcher, Wordmark, currentYear } from '@janso/ui';
import { BrandPanel } from './BrandPanel';

/**
 * The split shell shared by every auth screen: the brand / value panel (desktop), a compact
 * wordmark header (mobile), and the paper form column. The form itself is passed in as
 * children, so /login, /signup and /recover stay thin.
 *
 * The form column is a two-row grid — switcher, then the centred form — rather than a
 * centred flex box with the switcher absolutely positioned over it. Overlaying it would
 * collide with the form on a short viewport, where the two rows simply stack.
 */
export function AuthShell({ children, registration = false }: { children: ReactNode; registration?: boolean }) {
  return (
    <div className={`auth${registration ? ' janso-registration' : ''}`}>
      <header className="auth__mobile-brand">
        <Wordmark size={28} nameSize="1.3rem" />
      </header>
      <BrandPanel />
      <main className="auth__panel">
        {/*
          Choosing a palette is useful before signing in, not only after: this is the screen a
          returning user meets first, and the preference persists into the console.
        */}
        <div className="auth__panel-bar">
          <ThemeSwitcher />
        </div>
        <div className="auth__form-wrap">
          <div className="auth__form">{children}</div>
        </div>
      </main>
      {/*
        Legal is a grid child, not part of either column's content: on desktop it sits at
        the foot of the brand panel (which shares its background), keeping the form column
        uncrowded; on mobile — where the brand panel is hidden — it still shows, last.
      */}
      <footer className="auth__legal">
        {/*
          Resolved at render time, never hardcoded. `suppressHydrationWarning` because the
          page is prerendered: the HTML carries the build year, the client re-renders the
          real one, and that difference is intended rather than a bug.
        */}
        <span suppressHydrationWarning>© {currentYear()} Khushiyan Enterprise</span>
        <nav className="auth__legal-links" aria-label="Legal">
          <a href="/terms">Terms</a>
          <a href="/privacy">Privacy</a>
          <a href="/help">Help</a>
        </nav>
      </footer>
    </div>
  );
}
