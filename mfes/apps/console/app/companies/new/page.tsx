import { ErrorState } from '@janso/ui';
import { CompanyWizard } from '../../components/CompanyWizard';
import { ConsoleShell } from '../../components/ConsoleShell';
import { Providers } from '../../providers';
import { getCompanyContext, getCompanyList } from '../../lib/company-context';
import { getSession } from '../../session';
import { organisationPermissions } from '../../lib/session-authority';
import { companyBootstrapAccess } from '../../lib/company-bootstrap';

/**
 * Creating a company. **Creation is a tenant-level act**: the server requires
 * `company.create` at tenant scope, so the rail hides the route without it and this refuses it
 * — the API is what enforces it either way (CLAUDE.md §5.1).
 *
 * The wizard renders outside the console shell when there is no company to switch between:
 * a rail whose every destination is unusable is noise in front of the one thing to do. So this
 * page resolves the session alone, and pays for the company context only on the refusal path
 * that actually renders a rail.
 */
export default async function NewCompanyPage({ searchParams = Promise.resolve({}) }: { searchParams?: Promise<{ returnTo?: string }> }) {
  const query = await searchParams;
  const session = await getSession();
  const permissions = organisationPermissions(session);
  if (!permissions.includes('company.create')) {
    return (
      <Providers session={session}>
        <ConsoleShell session={session} context={await getCompanyContext(session, await getCompanyList())} activeHref="/companies/manage">
          <ErrorState status={403} detail="Creating a company needs tenant-level company.create." />
        </ConsoleShell>
      </Providers>
    );
  }

  /*
   * Creation commits company-scoped Company Administrator access before the
   * remaining setup calls. Those calls still independently check live authority.
   */
  const canBootstrapBooks = companyBootstrapAccess(session, { creating: true }).books;

  return (
    <Providers session={session}>
      <CompanyWizard key={session.organisation?.id} session={session} canBootstrapBooks={canBootstrapBooks} returnTo={query.returnTo} />
    </Providers>
  );
}
