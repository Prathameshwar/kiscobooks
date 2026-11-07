import { notFound } from 'next/navigation';
import { ErrorState } from '@janso/ui';
import { Providers } from '../../providers';
import { ConsoleShell } from '../../components/ConsoleShell';
import { NoCompany } from '../../components/NoCompany';
import { ProductWarehousePolicies } from '../../components/ProductWarehousePolicies';
import { pageContext } from '../../lib/page-context';
import { companyPermission } from '../../lib/company-permissions';
import { trackingId } from '../../lib/stock-tracking-resources';

export default async function ProductWarehousePolicyPage({ searchParams }: { searchParams?: Promise<{ item_id?: string | string[] }> }) {
  const query = await searchParams;
  if (typeof query?.item_id !== 'string' || !trackingId.test(query.item_id)) notFound();
  const { session, context } = await pageContext(), company = session.company.id;
  const allows = (permission: string) => companyPermission(session, permission, company);
  return <Providers session={session}><ConsoleShell session={session} context={context} activeHref="/masters/items">
    {!company ? <NoCompany action="maintain warehouse policies for" context={context} canCreate={allows('company.create')} /> : !allows('item.read') || !allows('warehouse.read') || !allows('item_warehouse_policy.read') ? <ErrorState status={403} /> : <ProductWarehousePolicies key={company + ':' + query.item_id} company={company} item={query.item_id} canManage={allows('item_warehouse_policy.manage')} />}
  </ConsoleShell></Providers>;
}
