import type { Metadata } from 'next';
import React from 'react';
import { passwordRecoveryDestination, recoverySignInHref } from '../lib/password-recovery';
import { safeAuthProvider } from '../lib/provider';
import { PasswordRecovery } from './PasswordRecovery';

export const dynamic = 'force-dynamic';
export const metadata: Metadata = { title: 'Forgot password | KiscoBooks', robots: { index: false, follow: false }, referrer: 'no-referrer' };

export default async function RecoveryPage({ searchParams }: {
  searchParams?: Promise<{ returnTo?: string | string[]; callbackUrl?: string | string[] }>;
}) {
  const query = await searchParams;
  const candidate = query?.returnTo ?? query?.callbackUrl;
  const signInHref = recoverySignInHref(typeof candidate === 'string' ? candidate : undefined);
  // The local provider has no provider-hosted recovery flow: no Authentik destination, and
  // administrator-issued links are the only route (docs/local-auth.md §1).
  if (safeAuthProvider() === 'local') return <PasswordRecovery destination={null} signInHref={signInHref} local />;
  return <PasswordRecovery destination={passwordRecoveryDestination()} signInHref={signInHref} />;
}
