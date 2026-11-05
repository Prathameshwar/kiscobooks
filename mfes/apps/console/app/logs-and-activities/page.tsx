import { ErrorState } from '@janso/ui';
import { ConsoleShell } from '../components/ConsoleShell';
import { LogsAndActivities } from '../components/LogsAndActivities';
import { NoCompany } from '../components/NoCompany';
import { Providers } from '../providers';
import { pageContext } from '../lib/page-context';
import { logsAndActivitiesAccess, logsAndActivitiesPath } from '../lib/logs-navigation';

export default async function LogsAndActivitiesPage() {
  const { session, context } = await pageContext();
  const access = logsAndActivitiesAccess(session);
  return <Providers session={session}><ConsoleShell session={session} context={context} activeHref={logsAndActivitiesPath}>
    {!session.company.id ? <NoCompany action="view logs and activities for" context={context} canCreate={session.permissions.includes('company.create')} />
      : !access.audit && !access.activities ? <ErrorState status={403} />
      : <LogsAndActivities canAudit={access.audit} canActivity={access.activities} />}
  </ConsoleShell></Providers>;
}
