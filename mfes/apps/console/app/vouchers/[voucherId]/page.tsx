import {
  Card,
  CardBody,
  ErrorState,
  PageHeader,
  PageNavigation,
} from '@janso/ui';
import { Providers } from '../../providers';
import { ConsoleShell } from '../../components/ConsoleShell';
import { VoucherWorkflow } from '../../components/VoucherWorkflow';
import { pageContext } from '../../lib/page-context';
import { companyPermission } from '../../lib/company-permissions';
import { dayBookReturnTo } from '../../lib/day-book';
import { trackingId } from '../../lib/stock-tracking-resources';
import { operateReturn } from '../../lib/operate-navigation';

export default async function VoucherDetailPage({
  params, searchParams,
}: {
  params: Promise<{ voucherId: string }>;
  searchParams?: Promise<{ returnTo?: string | string[] }>;
}) {
  const { session, context } = await pageContext(),
    { voucherId } = await params,
    company = session.company.id;
  const suppliedReturn = (await searchParams)?.returnTo;
  const dayBookReturn = dayBookReturnTo(suppliedReturn, company ?? '');
  const operationReturn = operateReturn(suppliedReturn);
  const returnTo = dayBookReturn ?? operationReturn;
  const permissions = company
    ? session.permissions.filter((key) =>
        companyPermission(session, key, company),
      )
    : [];
  return (
    <Providers session={session}>
      <ConsoleShell session={session} context={context} activeHref={dayBookReturn ? '/books/day-book' : operationReturn ?? '/vouchers'}>
        <div className="janso-page">
          <PageNavigation
            back={{ href: returnTo ?? '/vouchers', label: dayBookReturn ? 'Day Book' : operationReturn ? 'voucher list' : 'voucher drafts' }}
          />
          <PageHeader
            title="Voucher review"
            lede="Review the saved voucher, follow its approval workflow and check native posting confirmation."
          />
          {company &&
          permissions.includes('vouchers.read') &&
          trackingId.test(voucherId) ? (
            <Card>
              <CardBody>
                <VoucherWorkflow
                  key={company + voucherId}
                  company={company}
                  voucherId={voucherId}
                  permissions={permissions}
                />
              </CardBody>
            </Card>
          ) : (
            <ErrorState status={403} />
          )}
        </div>
      </ConsoleShell>
    </Providers>
  );
}
