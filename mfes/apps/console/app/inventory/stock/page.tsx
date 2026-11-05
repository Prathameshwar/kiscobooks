import { ErrorState } from '@janso/ui';
import { pageContext } from '../../lib/page-context';
import { companyPermission } from '../../lib/company-permissions';
import type { StockView } from '../../lib/stock';
import { Providers } from '../../providers';
import { ConsoleShell } from '../../components/ConsoleShell';
import { NoCompany } from '../../components/NoCompany';
import { StockDirectory } from '../../components/StockDirectory';

export default async function Page({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const { session, context } = await pageContext(), company = session.company.id, query = await searchParams;
  const view: StockView = ['cost-pools', 'positions', 'movements', 'account-policies'].includes(String(query.view)) ? query.view as StockView : 'cost-pools';
  const params = new URLSearchParams(); for (const [key, value] of Object.entries(query)) if (typeof value === 'string') params.set(key, value);
  return <Providers session={session}><ConsoleShell session={session} context={context} activeHref="/masters">
    {!company ? <NoCompany action="review stock for" context={context} canCreate={companyPermission(session, 'company.create')} /> : !companyPermission(session, 'accounting.stock.read') ? <ErrorState status={403} detail="Stock read access is required for this company." /> : <StockDirectory key={`${company}:${view}`} company={company} view={view} initialQuery={params.toString()} canConfigure={companyPermission(session, 'accounting.stock.configure')} />}
  </ConsoleShell></Providers>;
}
