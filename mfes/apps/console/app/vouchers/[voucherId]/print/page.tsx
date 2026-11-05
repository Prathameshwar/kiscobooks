import { ErrorState } from '@janso/ui';
import { Providers } from '../../../providers';
import { ConsoleShell } from '../../../components/ConsoleShell';
import { PurchasePrintPreview } from '../../../components/PurchasePrintPreview';
import { pageContext } from '../../../lib/page-context';
import { companyPermission } from '../../../lib/company-permissions';
import { trackingId } from '../../../lib/stock-tracking-resources';
import { PRINT_PERMISSIONS } from '../../../lib/purchase-print-action';

export const metadata = { title: 'Purchase print' };

export default async function PurchasePrintPage({ params, searchParams }: {
  params: Promise<{ voucherId: string }>;
  searchParams: Promise<{ revision?: string; version?: string }>;
}) {
  const { session, context } = await pageContext();
  const { voucherId } = await params;
  const { revision, version } = await searchParams;
  const company = session.company.id;
  const valid = trackingId.test(voucherId) && typeof revision === 'string' && trackingId.test(revision)
    && typeof version === 'string' && /^[1-9]\d{0,8}$/.test(version);
  const permitted = company && PRINT_PERMISSIONS
    .every(permission => companyPermission(session, permission, company));
  return <Providers session={session}>
    <ConsoleShell session={session} context={context} activeHref="/vouchers">
      {valid && permitted ? <PurchasePrintPreview key={company + voucherId + revision + version}
        company={company} voucherId={voucherId} revisionId={revision!} version={Number(version)} />
        : <ErrorState status={permitted ? 422 : 403} />}
    </ConsoleShell>
  </Providers>;
}
