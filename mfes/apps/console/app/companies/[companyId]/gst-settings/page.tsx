import { ErrorState } from '@janso/ui';
import { notFound } from 'next/navigation';
import { Providers } from '../../../providers';
import { ConsoleShell } from '../../../components/ConsoleShell';
import { CompanyGstSettings } from '../../../components/CompanyGstSettings';
import { pageContext } from '../../../lib/page-context';
import { companyPermission } from '../../../lib/company-permissions';

export default async function CompanyGstSettingsPage({ params, searchParams = Promise.resolve({}) }: { params: Promise<{ companyId: string }>; searchParams?: Promise<{ returnTo?: string }> }) {
  const { companyId: raw } = await params, companyId = raw.toLowerCase();
  if (!/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.test(companyId)) notFound();
  const { session, context } = await pageContext(), query = await searchParams;
  return <Providers session={session}><ConsoleShell session={session} context={context} activeHref={'/companies/' + companyId + '/gst-settings'}>
    {companyPermission(session, 'company.read', companyId) ? <CompanyGstSettings key={companyId} session={session} companyId={companyId} returnTo={query.returnTo} /> : <ErrorState status={403} detail="Company read access is required for this company." />}
  </ConsoleShell></Providers>;
}
