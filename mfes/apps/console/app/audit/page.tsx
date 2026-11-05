import { ConsoleShell } from '../components/ConsoleShell';
import { AuditEvents } from '../components/AuditEvents';
import { Providers } from '../providers';
import { pageContext } from '../lib/page-context';
import { ErrorState, Notice, PageNavigation } from '@janso/ui';
import { NoCompany } from '../components/NoCompany';
import { logsAndActivitiesAccess, logsAndActivitiesPath } from '../lib/logs-navigation';
import { tenantPermission } from '../lib/company-permissions';

export default async function AuditPage({
  searchParams,
}: {
  searchParams: Promise<{ company_id?: string | string[]; entity_id?: string | string[]; entity_type?: string | string[]; scope?: string | string[] }>;
}) {
  const [{ session, context }, filters] = await Promise.all([pageContext(), searchParams]);
  const organisation = filters.scope === 'organisation';
  const invalid = Object.values(filters).some(value => value !== undefined && typeof value !== 'string')
    || (filters.scope !== undefined && filters.scope !== 'company' && !organisation)
    || (organisation && filters.company_id !== undefined);
  const companyFilter = typeof filters.company_id === 'string' ? filters.company_id : undefined;
  const entityId = typeof filters.entity_id === 'string' ? filters.entity_id : undefined;
  const entityType = typeof filters.entity_type === 'string' ? filters.entity_type : undefined;
  const navigation = <PageNavigation back={{ href: logsAndActivitiesPath, label: 'logs and activities' }} breadcrumbs={[{ label: 'Business overview', href: '/' }, { label: 'Logs and activities', href: logsAndActivitiesPath }, { label: 'Audit logs' }]} />;
  const unavailable = !session.company.id && !organisation ? <NoCompany action="inspect company history for" context={context} canCreate={session.permissions.includes('company.create')} />
    : !(organisation ? tenantPermission(session, 'audit.read') : logsAndActivitiesAccess(session).audit) ? <ErrorState status={403} />
    : invalid ? <Notice tone="warning">This history link contains invalid filters.</Notice>
    : companyFilter && companyFilter.toLowerCase() !== session.company.id?.toLowerCase() ? <Notice tone="warning">Open the company associated with this history link before viewing its records.</Notice>
    : null;
  return (
    <Providers session={session}>
      <ConsoleShell session={session} context={context} activeHref="/audit">
        {unavailable ? <div className="janso-page">{navigation}{unavailable}</div>
          : <AuditEvents key={[organisation ? 'organisation' : session.company.id, entityType, entityId].join(':')} companyId={organisation ? undefined : session.company.id}
            entityId={entityId} entityType={entityType} navigation={navigation} />}
      </ConsoleShell>
    </Providers>
  );
}
