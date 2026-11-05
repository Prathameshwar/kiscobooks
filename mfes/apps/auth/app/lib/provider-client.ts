'use client';

import { useEffect, useState } from 'react';
import type { ProviderId } from './provider';

/** Browser side of `provider.ts`: the id NextAuth knows the configured provider by. */
export type { ProviderId };

/**
 * Asks the server which provider this installation uses. Not cached: a failed answer must
 * not stick, and one small request per sign-in click is cheaper than a stale guess. Rejects
 * when the server is unavailable or misconfigured, so a caller's existing "unable to start
 * sign in" path handles it instead of guessing a provider.
 */
export async function authProviderId(): Promise<ProviderId> {
  const response = await fetch('/api/provider', { cache: 'no-store' });
  const value = response.ok ? await response.json() : null;
  if (value?.provider === 'local' || value?.provider === 'authentik') return value.provider;
  throw new Error('Authentication provider unavailable');
}

/** The provider once known; `null` while loading or when the server could not say. */
export function useAuthProvider(): ProviderId | null {
  const [provider, setProvider] = useState<ProviderId | null>(null);
  useEffect(() => {
    let active = true;
    authProviderId().then(value => { if (active) setProvider(value); }).catch(() => undefined);
    return () => { active = false; };
  }, []);
  return provider;
}
