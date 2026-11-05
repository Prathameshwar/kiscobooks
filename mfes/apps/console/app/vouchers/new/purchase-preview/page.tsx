import type { Metadata } from 'next';
import { Providers } from '../../../providers';
import { pageContext } from '../../../lib/page-context';
import { companyPermission } from '../../../lib/company-permissions';
import { ConsoleShell } from '../../../components/ConsoleShell';
import { NoCompany } from '../../../components/NoCompany';
import { PurchaseWorkflowWorkspace } from '../../../components/PurchaseWorkflowWorkspace';
import { Notice } from '@janso/ui';

export const metadata: Metadata = { title: 'Purchase UI preview · KiscoBooks' };

/** Authenticated synthetic preview. Requires company-scoped vouchers.read or vouchers.create. */
export default async function PurchasePreviewPage() {
  const { session, context } = await pageContext();
  const company = session.company.id;
  const canCreate = !!company && companyPermission(session, 'vouchers.create', company);
  const canRead = !!company && companyPermission(session, 'vouchers.read', company);
  const today = new Intl.DateTimeFormat('en-CA', { timeZone: session.display.timezone || 'Asia/Kolkata', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
  return <Providers session={session}><ConsoleShell session={session} context={context} activeHref="/vouchers/new/purchase">
    {!company ? <NoCompany action="preview a purchase for" context={context} canCreate={companyPermission(session, 'company.create')} />
      : !canRead && !canCreate ? <Notice tone="danger" title="Purchase access required">You do not have permission to view or create vouchers for this company.</Notice>
      : <PurchaseWorkflowWorkspace context={{ company, year: context.fiscalYear?.id ?? 'unselected' }} today={today}
          permissions={{ create: canCreate, edit: companyPermission(session, 'vouchers.edit', company), submit: companyPermission(session, 'vouchers.submit', company) }} />}
  </ConsoleShell></Providers>;
}
