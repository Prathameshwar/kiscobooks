import type { ReactNode } from 'react';
import { ErrorState } from '@janso/ui';
import { Providers } from '../providers';
import { pageContext } from '../lib/page-context';
import { companyPermission } from '../lib/company-permissions';
import { ConsoleShell } from './ConsoleShell';
import { NoCompany } from './NoCompany';

export async function OperateFrame({ href, children }: { href: string; children: (company: string, permissions: string[]) => ReactNode }) {
  const { session, context } = await pageContext();
  const company = session.company.id;
  const permissions = company ? session.permissions.filter(key => companyPermission(session, key, company)) : [];
  return <Providers session={session}><ConsoleShell session={session} context={context} activeHref={href}>
    {!company ? <NoCompany action="browse vouchers for" context={context} canCreate={companyPermission(session, 'company.create')} />
      : !permissions.includes('vouchers.read') ? <ErrorState status={403} detail="Voucher read access is required for this company." />
        : children(company, permissions)}
  </ConsoleShell></Providers>;
}
