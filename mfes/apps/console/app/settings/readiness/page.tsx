import { Providers } from '../../providers';
import { ConsoleShell } from '../../components/ConsoleShell';
import { NoCompany } from '../../components/NoCompany';
import { CompanyReadiness } from '../../components/CompanyReadiness';
import { pageContext } from '../../lib/page-context';
import { companyPermission } from '../../lib/company-permissions';

export default async function CompanyReadinessPage() {
  const { session, context } = await pageContext();
  const permissions = ['company.read', 'company.update', 'accounting.finance.read', 'period.read', 'ledger.read', 'report.read', 'opening_balance.initialize_zero', 'accounting.finance.manage']
    .filter(key => !!session.company.id && companyPermission(session, key, session.company.id));
  return <Providers session={session}><ConsoleShell session={session} context={context} activeHref="/settings">
    {session.company.id ? <CompanyReadiness key={session.company.id + ':' + context.fiscalYear?.id} company={session.company.id} name={session.company.name}
      permissions={permissions} year={context.fiscalYear} fiscalNote={context.fiscalNote} />
      : <NoCompany action="check setup for" context={context} canCreate={companyPermission(session, 'company.create')} />}
  </ConsoleShell></Providers>;
}
