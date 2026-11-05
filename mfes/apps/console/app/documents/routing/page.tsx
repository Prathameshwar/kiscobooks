import type { Metadata } from 'next';
import { ErrorState } from '@janso/ui';
import { Providers } from '../../providers';
import { pageContext } from '../../lib/page-context';
import { companyPermission } from '../../lib/company-permissions';
import { ConsoleShell } from '../../components/ConsoleShell';
import { DocumentRouting } from '../../components/DocumentRouting';
import { NoCompany } from '../../components/NoCompany';

/**
 * Document routing, inside the ordinary console shell.
 *
 * Unlike the designer itself, this is a table and two forms — it wants the rail, the company
 * chip and a page gutter. Only the canvas needs the whole viewport, which is why the editor
 * lives in its own full-bleed route group and this does not.
 */

export const metadata: Metadata = {
  title: 'Document routing · KiscoBooks',
  description: 'Which template each kind of document prints on.',
};

export default async function DocumentRoutingPage() {
  const { session, context } = await pageContext();
  const company = session.company.id;
  const canRead = !!company && companyPermission(session, 'design.assignment.read', company);
  const canManage = !!company && companyPermission(session, 'design.assignment.manage', company);

  return (
    <Providers session={session}>
      <ConsoleShell session={session} context={context} activeHref="/documents/routing">
        {!company ? (
          <NoCompany
            action="route documents for"
            context={context}
            canCreate={companyPermission(session, 'company.create')}
          />
        ) : !canRead ? (
          <ErrorState
            status={403}
            detail="Routing read access is required for this company."
          />
        ) : (
          <DocumentRouting key={company} company={company} canManage={canManage} />
        )}
      </ConsoleShell>
    </Providers>
  );
}
