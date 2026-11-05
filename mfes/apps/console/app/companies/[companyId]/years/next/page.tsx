import { CompanyYearPage } from '../../../../components/CompanyYearPage';
export default async function NextYearPage({ params, searchParams = Promise.resolve({}) }: {
  params: Promise<{ companyId: string }>; searchParams?: Promise<{ returnTo?: string; sourceYear?: string }>;
}) {
  const search = await searchParams;
  return CompanyYearPage({ ...await params, returnTo: search.returnTo, sourceYearId: search.sourceYear, mode: 'next' });
}
