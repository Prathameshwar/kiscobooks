import { ConsoleShell } from '../../components/ConsoleShell';
import { RolesAccessOverview } from '../../components/RolesAccessOverview';
import { pageContext } from '../../lib/page-context';
import { Providers } from '../../providers';

export default async function RolesAccessPage() {
  const { session, context } = await pageContext();
  return <Providers session={session}><ConsoleShell session={session} context={context} activeHref="/organisation/access">
    <RolesAccessOverview session={session} />
  </ConsoleShell></Providers>;
}
