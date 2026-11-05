import { Providers } from '../../providers';
import { ConsoleShell } from '../../components/ConsoleShell';
import { NoCompany } from '../../components/NoCompany';
import { ProductFields } from '../../components/ProductFields';
import { pageContext } from '../../lib/page-context';
import { companyPermission } from '../../lib/company-permissions';
import { ErrorState } from '@janso/ui';

export default async function ProductCustomFieldsPage({ searchParams }: { searchParams?: Promise<{ returnTo?: string | string[] }> }) {
  const query = await searchParams;
  const { session, context } = await pageContext();
  const company = session.company.id;
  return <Providers session={session}><ConsoleShell session={session} context={context} activeHref="/products/custom-fields">
    {company
      ? companyPermission(session, 'item.read', company) ? <ProductFields key={company} returnTo={typeof query?.returnTo === 'string' ? query.returnTo : undefined} company={company} currencies={session.display.currency ? [session.display.currency] : []} canManage={companyPermission(session, 'custom_field.manage', company)} /> : <ErrorState status={403} />
      : <NoCompany action="configure" context={context} canCreate={companyPermission(session, 'company.create')} />}
  </ConsoleShell></Providers>;
}
