import type { Metadata, Viewport } from 'next';
import { themeScript } from '@janso/ui';
import { Providers } from './providers';

// Order matters: non-colour tokens, then every palette, then the components that consume them.
import '@janso/ui/styles/fonts.css';
import '@janso/ui/styles/tokens.css';
import '@janso/ui/styles/theme-light.css';
import '@janso/ui/styles/theme-dark.css';
import '@janso/ui/styles/theme-ledger.css';
import '@janso/ui/styles/janso-ui.css';
import '@janso/ui/styles/theme.css';
import '@janso/ui/styles/data.css';
import '@janso/ui/styles/setup.css';
import '@janso/ui/styles/search-select.css';
import '@janso/ui/styles/file-upload.css';
/* `Menu` and `ConfirmDialog` — sign-out confirmation and the account menu on the auth screens. */
import '@janso/ui/styles/overlay.css';
import './auth.css';
import '@janso/ui/styles/registration.css';
import './globals.css';

export const metadata: Metadata = {
  title: 'Sign in · KiscoBooks',
  description: 'KiscoBooks — billing, accounting and inventory that always balances.',
  icons: { icon: '/favicon.svg' },
};

export const viewport: Viewport = {
  themeColor: [
    { media: '(prefers-color-scheme: light)', color: '#f7f8fb' },
    { media: '(prefers-color-scheme: dark)', color: '#0e1117' },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // `suppressHydrationWarning`: the pre-paint script sets `data-theme` and `color-scheme`
    // on this element before React hydrates, so server markup and live DOM differ on exactly
    // those two attributes, by design.
    <html lang="en" suppressHydrationWarning>
      <head>
        {/*
         * The same pre-paint script the console uses. A returning user who chose Dark must not
         * be shown a white flash on the way back in, and the cookie and localStorage are
         * readable without a session — which is also what lets the switcher on this screen
         * work before there is a user record to write a preference to.
         */}
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className="janso-root">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
