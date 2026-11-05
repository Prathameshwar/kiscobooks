import { CompanyYearPage } from '../../../../components/CompanyYearPage';
export default async function FinancialYearPage({ params, searchParams = Promise.resolve({}) }: { searchParams?: Promise<{ returnTo?: string }>; params: Promise<{ companyId: string; yearId: string }> }) {
  return CompanyYearPage({ ...await params, returnTo: (await searchParams).returnTo });
}
