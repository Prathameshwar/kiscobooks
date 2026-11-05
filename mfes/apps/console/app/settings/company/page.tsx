import { ErrorState } from '@janso/ui';
import { Providers } from '../../providers';
import { ConsoleShell } from '../../components/ConsoleShell';
import { CompanyConfiguration } from '../../components/CompanyConfiguration';
import { NoCompany } from '../../components/NoCompany';
import { pageContext } from '../../lib/page-context';
import { companyPermission } from '../../lib/company-permissions';

export default async function CurrentCompanyConfigurationPage() {
  const { session, context } = await pageContext(), companyId = session.company.id;
  return <Providers session={session}><ConsoleShell session={session} context={context} activeHref="/settings">
    {!companyId ? <NoCompany action="configure" context={context} canCreate={companyPermission(session, 'company.create')} /> : companyPermission(session, 'company.read', companyId) ? <CompanyConfiguration key={companyId} session={session} companyId={companyId} returnTo="/settings" /> : <ErrorState status={403} detail="Company read access is required for this company." />}
  </ConsoleShell></Providers>;
}
