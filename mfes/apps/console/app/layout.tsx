import type { Metadata, Viewport } from 'next';
import { themeScript } from '@janso/ui';

// Order matters: non-colour tokens, then every palette, then the components that consume
// them. All three palettes ship in every build — switching themes must not need a reload,
// so it cannot need a different stylesheet.
import '@janso/ui/styles/fonts.css';
import '@janso/ui/styles/tokens.css';
import '@janso/ui/styles/theme-light.css';
import '@janso/ui/styles/theme-dark.css';
import '@janso/ui/styles/theme-ledger.css';
import '@janso/ui/styles/janso-ui.css';
import '@janso/ui/styles/controls.css';
import '@janso/ui/styles/theme.css';
import '@janso/ui/styles/shell.css';
import '@janso/ui/styles/data.css';
import '@janso/ui/styles/search-select.css';
import '@janso/ui/styles/file-upload.css';
import '@janso/ui/styles/chart.css';
import '@janso/ui/styles/overlay.css';
import '@janso/ui/styles/table.css';
import '@janso/ui/styles/day-book.css';
import '@janso/ui/styles/gst-reports.css';
import '@janso/ui/styles/trial-balance.css';
import '@janso/ui/styles/profit-loss.css';
import '@janso/ui/styles/master-opening.css';
import '@janso/ui/styles/product-wizard.css';
import '@janso/ui/styles/setup.css';
import './globals.css';
import './console.css';

// Every console page resolves a request-scoped authenticated session.
export const dynamic = 'force-dynamic';

export const metadata: Metadata = {
  title: 'Business overview · KiscoBooks',
  description: 'KiscoBooks — billing, accounting and inventory that always balances.',
  icons: { icon: '/favicon.svg' },
};

export const viewport: Viewport = {
  // Both entries so the browser chrome follows the resolved palette rather than guessing.
  themeColor: [
    { media: '(prefers-color-scheme: light)', color: '#f7f8fb' },
    { media: '(prefers-color-scheme: dark)', color: '#0e1117' },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // `suppressHydrationWarning`: the pre-paint script below sets `data-theme` and
    // `color-scheme` on this element before React hydrates, so the server-rendered
    // markup and the live DOM legitimately differ on exactly those two attributes.
    <html lang="en" suppressHydrationWarning>
      <head>
        {/*
         * Runs synchronously before first paint, so the correct palette is in place on the
         * very first frame. Without it, a dark-theme user sees a white flash on every
         * navigation — and the fix cannot live in React, which by definition runs later.
         */}
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      {/*
       * No `Providers` here: they need the request-scoped session, and the layout would have
       * to resolve it a second time to hand it over. Each page resolves the session once, in
       * its Server Component, and mounts `Providers` with it (see `session.ts`).
       */}
      <body className="janso-root">{children}</body>
    </html>
  );
}
