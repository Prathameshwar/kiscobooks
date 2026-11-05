import { ErrorState } from '@janso/ui';
import { pageContext } from '../../../lib/page-context';
import { Providers } from '../../../providers';
import { ConsoleShell } from '../../../components/ConsoleShell';
import { TimezoneDirectory } from './TimezoneDirectory';
export default async function Page() {
  const { session, context } = await pageContext();
  return <Providers session={session}><ConsoleShell session={session} context={context} activeHref="/platform/references/timezones">{session.permissions.includes('platform.config.manage') ? <TimezoneDirectory /> : <ErrorState status={403} detail="Platform configuration permission is required to browse timezones." />}</ConsoleShell></Providers>;
}
