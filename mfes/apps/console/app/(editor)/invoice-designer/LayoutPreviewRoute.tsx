'use client';

import { ErrorState, PageNavigation, Skeleton } from '@janso/ui';
import type { components } from '@janso/api-client/design';
import { PurchasePrintPreview } from '../../components/PurchasePrintPreview';
import { assertDesignRow, designBase, designRequest } from '../../lib/design-api';
import { useServiceRead } from '../../lib/service-resource';

type Wire = components['schemas'];

/**
 * One saved design version, printed on one saved Purchase revision (plan R4).
 *
 * The page names what it shows — the design and its version number — from the design service,
 * never from the link, so a crafted URL cannot make it claim a different design. The print
 * itself is the ordinary Purchase print with `layout_preview` beside the saved revision; Vouchers
 * checks the version belongs to a design this company may use and that the reader may read
 * designs, and marks every page of the PDF as a preview.
 */
export function LayoutPreviewRoute({
  company,
  templateId,
  designVersionId,
  voucherId,
  revisionId,
  version,
}: {
  company: string;
  templateId: string;
  designVersionId: string;
  voucherId: string;
  revisionId: string;
  version: number;
}) {
  const template = useServiceRead<Wire['TemplateDetail']>(
    designBase(company, '/' + templateId),
    designRequest,
    (value) => {
      assertDesignRow(value, company, templateId);
    },
    'design service',
  );
  const saved = useServiceRead<Wire['VersionDetail']>(
    `${designBase(company, '/' + templateId)}/versions/${designVersionId}`,
    designRequest,
    (value) => {
      assertDesignRow(value, company, designVersionId);
      if (value.template_id !== templateId) {
        throw { status: 502, message: 'The design version did not match this design. Reload before continuing.' };
      }
    },
    'design service',
  );
  const back = <PageNavigation back={{ href: `/invoice-designer/${templateId}`, label: 'designer' }} />;
  const failure = template.failure ?? saved.failure;

  if (failure) {
    return (
      <div className="janso-page">
        {back}
        {/* A foreign or deleted design answers 404, which is a 403 to the reader (CLAUDE.md §5.2). */}
        <ErrorState
          status={failure.status === 401 ? 401 : failure.status === 403 || failure.status === 404 ? 403 : 500}
          detail={failure.status === 403 ? 'You need permission to read designs to preview a layout with a saved bill.' : failure.message}
        />
      </div>
    );
  }
  if (template.loading || saved.loading || !template.data || !saved.data) {
    return (
      <div className="janso-page">
        {back}
        <Skeleton lines={3} />
      </div>
    );
  }
  if (template.data.voucher_kind && template.data.voucher_kind !== 'PURCHASE') {
    return (
      <div className="janso-page">
        {back}
        <ErrorState status={422} detail="Only a design for Purchase, or for any voucher, can be previewed with a Purchase bill." />
      </div>
    );
  }

  return (
    <PurchasePrintPreview
      key={[company, voucherId, revisionId, version, designVersionId].join(':')}
      company={company}
      voucherId={voucherId}
      revisionId={revisionId}
      version={version}
      layoutPreview={{
        templateId,
        versionId: designVersionId,
        templateName: template.data.name,
        versionNumber: saved.data.version_number,
      }}
    />
  );
}
