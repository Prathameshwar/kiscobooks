import { ErrorState, Notice } from '@janso/ui';
import { ConsoleShell } from './ConsoleShell';
import { CompanyProfile } from './CompanyProfile';
import { Providers } from '../providers';
import { pageContext } from '../lib/page-context';
import { companyPermission } from '../lib/company-permissions';

export async function CompanyManagementPage({ companyId, editing = false, returnTo }: { companyId: string; editing?: boolean; returnTo?: string }) {
  const { session, context } = await pageContext();
  const valid = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(companyId);
  companyId = companyId.toLowerCase();
  const canRead = companyPermission(session, 'company.read', companyId), canEdit = companyPermission(session, 'company.update', companyId);
  return <Providers session={session}><ConsoleShell session={session} context={context} activeHref="/companies/manage">
    {!valid ? <Notice tone="warning">Company not found. <a className="janso-link" href="/companies/manage">Manage companies</a></Notice> : !canRead || (editing && !canEdit)
      ? <ErrorState status={403} detail={editing ? 'Editing needs company.read and company.update for this company.' : 'Company read access is needed for this company.'} />
      : <CompanyProfile key={companyId} companyId={companyId} editing={editing} canEdit={canEdit} returnTo={returnTo} />}
  </ConsoleShell></Providers>;
}
