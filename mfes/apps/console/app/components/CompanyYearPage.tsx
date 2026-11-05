import { ErrorState, Notice, PageHeader } from '@janso/ui';
import { Providers } from '../providers';
import { ConsoleShell } from './ConsoleShell';
import { CompanyFinancialYears } from './CompanyFinancialYears';
import { pageContext } from '../lib/page-context';
import { companyPermission } from '../lib/company-permissions';

export async function CompanyYearPage({ companyId, yearId, sourceYearId, mode = 'list', returnTo }: { companyId: string; yearId?: string; sourceYearId?: string; mode?: 'list' | 'new' | 'next'; returnTo?: string }) {
  const { session, context } = await pageContext();
  const valid = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
  const identifiersValid = valid.test(companyId) && (!yearId || valid.test(yearId)) && (!sourceYearId || valid.test(sourceYearId));
  companyId = companyId.toLowerCase(); yearId = yearId?.toLowerCase();
  const allowed = companyPermission(session, 'period.read', companyId) && (mode === 'list' || companyPermission(session, 'period.manage', companyId));
  const name = context.companies.find(company => company.id === companyId)?.name
    ?? (session.company.id === companyId ? session.company.name : 'Company');
  return <Providers session={session}><ConsoleShell session={session} context={context} activeHref={'/companies/' + companyId + '/years'}>
    {!identifiersValid ? <div className="janso-page"><PageHeader title="Financial years" /><Notice tone="warning">Company or financial year not found. <a className="janso-link" href="/companies">Return to companies</a></Notice></div>
      : !allowed ? <div className="janso-page"><PageHeader title="Financial years" /><ErrorState status={403} detail={mode !== 'list' ? 'Generating years needs period.read and period.manage for this company.' : 'Financial-year access needs period.read for this company.'} /></div>
      : <CompanyFinancialYears key={companyId + ':' + (yearId ?? mode)} session={session} companyId={companyId} companyName={name} yearId={yearId} mode={mode} sourceYearId={sourceYearId?.toLowerCase() ?? (mode === 'next' && session.company.id === companyId ? context.fiscalYear?.id : undefined)} returnTo={returnTo} />}
  </ConsoleShell></Providers>;
}
