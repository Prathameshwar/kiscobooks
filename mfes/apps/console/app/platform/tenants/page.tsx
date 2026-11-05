import { Notice } from '@janso/ui';
import { ConsoleShell } from '../../components/ConsoleShell';
import { Providers } from '../../providers';
import { pageContext } from '../../lib/page-context';
import { TenantDirectory } from './TenantDirectory';

export default async function TenantsPage() {
  const { session, context } = await pageContext();
  return <Providers session={session}><ConsoleShell session={session} context={context} activeHref="/platform/tenants">
    {session.permissions.includes('platform.tenant.read')
      ? <TenantDirectory permissions={session.permissions} ownTenantId={session.organisation.id} />
      : <Notice tone="danger">Platform administration permission is required.</Notice>}
  </ConsoleShell></Providers>;
}
