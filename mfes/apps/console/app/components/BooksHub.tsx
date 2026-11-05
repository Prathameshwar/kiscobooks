'use client';
import { BookIcon } from '@janso/ui';
import { bookEntries, bookSections, type BookKey } from '../lib/book-cards';
import { ReportCardCatalogue } from './ReportCardCatalogue';
export function BooksHub({ company, book }: { company: string; book?: BookKey }) {
  const selected = bookEntries.find((item) => item.key === book);
  return (
    <ReportCardCatalogue
      key={company}
      company={company}
      root="/books"
      rootTitle="Books"
      title={selected?.title ?? 'Books'}
      description={
        selected?.description ??
        'Browse posted company books, transaction registers and ledgers.'
      }
      selected={book}
      sections={bookSections(book)}
      links={bookEntries.map((item) => ({ key: item.key, title: item.title }))}
      icon={<BookIcon />}
    />
  );
}
