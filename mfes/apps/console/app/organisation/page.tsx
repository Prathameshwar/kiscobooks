import { Providers } from '../providers';
import { ConsoleShell } from '../components/ConsoleShell';
import { OrganisationOverview } from '../components/OrganisationOverview';
import { pageContext } from '../lib/page-context';

export default async function OrganisationPage() {
  const { session, context } = await pageContext();
  return <Providers session={session}><ConsoleShell session={session} context={context} activeHref="/organisation">
    <OrganisationOverview session={session} />
  </ConsoleShell></Providers>;
}
