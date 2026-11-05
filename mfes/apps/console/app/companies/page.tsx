import { ConsoleShell } from '../components/ConsoleShell';
import { Companies } from '../components/Companies';
import { Providers } from '../providers';
import { pageContext } from '../lib/page-context';
import { organisationPermissions } from '../lib/session-authority';
import { companyPermission } from '../lib/company-permissions';

/**
 * The company directory the rail has always linked to. It is reachable without
 * `company.create`: the list is how someone with several companies moves between them, and
 * the empty state is how someone with none finds out why.
 */
export default async function CompaniesPage() {
  const { session, context } = await pageContext();

  return (
    <Providers session={session}>
      <ConsoleShell session={session} context={context} activeHref="/companies">
        <Companies
          companies={context.companies}
          note={context.companiesNote}
          openCompanyId={session.company.id}
          canCreate={organisationPermissions(session).includes('company.create')}
          canManage={companyPermission(session, 'company.read')}
          grants={session.grants}
          initialPage={context.companiesPage}
        />
      </ConsoleShell>
    </Providers>
  );
}
