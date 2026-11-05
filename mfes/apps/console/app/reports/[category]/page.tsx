import { notFound } from 'next/navigation';
import { ErrorState } from '@janso/ui';
import { Providers } from '../../providers';
import { ConsoleShell } from '../../components/ConsoleShell';
import { NoCompany } from '../../components/NoCompany';
import { ReportsHub } from '../../components/ReportsHub';
import { pageContext } from '../../lib/page-context';
import { companyPermission } from '../../lib/company-permissions';
import { isReportCategory } from '../../lib/report-cards';

export default async function ReportCategoryPage({ params }: { params: Promise<{ category: string }> }) {
  const { category } = await params;
  if (!isReportCategory(category)) notFound();
  const { session, context } = await pageContext(), company = session.company.id;
  return <Providers session={session}><ConsoleShell session={session} context={context} activeHref={'/reports/' + category}>
    {!company ? <NoCompany action="report on" context={context} canCreate={companyPermission(session, 'company.create')} />
      : !companyPermission(session, 'report.read', company) ? <ErrorState status={403} />
      : <ReportsHub key={company + ':' + category} company={company} category={category} />}
  </ConsoleShell></Providers>;
}
