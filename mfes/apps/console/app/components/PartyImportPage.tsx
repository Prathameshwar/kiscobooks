import { ErrorState } from '@janso/ui';
import { notFound } from 'next/navigation';
import { ConsoleShell } from './ConsoleShell';
import { NoCompany } from './NoCompany';
import { Providers } from '../providers';
import { pageContext } from '../lib/page-context';
import { companyPermission } from '../lib/company-permissions';
import { PartyImport } from './PartyImport';

export async function PartyImportPage({
  supplier = false,
  query = {},
}: {
  supplier?: boolean;
  query?: { job?: string; view?: string; returnTo?: string };
}) {
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
        activeHref={'/accounting/' + (supplier ? 'suppliers' : 'parties')}
      >
        {!company ? (
          <NoCompany
            action={supplier ? 'import suppliers' : 'import parties'}
            context={context}
            canCreate={companyPermission(session, 'company.create')}
          />
        ) : !allows('accounting.party.read') ||
          !allows('accounting.import.manage') ? (
          <ErrorState
            status={403}
            detail="Party read and Accounting import access are required for this company."
          />
        ) : (
          <PartyImport
            key={company + ':' + (query.job ?? 'new')}
            company={company}
            supplier={supplier}
            canManage={allows('accounting.party.manage')}
            initialJob={query.job?.toLowerCase()}
            initialHistory={query.view === 'history'}
            returnTo={query.returnTo}
          />
        )}
      </ConsoleShell>
    </Providers>
  );
}
