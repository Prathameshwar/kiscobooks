import type { DisplayConfig } from '@janso/ui';
import { PURCHASE_DEMO_POLICY, purchaseEvidenceSignature, type PurchaseWorkspacePolicy } from '../../../../mfes/apps/console/app/lib/purchase-workspace';
import { purchaseScenario } from '../../../../mfes/apps/console/app/lib/purchase-workspace-scenarios';

/** Harness data only. Never imported by an application route. */
export function reviewFixture(params: URLSearchParams) {
  const draft = purchaseScenario(params.get('scenario') || 'goods', '2026-10-31');
  const count = Number(params.get('lines'));
  if ([1, 50, 200].includes(count)) {
    const line = draft.lines[0]!;
    draft.lines = Array.from({ length: count }, (_, index) => ({ ...line, key: `p${index + 1}`, received: '1', billed: '1', discount: '0' }));
    draft.nextKey = count + 1; draft.details.advances = []; draft.details.components = [];
    if (draft.evidence) draft.evidence.signature = purchaseEvidenceSignature(draft);
  }
  let policy: PurchaseWorkspacePolicy = PURCHASE_DEMO_POLICY;
  if (params.get('scenario') === 'duplicate') policy = { ...policy, duplicateCheck: { supplier: draft.supplier, invoice: draft.invoice, references: ['DEMO-PUR-0042 · Same supplier / invoice · Submitted example'] } };
  if (params.has('restricted')) policy = { ...policy, costAccess: 'DENIED' };
  if (params.has('long')) {
    const label = 'A5 ruled notebooks · pack of 4 · कार्यालय सामग्री · Fournitures de bureau · supplier specification / extended purchase description';
    draft.lines[0] = { ...draft.lines[0]!, label, description: label.repeat(6) };
    policy = { ...policy, suppliers: policy.suppliers.map((supplier, index) => index ? supplier : { ...supplier, label: 'Paper & Co. Supplies · कार्यालय सामग्री · Comptoir de fournitures professionnelles et équipements de bureau' }),
      subjects: policy.subjects.map(subject => subject.id === draft.lines[0]!.subject ? { ...subject, label } : subject) };
  }
  const display: Partial<DisplayConfig> = params.has('locale') ? { locale: 'de-DE', dateFormat: 'dd.MM.yyyy', decimalSeparator: ',', groupSeparator: '.', digitGrouping: 'western', currencySymbolPosition: 'suffix' } : {};
  return { draft, policy, display };
}
