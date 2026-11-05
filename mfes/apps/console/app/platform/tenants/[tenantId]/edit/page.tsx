import { Notice } from '@janso/ui';
import { notFound } from 'next/navigation';
import { ConsoleShell } from '../../../../components/ConsoleShell';
import { Providers } from '../../../../providers';
import { pageContext } from '../../../../lib/page-context';
import { TenantForm } from '../../TenantForm';

export default async function EditTenantPage({ params, searchParams }: { params: Promise<{ tenantId: string }>; searchParams: Promise<{ returnTo?: string }> }) {
  const [{ session, context }, { tenantId }, query] = await Promise.all([pageContext(), params, searchParams]);
  if (!/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(tenantId)) notFound();
  return <Providers session={session}><ConsoleShell session={session} context={context} activeHref="/platform/tenants">
    {['platform.tenant.read', 'platform.config.manage'].every(permission => session.permissions.includes(permission))
      ? <TenantForm scope={session.organisation.id ?? ''} tenantId={tenantId} returnTo={query.returnTo} /> : <Notice tone="danger">Tenant configuration permission is required.</Notice>}
  </ConsoleShell></Providers>;
}
