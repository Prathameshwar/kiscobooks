import { ErrorState, Notice, PageHeader } from '@janso/ui';
import { Providers } from '../../../../../providers';
import { ConsoleShell } from '../../../../../components/ConsoleShell';
import { CompanyBalanceContinuity } from '../../../../../components/CompanyBalanceContinuity';
import { companyPermission } from '../../../../../lib/company-permissions';
import { pageContext } from '../../../../../lib/page-context';

export default async function ContinuityPage({ params, searchParams = Promise.resolve({}) }: {
  params: Promise<{ companyId: string; yearId: string }>; searchParams?: Promise<{ returnTo?: string }>;
}) {
  const { session, context } = await pageContext(), { companyId, yearId } = await params;
  const company = companyId.toLowerCase(), year = yearId.toLowerCase();
  const valid = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
  const permissions = ['report.read', 'report.export', 'report.definition.manage', 'period.read'].filter(key => companyPermission(session, key, company));
  const name = context.companies.find(item => item.id === company)?.name ?? (session.company.id === company ? session.company.name : 'Company');
  return <Providers session={session}><ConsoleShell session={session} context={context} activeHref={`/companies/${company}/years`}>
    {!valid.test(company) || !valid.test(year) ? <div className="janso-page"><PageHeader title="Review opening balances" /><Notice>Company or financial year not found. <a className="janso-link" href="/companies">Return to companies</a></Notice></div>
      : !permissions.includes('report.read') || !permissions.includes('period.read') ? <ErrorState status={403} detail="Opening-balance review needs report and financial-calendar read access for this company." />
        : <CompanyBalanceContinuity company={company} yearId={year} name={name} permissions={permissions} returnTo={(await searchParams).returnTo} />}
  </ConsoleShell></Providers>;
}
