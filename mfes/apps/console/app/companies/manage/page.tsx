import { ErrorState } from '@janso/ui';
import { ConsoleShell } from '../../components/ConsoleShell';
import { CompanyDirectory } from '../../components/CompanyDirectory';
import { Providers } from '../../providers';
import { pageContext } from '../../lib/page-context';
import { companyPermission } from '../../lib/company-permissions';

export default async function ManageCompaniesPage({ searchParams = Promise.resolve({}) }: { searchParams?: Promise<Record<string, string | string[] | undefined>> }) {
  const { session, context } = await pageContext();
  const search = await searchParams;
  const query = new URLSearchParams(Object.entries(search).flatMap(([key, value]) => typeof value === 'string' ? [[key, value]] : [])).toString();
  return <Providers session={session}><ConsoleShell session={session} context={context} activeHref="/companies/manage">
    {companyPermission(session, 'company.read') || companyPermission(session, 'company.create')
      ? <CompanyDirectory session={session} initialQuery={query} /> : <ErrorState status={403} detail="Company management needs company.read or tenant-level company.create." />}
  </ConsoleShell></Providers>;
}
