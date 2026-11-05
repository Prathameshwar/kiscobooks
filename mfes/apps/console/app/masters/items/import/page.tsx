import { ErrorState } from '@janso/ui';
import { notFound } from 'next/navigation';
import { Providers } from '../../../providers';
import { ConsoleShell } from '../../../components/ConsoleShell';
import { NoCompany } from '../../../components/NoCompany';
import { ProductImport } from '../../../components/ProductImport';
import { pageContext } from '../../../lib/page-context';
import { companyPermission } from '../../../lib/company-permissions';

export default async function ProductImportPage({
  searchParams = Promise.resolve({}),
}: {
  searchParams?: Promise<{ job?: string; view?: string; returnTo?: string }>;
}) {
  const query = await searchParams;
  if (
    query.job &&
    !/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(query.job)
  )
    notFound();
  const { session, context } = await pageContext(),
    company = session.company.id;
  const allows = (permission: string) =>
    !!company && companyPermission(session, permission, company);
  return (
    <Providers session={session}>
      <ConsoleShell
        session={session}
        context={context}
        activeHref="/masters/items"
      >
        {!company ? (
          <NoCompany
            action="import products"
            context={context}
            canCreate={companyPermission(session, 'company.create')}
          />
        ) : !allows('item.read') || !allows('catalog.bulk.read') ? (
          <ErrorState
            status={403}
            detail="Product read and import read access are required for this company."
          />
        ) : (
          <ProductImport
            key={company + ':' + (query.job ?? 'new')}
            company={company}
            canManage={allows('catalog.bulk.manage')}
            initialJob={query.job?.toLowerCase()}
            initialHistory={query.view === 'history'}
            returnTo={query.returnTo}
          />
        )}
      </ConsoleShell>
    </Providers>
  );
}
