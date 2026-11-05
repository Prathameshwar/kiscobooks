import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import { ErrorState } from '@janso/ui';
import { Providers } from '../../../providers';
import { pageContext } from '../../../lib/page-context';
import { companyPermission } from '../../../lib/company-permissions';
import { ConsoleShell } from '../../../components/ConsoleShell';
import { NoCompany } from '../../../components/NoCompany';
import { VoucherPrintKind } from '../../../components/VoucherPrintKind';
import { kindFromSlug, kindLabel } from '../../../lib/voucher-kinds';
import { operateReturn } from '../../../lib/operate-navigation';

/**
 * One voucher kind's print. An unrecognised segment *is* a 404 — it was never offered as a card,
 * and guessing "the nearest kind" would show one voucher's templates under another's name.
 */

export async function generateMetadata({ params }: { params: Promise<{ kind: string }> }): Promise<Metadata> {
  const kind = kindFromSlug((await params).kind);
  if (!kind) notFound();
  return {
    title: `${kindLabel(kind)} print · KiscoBooks`,
    description: `The templates a ${kindLabel(kind).toLowerCase()} prints on, and a way to design another.`,
  };
}

export default async function VoucherPrintKindPage({ params, searchParams }: { params: Promise<{ kind: string }>; searchParams?: Promise<{ returnTo?: string | string[] }> }) {
  const kind = kindFromSlug((await params).kind);
  if (!kind) notFound();
  const returnTo = operateReturn((await searchParams)?.returnTo);

  const { session, context } = await pageContext();
  const company = session.company.id;
  const canRead = !!company && companyPermission(session, 'design.template.read', company);
  const canManageTemplates = !!company && companyPermission(session, 'design.template.manage', company);
  const canReadRouting = !!company && companyPermission(session, 'design.assignment.read', company);
  const canManageRouting = !!company && companyPermission(session, 'design.assignment.manage', company);

  return (
    <Providers session={session}>
      <ConsoleShell session={session} context={context} activeHref={returnTo ?? '/documents/vouchers'}>
        {!company ? (
          <NoCompany
            action="design voucher prints for"
            context={context}
            canCreate={companyPermission(session, 'company.create')}
          />
        ) : !canRead ? (
          <ErrorState status={403} detail="Template read access is required for this company." />
        ) : (
          <VoucherPrintKind
            key={company + kind}
            company={company}
            kind={kind}
            canManageTemplates={canManageTemplates}
            canReadRouting={canReadRouting}
            canManageRouting={canManageRouting}
            returnTo={returnTo}
          />
        )}
      </ConsoleShell>
    </Providers>
  );
}
