import { Notice } from '@janso/ui';
import { notFound } from 'next/navigation';
import { ConsoleShell } from '../../../components/ConsoleShell';
import { Providers } from '../../../providers';
import { pageContext } from '../../../lib/page-context';
import { TenantDetail } from '../TenantDetail';

export default async function ViewTenantPage({ params, searchParams }: { params: Promise<{ tenantId: string }>; searchParams: Promise<{ returnTo?: string }> }) {
  const [{ session, context }, { tenantId }, query] = await Promise.all([pageContext(), params, searchParams]);
  if (!/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(tenantId)) notFound();
  return <Providers session={session}><ConsoleShell session={session} context={context} activeHref="/platform/tenants">
    {session.permissions.includes('platform.tenant.read') ? <TenantDetail tenantId={tenantId} permissions={session.permissions} ownTenantId={session.organisation.id} returnTo={query.returnTo} /> : <Notice tone="danger">Tenant read permission is required.</Notice>}
  </ConsoleShell></Providers>;
}
