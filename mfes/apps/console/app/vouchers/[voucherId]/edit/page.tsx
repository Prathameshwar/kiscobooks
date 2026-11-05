import { notFound } from 'next/navigation';
import { ErrorState } from '@janso/ui';
import { Providers } from '../../../providers';
import { ConsoleShell } from '../../../components/ConsoleShell';
import { VoucherDraftEditor } from '../../../components/VoucherDraftEditor';
import { NoCompany } from '../../../components/NoCompany';
import { pageContext } from '../../../lib/page-context';
import { companyPermission } from '../../../lib/company-permissions';
import { trackingId } from '../../../lib/stock-tracking-resources';
import { operateReturn } from '../../../lib/operate-navigation';
export default async function VoucherEditPage({ params, searchParams }: { params: Promise<{ voucherId: string }>; searchParams: Promise<{ type_id?: string; returnTo?: string | string[] }> }) {
  const { voucherId } = await params, query = await searchParams, typeId = query.type_id, returnTo = operateReturn(query.returnTo);
  if (!trackingId.test(voucherId) || typeof typeId !== 'string' || !trackingId.test(typeId)) notFound();
  const { session, context } = await pageContext(), company = session.company.id;
  return <Providers session={session}><ConsoleShell session={session} context={context} activeHref={returnTo??'/vouchers'}>{!company ? <NoCompany action="edit" context={context} canCreate={companyPermission(session,'company.create')} /> : companyPermission(session, 'vouchers.read', company) && companyPermission(session, 'vouchers.edit', company) ? <VoucherDraftEditor key={company + ':' + voucherId} company={company} voucherId={voucherId} typeId={typeId} currency={session.display.currency ?? ''} returnTo={returnTo} /> : <ErrorState status={403} />}</ConsoleShell></Providers>;
}
