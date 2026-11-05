import { ErrorState, PageHeader, PageNavigation } from '@janso/ui';
import { Providers } from '../../providers';
import { ConsoleShell } from '../../components/ConsoleShell';
import { BankReconciliation } from '../../components/BankReconciliation';
import { pageContext } from '../../lib/page-context';
import { companyPermission } from '../../lib/company-permissions';

export default async function BankReconciliationPage() {
  const { session, context } = await pageContext(), company = session.company.id;
  const permissions = session.permissions.filter(key => !!company && companyPermission(session, key, company));
  const allowed = !!company && ['accounting.bank.read', 'accounting.statement.read'].every(key => companyPermission(session, key, company));
  return <Providers session={session}><ConsoleShell session={session} context={context} activeHref="/masters">
    {!allowed ? <div className="janso-page"><ErrorState status={403} detail="Choose a company with bank and statement read access to review bank opening items." /></div>
      : <div className="janso-page"><PageNavigation back={{ href: '/accounting/opening', label: 'Account and party openings' }} breadcrumbs={[{ label: 'Masters', href: '/masters' }, { label: 'Bank reconciliation' }]} />
        <PageHeader title="Bank reconciliation and opening items" lede="Outstanding cheques and deposits support statement reconciliation. They do not post the bank opening balance again." />
        <BankReconciliation key={company} company={company} permissions={permissions} />
      </div>}
  </ConsoleShell></Providers>;
}
