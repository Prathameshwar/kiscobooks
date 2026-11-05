import type { Metadata } from 'next';
import { ErrorState } from '@janso/ui';
import { Providers } from '../../providers';
import { pageContext } from '../../lib/page-context';
import { companyPermission } from '../../lib/company-permissions';
import { ConsoleShell } from '../../components/ConsoleShell';
import { NoCompany } from '../../components/NoCompany';
import { VoucherPrintHub } from '../../components/VoucherPrintHub';

/**
 * Voucher print — one card per kind of voucher, inside the ordinary console shell.
 *
 * Like document routing, this is cards and tables: it wants the rail, the company chip and a page
 * gutter. Only the canvas needs the whole viewport, which is why the editor lives in its own
 * full-bleed route group and this does not.
 *
 * Opening the page needs `design.template.read` — the same key the rail entry is gated on. The
 * template counts on the cards are a courtesy read with `design.assignment.read` and are simply
 * absent without it; the design service authorizes every call again against the company.
 */

export const metadata: Metadata = {
  title: 'Voucher print · KiscoBooks',
  description: 'Design what each kind of voucher prints, and see which templates it uses.',
};

export default async function VoucherPrintPage() {
  const { session, context } = await pageContext();
  const company = session.company.id;
  const canRead = !!company && companyPermission(session, 'design.template.read', company);
  const canManage = !!company && companyPermission(session, 'design.template.manage', company);
  const canReadRouting = !!company && companyPermission(session, 'design.assignment.read', company);

  return (
    <Providers session={session}>
      <ConsoleShell session={session} context={context} activeHref="/documents/vouchers">
        {!company ? (
          <NoCompany
            action="design voucher prints for"
            context={context}
            canCreate={companyPermission(session, 'company.create')}
          />
        ) : !canRead ? (
          <ErrorState status={403} detail="Template read access is required for this company." />
        ) : (
          <VoucherPrintHub
            key={company}
            company={company}
            canManage={canManage}
            canReadRouting={canReadRouting}
          />
        )}
      </ConsoleShell>
    </Providers>
  );
}
