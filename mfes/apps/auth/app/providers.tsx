'use client';

import type { ReactNode } from 'react';
import { ThemeProvider } from '@janso/ui';

/**
 * Theme context for the pre-sign-in screens.
 *
 * No `initial`: before sign-in there is no user record, so the cookie and `localStorage` the
 * pre-paint script already read are the only sources — and `ThemeProvider` reads the same two.
 * A preference chosen here therefore survives into the console, where it becomes the durable
 * `user.theme` once identity is wired.
 */
export function Providers({ children }: { children: ReactNode }) {
  return <ThemeProvider>{children}</ThemeProvider>;
}
