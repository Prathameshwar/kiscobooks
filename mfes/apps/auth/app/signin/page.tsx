import type { Metadata } from 'next';
import React from 'react';
import { validOpaqueToken } from '../lib/local-auth-shared';
import { safeAuthProvider } from '../lib/provider';
import { SignInForm } from './SignInForm';

export const dynamic = 'force-dynamic';
// The URL carries the authorization request id: keep it out of Referer and out of search indexes.
export const metadata: Metadata = { title: 'Sign in | KiscoBooks', robots: { index: false, follow: false }, referrer: 'no-referrer' };

/**
 * Where the local OIDC provider sends the browser after `authorize` (`…/signin?request=<id>`,
 * docs/local-auth.md §3). Public intentionally: it is the sign-in screen. The request id is
 * validated as an opaque token here and again by the BFF before it goes anywhere.
 */
export default async function SignInPage({ searchParams }: { searchParams?: Promise<{ request?: string | string[] }> }) {
  const query = await searchParams;
  const candidate = query?.request;
  return <SignInForm requestId={validOpaqueToken(candidate) ? candidate : null} available={safeAuthProvider() === 'local'} />;
}
