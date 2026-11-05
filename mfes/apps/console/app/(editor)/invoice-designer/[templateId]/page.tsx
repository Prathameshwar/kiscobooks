import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import { ErrorState } from '@janso/ui';
import { Providers } from '../../../providers';
import { pageContext } from '../../../lib/page-context';
import { companyPermission } from '../../../lib/company-permissions';
import { PRINT_PERMISSIONS } from '../../../lib/purchase-print-action';
import { DesignerRoute } from '../DesignerRoute';

/**
 * The invoice designer, on one real template.
 *
 * The route's shape did not change when it stopped being a fixture — it always took a template
 * id — which is what the UI-first phases were betting on. What changed is that the id now has
 * to be a real one: a malformed path is a 404 before any request is made, rather than a
 * service round trip that answers 422 and a screen that has to explain it.
 */

export const metadata: Metadata = {
  title: 'Invoice designer · KiscoBooks',
  description: 'Design the layout of printed invoices, challans and receipts.',
};

const UUID = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;

export default async function InvoiceDesignerPage({
  params,
}: {
  params: Promise<{ templateId: string }>;
}) {
  const { templateId } = await params;
  if (!UUID.test(templateId)) notFound();

  const { session } = await pageContext();
  const company = session.company.id;
  // Reading opens the editor; `design.template.manage` is what a *save* needs. A reader
  // without it sees the design read-only rather than a denial — looking at a layout is a
  // legitimate thing to be allowed to do, and the service refuses the write regardless.
  const canRead = !!company && companyPermission(session, 'design.template.read', company);
  const canManage = !!company && companyPermission(session, 'design.template.manage', company);
  // Each piece of the designer's Purchase flow (plan R4) is offered only to whoever may use it.
  const has = (permission: string) => !!company && companyPermission(session, permission, company);

  return (
    <Providers session={session}>
      {!company || !canRead ? (
        <main className="janso-gallery">
          <ErrorState
            status={403}
            detail="Template read access for an open company is required to use the designer."
          />
        </main>
      ) : (
        <DesignerRoute
          key={company + ':' + templateId}
          company={company}
          templateId={templateId.toLowerCase()}
          canManage={canManage}
          canReadRouting={has('design.assignment.read')}
          canManageRouting={has('design.assignment.manage')}
          canReadVouchers={has('vouchers.read')}
          canPreview={PRINT_PERMISSIONS.every(has)}
        />
      )}
    </Providers>
  );
}
