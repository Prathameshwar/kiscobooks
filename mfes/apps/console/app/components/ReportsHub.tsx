'use client';
import { ReportsIcon } from '@janso/ui';
import {
  reportCategories,
  reportSectionsFor,
  type ReportCategory,
} from '../lib/report-cards';
import { ReportCardCatalogue } from './ReportCardCatalogue';
export function ReportsHub({
  company,
  category,
}: {
  company: string;
  category?: ReportCategory;
}) {
  const selected = reportCategories.find((item) => item.key === category);
  return (
    <ReportCardCatalogue
      key={company}
      company={company}
      root="/reports"
      rootTitle="Reports"
      title={selected?.title ?? 'Reports'}
      description={
        selected?.description ??
        'Browse inventory, finance, tax and analytics reports by name or purpose.'
      }
      selected={category}
      sections={reportSectionsFor(category)}
      links={reportCategories.map((item) => ({
        key: item.key,
        title: item.title,
      }))}
      icon={<ReportsIcon />}
    />
  );
}
