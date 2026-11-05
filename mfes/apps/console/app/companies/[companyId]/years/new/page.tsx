import { CompanyYearPage } from '../../../../components/CompanyYearPage';
export default async function GenerateYearPage({ params, searchParams = Promise.resolve({}) }: { searchParams?: Promise<{ returnTo?: string }>; params: Promise<{ companyId: string }> }) {
  return CompanyYearPage({ ...await params, returnTo: (await searchParams).returnTo, mode: 'new' });
}
