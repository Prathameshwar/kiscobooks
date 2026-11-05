import { ErrorState, PageHeader, PageNavigation } from '@janso/ui';
import { ConsoleShell } from '../../components/ConsoleShell';
import { PlatformRoleUpdates } from '../../components/PlatformRoleUpdates';
import { pageContext } from '../../lib/page-context';
import { Providers } from '../../providers';

export default async function SystemRolesPage() {
  const { session, context } = await pageContext();
  return <Providers session={session}><ConsoleShell session={session} context={context} activeHref="/platform">
    <div className="janso-page">
      <PageNavigation back={{ href: '/platform', label: 'platform administration' }} breadcrumbs={[{ label: 'Platform administration', href: '/platform' }, { label: 'System role updates' }]} />
      <PageHeader title="System role updates" lede="Review and apply the current system role catalogue." />
      {session.permissions.includes('platform.config.manage') ? <PlatformRoleUpdates /> : <ErrorState status={403} />}
    </div>
  </ConsoleShell></Providers>;
}
