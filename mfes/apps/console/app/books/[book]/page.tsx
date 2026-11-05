import { notFound } from 'next/navigation';
import { ErrorState } from '@janso/ui';
import { Providers } from '../../providers';
import { ConsoleShell } from '../../components/ConsoleShell';
import { NoCompany } from '../../components/NoCompany';
import { BooksHub } from '../../components/BooksHub';
import { DayBookWorkspace } from '../../components/DayBookWorkspace';
import { NativeBookWorkspace } from '../../components/NativeBookWorkspace';
import { pageContext } from '../../lib/page-context';
import { companyPermission } from '../../lib/company-permissions';
import { isBookKey } from '../../lib/book-cards';
import { isNativeBook } from '../../lib/book-workspace';

export default async function BookPage({
  params,
}: {
  params: Promise<{ book: string }>;
}) {
  const { book } = await params;
  if (!isBookKey(book)) notFound();
  const { session, context } = await pageContext(),
    company = session.company.id;
  return (
    <Providers session={session}>
      <ConsoleShell
        session={session}
        context={context}
        activeHref={'/books/' + book}
      >
        {!company ? (
          <NoCompany
            action="report on"
            context={context}
            canCreate={companyPermission(session, 'company.create')}
          />
        ) : !companyPermission(session, 'report.read', company) ? (
          <ErrorState status={403} />
        ) : book === 'day-book' ? (
          <DayBookWorkspace key={company + ':' + session.user.id + ':day-book'} company={company} companyName={session.company.name}
            actor={session.user.id ?? ''} permissions={session.permissions.filter(permission => companyPermission(session, permission, company))}
            year={context.fiscalYear} />
        ) : isNativeBook(book) ? (
          <NativeBookWorkspace key={company + ':' + session.user.id + ':' + book} book={book} company={company} companyName={session.company.name}
            actor={session.user.id ?? ''} permissions={session.permissions.filter(permission => companyPermission(session, permission, company))}
            year={context.fiscalYear} />
        ) : (
          <BooksHub key={company + ':' + book} company={company} book={book} />
        )}
      </ConsoleShell>
    </Providers>
  );
}
