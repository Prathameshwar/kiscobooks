import { ErrorState } from '@janso/ui';
import { ConsoleShell } from '../components/ConsoleShell';
import { ActivityFeed } from '../components/ActivityFeed';
import { NoCompany } from '../components/NoCompany';
import { Providers } from '../providers';
import { pageContext } from '../lib/page-context';
import { companyPermission, tenantPermission } from '../lib/company-permissions';

export default async function ActivityPage({ searchParams }: { searchParams?: Promise<{ scope?: string | string[] }> }) {
  const { session, context } = await pageContext();
  const scope = (await searchParams)?.scope;
  const invalid = scope !== undefined && scope !== 'company' && scope !== 'organisation';
  const organisation = scope === 'organisation';
  const canOrganisation = tenantPermission(session, 'activity.read');
  const company = session.company.id;
  return <Providers session={session}><ConsoleShell session={session} context={context} activeHref="/activity">
    {invalid ? <ErrorState status={422} />
      : !company && !organisation ? <NoCompany action="view activity for" context={context} canCreate={session.permissions.includes('company.create')} />
      : !(organisation ? canOrganisation : companyPermission(session, 'activity.read', company)) ? <ErrorState status={403} />
      : <ActivityFeed key={company + ':' + organisation} company={company ?? ''} organisation={organisation} canOrganisation={canOrganisation}
          canAudit={organisation ? tenantPermission(session, 'audit.read') : companyPermission(session, 'audit.read', company)} />}
  </ConsoleShell></Providers>;
}
