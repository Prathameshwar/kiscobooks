import { ErrorState } from '@janso/ui';
import { notFound } from 'next/navigation';
import { Providers } from '../../../../providers';
import { ConsoleShell } from '../../../../components/ConsoleShell';
import { CompanyBankCreate } from '../../../../components/CompanyBankCreate';
import { pageContext } from '../../../../lib/page-context';
import { companyPermission } from '../../../../lib/company-permissions';
import { accountingUUID } from '../../../../lib/accounting-configuration-resources';

export default async function NewCompanyBankPage({
  params,
  searchParams = Promise.resolve({}),
}: {
  params: Promise<{ companyId: string }>;
  searchParams?: Promise<{ returnTo?: string }>;
}) {
  const { companyId: raw } = await params,
    companyId = raw.toLowerCase();
  if (!accountingUUID.test(companyId)) notFound();
  const { session, context } = await pageContext(),
    query = await searchParams;
  return (
    <Providers session={session}>
      <ConsoleShell session={session} context={context} activeHref="/masters">
        {companyPermission(session, 'company.read', companyId) &&
        companyPermission(session, 'company.update', companyId) ? (
          <CompanyBankCreate
            key={companyId}
            company={companyId}
            returnTo={query.returnTo}
          />
        ) : (
          <ErrorState
            status={403}
            detail="Company read and update access are required to add company bank details."
          />
        )}
      </ConsoleShell>
    </Providers>
  );
}
