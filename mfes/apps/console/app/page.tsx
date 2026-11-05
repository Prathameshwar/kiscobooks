import { redirect } from 'next/navigation';
import { ConsoleShell } from './components/ConsoleShell';
import { CompanyOverview } from './components/CompanyOverview';
import { NoCompany } from './components/NoCompany';
import { companyPermission } from './lib/company-permissions';
import { pageContext } from './lib/page-context';
import { platformNavigationPermissions } from './lib/session-authority';
import { Providers } from './providers';
import { EmptyState, PageHeader } from '@janso/ui';

/**
 * A Server Component, and the one place per request where the session, the company context and
 * the overview's access are resolved. They are then passed down as props — never imported from
 * module scope by a client component, because a module-scope binding lives for the whole server
 * process and would be shared across tenants (see `session.ts`).
 *
 * With no company open and the authority to create one, this is the first screen after signing
 * in, so it sends the user straight to creating their first company rather than showing them an
 * empty dashboard they cannot fill. Anyone who cannot create one gets the explanation instead —
 * and `/companies/new` is excluded from that redirect by being a different route, so there is
 * no loop.
 */
export default async function DashboardPage({ searchParams = Promise.resolve({}) }: { searchParams?: Promise<{ period?: string | string[] }> }) {
  const { session, context } = await pageContext();
  const query = await searchParams;
  if (!session.company.id && platformNavigationPermissions.some(permission => session.permissions.includes(permission))) {
    redirect('/platform');
  }
  const dashboard = session.company.id && session.permissions.includes('report.read') && companyPermission(session, 'report.read', session.company.id);
  if (!session.company.id && context.companies.length === 0 && session.permissions.includes('company.create')) {
    redirect('/companies/new');
  }
  const company = session.company.id;
  // Navigation hints only: each destination re-checks its own access.
  const links = {
    opening: company && companyPermission(session, 'accounting.finance.read', company) ? '/accounting/opening' : undefined,
    voucher: company && companyPermission(session, 'vouchers.create', company) ? '/vouchers/new/sales' : undefined,
  };

  return (
    <Providers session={session}>
      <ConsoleShell session={session} context={context} activeHref="/">
        {company ? (
          dashboard ? <CompanyOverview key={company + ':' + context.fiscalYear?.id} company={company} yearId={context.fiscalYear?.id}
            companyName={session.company.name} yearLabel={context.fiscalYear?.code} initialPeriod={typeof query.period === 'string' ? query.period : undefined}
            canReadCustomers={companyPermission(session, 'accounting.party.read', company)} links={links} /> : (
            <div className="janso-page">
              <PageHeader title="Business overview" lede={session.company.name} />
              <EmptyState title="Company figures need report access" body="The overview shows this company's balances and posted activity, which requires report read access for it. Ask a company administrator to review your access. You can continue using the areas available in the menu." />
            </div>
          )
        ) : (
          <NoCompany action="show" context={context} canCreate={session.permissions.includes('company.create')} />
        )}
      </ConsoleShell>
    </Providers>
  );
}
