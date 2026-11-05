import { Providers } from '../providers';
import { ConsoleShell } from '../components/ConsoleShell';
import { MyAccess } from '../components/MyAccess';
import { pageContext } from '../lib/page-context';

export default async function MyAccessPage() {
  const { session, context } = await pageContext();
  // Authenticated self-read of the session; it needs no directory-management permission.
  return <Providers session={session}><ConsoleShell session={session} context={context} activeHref="/my-access"><MyAccess key={session.organisation.id + ':' + session.company.id} session={session} /></ConsoleShell></Providers>;
}
