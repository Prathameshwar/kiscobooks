'use client';

import type { ReactNode } from 'react';
import { DisplayConfigProvider, PermissionProvider, ThemeProvider } from '@janso/ui';
import type { Session } from './session';
import { ProductModeProvider } from './components/ProductModeProvider';
import { CompanyAccessProvider } from './lib/company-access';

/**
 * The three pieces of ambient context every console screen needs.
 *
 * The session arrives as a **prop**, resolved per request by the Server Component that renders
 * this. It is never imported from module scope: one shared session object per server process
 * is how one tenant's context reaches another tenant's request (see `session.ts`).
 *
 * `PermissionProvider` is presentation only — it decides what to *render*, never what is
 * *allowed*. The server remains the enforcement point for every one of these keys
 * (CLAUDE.md §5.2, §6.15).
 */
export function Providers({ session, children }: { session: Session; children: ReactNode }) {
  return (
    <ThemeProvider
      // `null` means the user has no stored preference, so the cookie / localStorage the
      // pre-paint script already read decides — passing `undefined` is what asks for that.
      initial={session.user.theme ?? undefined}
      onChange={(preference) => {
        // Where the PATCH to the user record will go once identity is wired. Until then the
        // preference still survives a reload via the cookie and localStorage, so the
        // no-flash path is already exercised end to end.
        void preference;
      }}
    >
      <DisplayConfigProvider key={JSON.stringify([session.organisation.id, session.user.id, session.company.id, session.permissions, session.grants, session.display])} config={session.display}>
        <CompanyAccessProvider grants={session.grants}>
          <PermissionProvider permissions={session.permissions}>
            <ProductModeProvider key={session.organisation.id + ':' + session.company.id + ':' + session.user.id} session={session}>{children}</ProductModeProvider>
          </PermissionProvider>
        </CompanyAccessProvider>
      </DisplayConfigProvider>
    </ThemeProvider>
  );
}
