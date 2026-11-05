import { ErrorState } from '@janso/ui';
import { Providers } from '../../providers';
import { ConsoleShell } from '../../components/ConsoleShell';
import { FinancialOpeningWorkspace } from '../../components/FinancialOpeningWorkspace';
import { pageContext } from '../../lib/page-context';
import { companyPermission } from '../../lib/company-permissions';
import { trackingId } from '../../lib/stock-tracking-resources';

export default async function FinancialOpeningPage({ searchParams }: { searchParams?: Promise<Record<string, string | string[] | undefined>> }) {
  const { session, context } = await pageContext(), query = await searchParams;
  const company = session.company.id;
  const can = (key: string) => !!company && companyPermission(session, key, company);
  const selected = (key: string) => typeof query?.[key] === 'string' && trackingId.test(query[key]) ? query[key].toLowerCase() : undefined;
  const access = { manage: can('accounting.finance.manage'), period: can('period.post'), cancel: can('accounting.finance.manage') && can('ledger.post_journal'), post: can('accounting.finance.manage') && can('ledger.post_journal') && can('period.post'), export: can('accounting.export.read') };
  return <Providers session={session}><ConsoleShell session={session} context={context} activeHref="/masters">
    {!company || !can('accounting.finance.read') ? <div className="janso-page"><ErrorState status={403} detail="Choose a company with finance read access to review its account and party opening balances." /></div>
      : <FinancialOpeningWorkspace key={company} company={company} access={access} initialAccountId={selected('account_id')} initialPartyId={selected('party_id')} initialBatchId={selected('batch_id')} />}
  </ConsoleShell></Providers>;
}
