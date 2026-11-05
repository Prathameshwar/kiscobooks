import type { Metadata } from 'next';
import React from 'react';
import { validOpaqueToken } from '../lib/local-auth-shared';
import { safeAuthProvider } from '../lib/provider';
import { ResetForm } from './ResetForm';

export const dynamic = 'force-dynamic';
// The URL carries a one-time recovery token: never in Referer, never indexed.
export const metadata: Metadata = { title: 'Reset password | KiscoBooks', robots: { index: false, follow: false }, referrer: 'no-referrer' };

/**
 * Landing page for an operator-issued recovery link (`/reset?token=…`, docs/local-auth.md §4).
 * Public intentionally: the unguessable single-use token is the credential. The token is checked
 * for shape here and verified by Identity (via the BFF) before any password is asked for.
 */
export default async function ResetPage({ searchParams }: { searchParams?: Promise<{ token?: string | string[] }> }) {
  const query = await searchParams;
  const candidate = query?.token;
  return <ResetForm token={validOpaqueToken(candidate) ? candidate : null} available={safeAuthProvider() === 'local'} />;
}
