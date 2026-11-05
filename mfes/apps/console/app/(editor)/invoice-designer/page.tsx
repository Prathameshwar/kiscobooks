import type { Metadata } from 'next';
import { ErrorState } from '@janso/ui';
import { Providers } from '../../providers';
import { pageContext } from '../../lib/page-context';
import { companyPermission } from '../../lib/company-permissions';
import { DesignGalleryRoute } from './DesignGalleryRoute';

/**
 * The template gallery — the way into the designer.
 *
 * Request-scoped now, not static: it lists this company's real designs. The session resolves
 * here, in the Server Component, and is handed down as a prop — never imported from module
 * scope by a client component, where one binding would be shared across every tenant the
 * server process serves (see `session.ts`).
 *
 * `Providers` without `ConsoleShell`: the editor route group is full-bleed on purpose, but it
 * still needs the permission and display context every console screen reads from.
 */

export const metadata: Metadata = {
  title: 'Print templates · KiscoBooks',
  description: 'Printed document templates: invoices, challans and receipts.',
};

export default async function InvoiceTemplatesPage() {
  const { session } = await pageContext();
  const company = session.company.id;
  const canRead = !!company && companyPermission(session, 'design.template.read', company);
  const canManage = !!company && companyPermission(session, 'design.template.manage', company);

  return (
    <Providers session={session}>
      {!company ? (
        <main className="janso-gallery">
          <ErrorState
            status={403}
            detail="Open a company to see the document templates it prints on."
          />
        </main>
      ) : !canRead ? (
        <main className="janso-gallery">
          <ErrorState
            status={403}
            detail="Template read access is required for this company."
          />
        </main>
      ) : (
        <DesignGalleryRoute key={company} company={company} canManage={canManage} />
      )}
    </Providers>
  );
}
