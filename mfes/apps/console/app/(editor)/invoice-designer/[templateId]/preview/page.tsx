import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import { ErrorState } from '@janso/ui';
import { Providers } from '../../../../providers';
import { ConsoleShell } from '../../../../components/ConsoleShell';
import { pageContext } from '../../../../lib/page-context';
import { companyPermission } from '../../../../lib/company-permissions';
import { PRINT_PERMISSIONS } from '../../../../lib/purchase-print-action';
import { trackingId } from '../../../../lib/stock-tracking-resources';
import { LayoutPreviewRoute } from '../../LayoutPreviewRoute';

export const metadata: Metadata = {
  title: 'Layout preview · KiscoBooks',
  description: 'A saved design version printed on a saved Purchase bill, marked as a preview.',
};

/**
 * *Preview with a saved bill* (plan R4): a saved design version on a saved Purchase revision.
 *
 * Inside the console shell like the Purchase print it is a variant of, rather than full-bleed like
 * the editor: it is a page to read, not a canvas. A preview shows a design that may be
 * unpublished, so reading designs is required on top of the Purchase print rights — the service
 * requires the same and refuses with 403 regardless.
 */
export default async function LayoutPreviewPage({
  params,
  searchParams,
}: {
  params: Promise<{ templateId: string }>;
  searchParams: Promise<{ design_version?: string; voucher?: string; revision?: string; version?: string }>;
}) {
  const { templateId } = await params;
  if (!trackingId.test(templateId)) notFound();
  const { design_version: designVersion, voucher, revision, version } = await searchParams;
  const { session, context } = await pageContext();
  const company = session.company.id;
  const valid =
    [designVersion, voucher, revision].every((value) => typeof value === 'string' && trackingId.test(value)) &&
    typeof version === 'string' && /^[1-9]\d{0,8}$/.test(version);
  const readsDesigns = !!company && companyPermission(session, 'design.template.read', company);
  const prints = !!company && PRINT_PERMISSIONS.every((permission) => companyPermission(session, permission, company));

  return (
    <Providers session={session}>
      <ConsoleShell session={session} context={context} activeHref="/invoice-designer">
        {!company || !readsDesigns ? (
          <ErrorState status={403} detail="You need permission to read designs to preview a layout with a saved bill." />
        ) : !prints ? (
          <ErrorState status={403} detail="Previewing with a saved bill needs permission to read and print Purchase bills." />
        ) : !valid ? (
          <ErrorState status={422} detail="Choose the bill again from the designer: this preview link is incomplete." />
        ) : (
          <LayoutPreviewRoute
            key={[company, templateId, designVersion, voucher, revision, version].join(':')}
            company={company}
            templateId={templateId.toLowerCase()}
            designVersionId={designVersion!.toLowerCase()}
            voucherId={voucher!.toLowerCase()}
            revisionId={revision!.toLowerCase()}
            version={Number(version)}
          />
        )}
      </ConsoleShell>
    </Providers>
  );
}
