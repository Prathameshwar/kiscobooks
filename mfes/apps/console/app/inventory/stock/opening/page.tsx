import { ErrorState } from '@janso/ui';
import { Providers } from '../../../providers';
import { ConsoleShell } from '../../../components/ConsoleShell';
import { OpeningStockWorkspace } from '../../../components/OpeningStockWorkspace';
import { pageContext } from '../../../lib/page-context';
import { companyPermission } from '../../../lib/company-permissions';

export default async function OpeningStockPage({
  searchParams,
}: {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { session, context } = await pageContext(),
    query = await searchParams;
  const company = session.company.id;
  const id =
    typeof query?.item_id === 'string' &&
    /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(query.item_id)
      ? query.item_id.toLowerCase()
      : undefined;
  const allowed =
    !!company && companyPermission(session, 'accounting.stock.read', company);
  const can = (key: string) =>
    !!company && companyPermission(session, key, company!);
  const access = {
    manage:
      can('accounting.finance.manage') &&
      can('accounting.stock.configure') &&
      can('period.post'),
    draft: can('vouchers.import.manage') && can('vouchers.create'),
    importRead: can('vouchers.import.read') && can('vouchers.read'),
    commit: can('vouchers.import.commit') && can('vouchers.create'),
    zero:
      can('opening_balance.initialize_zero') ||
      can('accounting.finance.manage'),
    export: can('accounting.export.read'),
  };
  return (
    <Providers session={session}>
      <ConsoleShell session={session} context={context} activeHref="/masters">
        {!company || !allowed ? (
          <div className="janso-page">
            <ErrorState
              status={403}
              detail="Choose a company with stock read access to review its opening."
            />
          </div>
        ) : (
          <OpeningStockWorkspace
            key={company}
            company={company}
            currency={session.display.currency ?? ''}
            access={access}
            initialItemId={id}
          />
        )}
      </ConsoleShell>
    </Providers>
  );
}
