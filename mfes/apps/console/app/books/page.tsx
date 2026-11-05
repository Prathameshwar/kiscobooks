import { ErrorState } from '@janso/ui';
import { Providers } from '../providers';
import { ConsoleShell } from '../components/ConsoleShell';
import { NoCompany } from '../components/NoCompany';
import { BooksHub } from '../components/BooksHub';
import { pageContext } from '../lib/page-context';
import { companyPermission } from '../lib/company-permissions';

export default async function BooksPage() {
  const { session, context } = await pageContext();
  const company = session.company.id;
  return (
    <Providers session={session}>
      <ConsoleShell session={session} context={context} activeHref="/books">
        {!company ? (
          <NoCompany
            action="report on"
            context={context}
            canCreate={companyPermission(session, 'company.create')}
          />
        ) : companyPermission(session, 'report.read', company) ? (
          <BooksHub key={company} company={company} />
        ) : (
          <ErrorState status={403} />
        )}
      </ConsoleShell>
    </Providers>
  );
}
