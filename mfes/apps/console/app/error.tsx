'use client';

import { Button, Notice } from '@janso/ui';
import { goTo, signInUrl } from './lib/navigate';

export default function ConsoleError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <main className="janso-main">
    <Notice tone="danger" title="Unable to load your books">
      Your session or company access could not be loaded. Try again, or sign in to check your access.
    </Notice>
    <Button onClick={reset}>Try again</Button>
    <Button variant="ghost" onClick={() => goTo(signInUrl())}>Sign in</Button>
  </main>;
}
