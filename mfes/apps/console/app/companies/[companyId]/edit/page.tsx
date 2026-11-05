import { CompanyManagementPage } from '../../../components/CompanyManagementPage';

export default async function EditCompanyPage({ params, searchParams = Promise.resolve({}) }: { params: Promise<{ companyId: string }>; searchParams?: Promise<{ returnTo?: string }> }) {
  const query = await searchParams;
  return CompanyManagementPage({ companyId: (await params).companyId, returnTo: query.returnTo, editing: true });
}
