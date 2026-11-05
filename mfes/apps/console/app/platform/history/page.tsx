import { platformNavigationPermissions } from '../../lib/session-authority';
import { Notice, PageNavigation } from '@janso/ui';
import { AuditEvents } from '../../components/AuditEvents';
import { ConsoleShell } from '../../components/ConsoleShell';
import { Providers } from '../../providers';
import { pageContext } from '../../lib/page-context';
import { administrationBackLabel, administrationReturn } from '../../lib/administration-navigation';

export default async function PlatformHistoryPage({ searchParams }: { searchParams: Promise<{ entity_type?: string; entity_id?: string; returnTo?: string }> }) {
  const { session, context } = await pageContext();
  const filters = await searchParams;
  const back = filters.returnTo ? administrationReturn('tenants', filters.returnTo) : '/platform';
  const permitted = session.permissions.some(key => platformNavigationPermissions.includes(key));
  return <Providers session={session}><ConsoleShell session={session} context={context} activeHref="/platform/history">
    <PageNavigation back={{ href: back, label: administrationBackLabel(back) }} breadcrumbs={[{ label: 'Platform administration', href: '/platform' }, { label: 'History' }]} />
    {permitted ? <AuditEvents platform entityType={filters.entity_type} entityId={filters.entity_id} /> : <Notice tone="danger">Platform history permission is required.</Notice>}
  </ConsoleShell></Providers>;
}
