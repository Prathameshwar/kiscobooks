'use client';
import { useMemo } from 'react';
import { MasterImport } from './MasterImport';
import { partyImportProfile } from '../lib/master-import-profiles';

export function PartyImport({
  supplier = false,
  ...props
}: {
  company: string;
  canManage: boolean;
  supplier?: boolean;
  returnTo?: string;
  initialJob?: string;
  initialHistory?: boolean;
}) {
  const profile = useMemo(() => partyImportProfile(supplier), [supplier]);
  return <MasterImport {...props} profile={profile} />;
}
