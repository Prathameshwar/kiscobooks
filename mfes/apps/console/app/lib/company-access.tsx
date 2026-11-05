'use client';

import { createContext, useContext, type ReactNode } from 'react';
import type { Session } from '../session';
import { companyPermission } from './company-permissions';

// Object-level presentation uses the record's company, which may differ from the open one.
const CompanyGrants = createContext<Session['grants']>([]);
export function CompanyAccessProvider({ grants, children }: { grants: Session['grants']; children: ReactNode }) {
  return <CompanyGrants.Provider value={grants}>{children}</CompanyGrants.Provider>;
}
export function useCompanyPermission(permission: string, company: string): boolean {
  const grants = useContext(CompanyGrants);
  return !!company && companyPermission({ grants }, permission, company);
}
