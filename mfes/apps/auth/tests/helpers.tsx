import type { ReactElement } from 'react';
import { render } from '@testing-library/react';
import { Providers } from '../app/providers';

/**
 * Renders a screen inside the **real** `Providers` the root layout mounts, rather than a
 * hand-built copy of it: a stand-in tree would keep passing if the app stopped wrapping its
 * pages, which is the one thing this is here to catch.
 *
 * No theme is pinned, because `Providers` deliberately takes no `initial` — before sign-in
 * there is no user record, so the cookie and `localStorage` decide. The setup file clears both
 * between tests, so this resolves to `light` deterministically.
 */
export function renderScreen(ui: ReactElement) {
  return render(<Providers>{ui}</Providers>);
}
