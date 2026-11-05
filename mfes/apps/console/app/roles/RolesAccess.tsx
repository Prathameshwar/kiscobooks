'use client';
import { AccessDirectory } from '../components/AccessDirectory';
import type { AccessContext } from '../lib/access-directory';

export function RolesAccess({ context, initialQuery = '' }: { context: AccessContext; initialQuery?: string }) {
  return <AccessDirectory resource="roles" context={context} initialQuery={initialQuery} />;
}
