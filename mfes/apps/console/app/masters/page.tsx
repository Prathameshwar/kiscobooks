import { ConsoleShell } from '../components/ConsoleShell';
import { CompanyMasters } from '../components/CompanyMasters';
import { pageContext } from '../lib/page-context';
import { Providers } from '../providers';

export default async function MastersPage() {
  const { session, context } = await pageContext();
  return <Providers session={session}><ConsoleShell session={session} context={context} activeHref="/masters">
    <CompanyMasters key={session.company.id ?? 'none'} session={session} context={context} />
  </ConsoleShell></Providers>;
}
