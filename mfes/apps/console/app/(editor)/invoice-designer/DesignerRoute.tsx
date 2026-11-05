'use client';

import { useMemo, useState } from 'react';
import { ErrorState, Notice, Skeleton } from '@janso/ui';
import { readPublishedDesignVersion, useDesignTemplate } from '../../lib/design-templates';
import { useDesignWrites } from '../../lib/design-commands';
import { useRoutingRules } from '../../lib/design-routing';
import { kindLabel } from '../../lib/voucher-kinds';
import { serviceCall, type ServiceRequest } from '../../lib/service-call';
import { useServiceRead } from '../../lib/service-resource';
import { manifestFor, printCapabilitiesPath, verifyPrintCapabilities, type PrintCapabilities } from './print-capabilities';

const voucherRead = <T,>(request: ServiceRequest) =>
  serviceCall<T>('/api/product-fields', { service: 'vouchers', ...request }, 'voucher service');
import { DesignerShell, type DesignerPersistence } from './DesignerShell';
import { SavedBillPicker } from './SavedBillPicker';
import { TemplateUsage } from './TemplateUsage';

/**
 * The editor, on one real template.
 *
 * `DesignerShell` keeps its own signature — a list of templates and which one to open — so the
 * eight phases of editor behaviour behind it are untouched. It is handed a list of one, because
 * the route names one template and loading every layout in the company to populate a switcher
 * would fetch a page of trees to draw one canvas.
 *
 * Persistence appends native versions through the scoped API. Historical layouts are read
 * on demand for restore; the editor retains the current layout until that read is verified.
 */
export function DesignerRoute({
  company,
  templateId,
  canManage,
  canReadRouting = false,
  canManageRouting = false,
  canReadVouchers = false,
  canPreview = false,
}: {
  company: string;
  templateId: string;
  /** `design.template.manage` for this company. Without it the editor opens read-only. */
  canManage: boolean;
  /** `design.assignment.read`: where this design is used. */
  canReadRouting?: boolean;
  /** `design.assignment.manage`: using it for a Purchase type, and stopping. */
  canManageRouting?: boolean;
  /** `vouchers.read`: naming the Purchase types a rule is for. */
  canReadVouchers?: boolean;
  /** The Purchase print rights: *Preview with a saved bill*. */
  canPreview?: boolean;
}) {
  const { template, paper, readOnlyReason, loading, failure, refresh } = useDesignTemplate(
    company,
    templateId,
  );
  const writes = useDesignWrites(company, templateId);
  // Purchase is the one kind that prints today; a template it is routed to is checked against
  // the manifest its printer publishes. A reader without routing or voucher read access gets no
  // such check — printing still refuses an unsupported layout, with its reason.
  const purchase = useRoutingRules(company, 'PURCHASE');
  const routed = purchase.rules.some((rule) => rule.is_active && rule.template_id === templateId);
  // A design made for a kind is checked for that kind from the first edit, routed or not.
  const printKind = template?.voucherKind ?? (routed ? 'PURCHASE' : undefined);
  const capabilities = useServiceRead<PrintCapabilities>(printKind ? printCapabilitiesPath(company) : undefined, voucherRead, verifyPrintCapabilities, 'voucher service');
  const printManifest = manifestFor(capabilities.data, printKind);
  const unprintable = !!printKind && !!capabilities.data && !printManifest;
  /** The saved version a bill is being chosen for, while the picker is open. */
  const [previewing, setPreviewing] = useState<{ id: string; versionNumber: number } | null>(null);
  // Only Purchase prints from a design, so only a Purchase design — or one for any voucher — is
  // assigned and previewed from here. Another kind keeps its "cannot be printed yet" notice.
  const forPurchase = !!template && (!template.voucherKind || template.voucherKind === 'PURCHASE');

  // Read-only wins over writable: a shipped design, an old layout format or a missing
  // `manage` grant each mean the same thing to the editor, and the reason is what differs.
  const blocked =
    readOnlyReason ??
    (canManage ? null : 'You have read access to this design but not permission to change it.');

  const persistence = useMemo<DesignerPersistence | undefined>(
    () =>
      blocked
        ? undefined
        : {
            saveDraft: writes.saveVersion,
            publish: writes.publishVersion,
            pending: writes.pending,
            failure: writes.failure,
            uncertain: writes.uncertain,
            reload: refresh,
            loadVersion: async versionId => {
              if (!paper) throw new Error('Template paper is unavailable.');
              return readPublishedDesignVersion(company, templateId, versionId, paper);
            },
          },
    [blocked, company, paper, refresh, templateId, writes.failure, writes.pending, writes.publishVersion, writes.saveVersion, writes.uncertain],
  );

  if (failure) {
    return (
      <main className="janso-gallery">
        {/* `ErrorState` covers 401/403/422/500 — a deleted or foreign template answers 404,
          * which is a 403 to the reader: "this is not yours to see" and "this is gone" must
          * not be distinguishable, or the 404 becomes an existence oracle (CLAUDE.md §5.2). */}
        <ErrorState
          status={failure.status === 403 || failure.status === 404 ? 403 : 500}
          detail={failure.message}
        />
      </main>
    );
  }
  if (loading || !template) {
    return (
      <main className="janso-gallery">
        <Skeleton lines={4} />
      </main>
    );
  }

  return (
    <>
      {blocked ? <Notice tone="warning">{blocked}</Notice> : null}
      {unprintable ? (
        <Notice>
          {kindLabel(printKind!)} vouchers cannot be printed from a design yet. This one is kept and
          is used once their printing arrives.
        </Notice>
      ) : null}
      {/* An uncertain write is its own state, louder than a failure: the version may or may
        * not exist, and the next attempt has to be the identical request rather than a
        * second one. `useServiceCommand` holds the key for exactly that. */}
      {writes.uncertain ? (
        <Notice tone="warning">
          The last save did not confirm. Retry the same action — it will not create a second
          version if the first one landed.
        </Notice>
      ) : null}
      <DesignerShell
        templates={[template]}
        initialTemplateId={template.id}
        company={company}
        {...(persistence ? { persistence } : {})}
        {...(blocked ? { readOnlyReason: blocked } : {})}
        {...(printManifest ? { printManifest } : {})}
        {...(forPurchase && canReadRouting
          ? {
              usage: (
                <TemplateUsage
                  company={company}
                  templateId={template.id}
                  published={!!template.liveVersionId}
                  canRead={canReadRouting}
                  canManage={canManageRouting}
                  canReadTypes={canReadVouchers}
                  onChanged={purchase.refresh}
                />
              ),
            }
          : {})}
        {...(forPurchase && canPreview ? { onPreviewWithBill: setPreviewing } : {})}
      />
      {previewing ? (
        <SavedBillPicker
          company={company}
          templateId={template.id}
          version={previewing}
          open
          onClose={() => setPreviewing(null)}
        />
      ) : null}
    </>
  );
}
