import { describe, expect, it } from 'vitest';
import { PURCHASE_DEMO_POLICY as policy, purchaseExample, purchaseEvidenceSignature, purchaseWorkspacePreview, purchaseWorkspaceProblems, purchaseWorkspaceReducer } from '../app/lib/purchase-workspace';
import { normalizePurchaseCustom, purchaseDetailProblems, purchaseDueDate } from '../app/lib/purchase-workspace-details';
import { purchaseScenario } from '../app/lib/purchase-workspace-scenarios';
import { checkPurchaseAttachment } from '../app/lib/purchase-workspace-attachments';

const today = '2026-10-31';
const problems = (draft: ReturnType<typeof purchaseExample>) => purchaseWorkspaceProblems(draft, policy);
describe('Purchase details: bounded exact presentation', () => {
  it('recalculates supplied tax for document discount edits with an explicit base', () => {
    const draft = purchaseExample(today);
    draft.details.components.push({ id: 'pc2', label: 'Document discount', kind: 'DISCOUNT', basis: 'PERCENT', value: '10', targets: [], payable: true, taxTreatment: 'INCLUDED' });
    const preview = purchaseWorkspacePreview(draft);
    expect(preview.components.discount).toBe(4750000n);
    expect(preview.taxBase).toBe(43750000n);
    expect(preview.tax).toBe(7875000n);
    expect(preview.total).toBe(51625000n);
    expect(preview.settlement.remaining).toBe(41625000n);
    expect(problems(draft)).toEqual([]);
  });
  it('supports selected-line discounts and deterministic ordered discounts', () => {
    const draft = purchaseExample(today);
    draft.details.components.push({ id: 'pc2', label: 'Notebook discount', kind: 'DISCOUNT', basis: 'PERCENT', value: '10', targets: ['p1'], payable: true, taxTreatment: 'INCLUDED' });
    expect(purchaseWorkspacePreview(draft).components.discount).toBe(2850000n);
    draft.details.components.push({ id: 'pc3', label: 'Further notebook discount', kind: 'DISCOUNT', basis: 'AMOUNT', value: '65', targets: ['p1'], payable: true, taxTreatment: 'INCLUDED' });
    expect(purchaseWorkspacePreview(draft).components.discount).toBe(3500000n);
    draft.details.components[1]!.targets = ['removed-line'];
    expect(purchaseWorkspacePreview(draft).total).toBeNull();
    expect(problems(draft).some(problem => problem.panel === 'components')).toBe(true);
  });
  it('does not add recipient liability or additional costs to supplier payable', () => {
    const recipient = purchaseScenario('recipient', today);
    expect(purchaseWorkspacePreview(recipient)).toMatchObject({ total: 10000000n, tax: 0n, recipientTax: 1800000n });
    const draft = purchaseExample(today);
    draft.details.components.push({ id: 'pc2', label: 'Separate handling cost', kind: 'CHARGE', basis: 'AMOUNT', value: '50', targets: [], payable: false, taxTreatment: 'EXCLUDED' });
    expect(purchaseWorkspacePreview(draft)).toMatchObject({ total: 57230000n, components: { landedCharges: 500000n, supplierCharges: 1000000n } });
  });
  it('keeps unresolved treatments and changed supplier/date/core facts unavailable', () => {
    const draft = purchaseExample(today);
    draft.details.components[0]!.taxTreatment = 'UNRESOLVED';
    expect(purchaseWorkspacePreview(draft).total).toBeNull();
    expect(purchaseWorkspacePreview(purchaseWorkspaceReducer(purchaseExample(today), { type: 'header', field: 'postingDate', value: '2026-11-01' })).total).toBeNull();
  });
  it('keeps declared originals and blocks mismatches without a balancing adjustment', () => {
    const draft = purchaseExample(today);
    draft.details.declaredTotal = '5750';
    expect(purchaseWorkspacePreview(draft).settlement.difference).toBe(270000n);
    expect(problems(draft).some(problem => problem.field === 'declaredTotal')).toBe(true);
    expect(purchaseDetailProblems(draft, policy, 57230000n, 'APPLY')).toEqual([]);
    Object.assign(draft.details, { comparison: 'SUPPLIER_REVISED', revisedTotal: '5723', comparisonReason: 'Supplier correction email reference EX-1' });
    expect(problems(draft)).toEqual([]);
    expect(draft.details.declaredTotal).toBe('5750');
    expect(purchaseWorkspacePreview(draft).total).toBe(57230000n);
  });
  it('requires the original supplier total before accepting a revision', () => {
    const draft = purchaseExample(today);
    Object.assign(draft.details, { comparison: 'SUPPLIER_REVISED', revisedTotal: '5723', comparisonReason: 'Supplier correction' });
    expect(problems(draft).some(problem => problem.field === 'declaredTotal')).toBe(true);
  });
  it('uses calendar terms explicitly and bounds settlement to eligible supplied balances', () => {
    const draft = purchaseExample(today);
    expect(purchaseDueDate(draft)).toBe('2026-11-30');
    draft.details.payment = { amount: '2000', method: 'BANK', account: 'demo-bank', reference: 'Example instruction' };
    expect(purchaseWorkspacePreview(draft)).toMatchObject({ total: 57230000n, settlement: { remaining: 27230000n } });
    draft.details.payment.amount = '5000';
    expect(purchaseWorkspacePreview(draft).settlement.remaining).toBeNull();
    expect(problems(draft).some(problem => problem.field === 'paymentAmount')).toBe(true);
    draft.details.advances[0]!.amount = '1000.01';
    expect(problems(draft).some(problem => problem.field === 'advance-demo-advance-paper')).toBe(true);
    draft.supplier = 'demo-services';
    expect(problems(draft).some(problem => problem.field === 'advances')).toBe(true);
    draft.details.termsDays = '1.5'; expect(purchaseDueDate(draft)).toBeNull();
  });
  it('does not relabel a different method account or accept duplicate advance selections', () => {
    const draft = purchaseExample(today);
    draft.details.payment = { amount: '100', method: 'CASH', account: 'demo-bank', reference: '' };
    draft.details.advances.push({ ...draft.details.advances[0]! });
    expect(problems(draft).some(problem => problem.field === 'paymentAccount')).toBe(true);
    expect(problems(draft).some(problem => problem.field === 'advances')).toBe(true);
  });
});
describe('Purchase receipt and tracking fixtures', () => {
  it('allows a six-of-ten partial receipt without receiving again', () => {
    const draft = purchaseScenario('receipt', today);
    expect(problems(draft)).toEqual([]);
    expect(purchaseWorkspacePreview(draft).total).toBe(7080000n);
    expect(draft.details.receiptIntent).toBe('REFERENCE');
    expect(policy.details.receipts[0]!.remaining).toBe('10');
  });
  it('sums duplicate-row slices against one source and rejects mismatched suppliers and units', () => {
    const draft = purchaseWorkspaceReducer(purchaseScenario('receipt', today), { type: 'duplicate', key: 'p1' });
    draft.details.receipts.push({ lineKey: 'p2', sourceId: 'demo-grn-notebooks', quantity: '6' });
    expect(problems(draft).some(problem => problem.field === 'receipt-allocation')).toBe(true);
    draft.supplier = 'demo-services';
    expect(problems(draft).some(problem => problem.field === 'receipt-p1')).toBe(true);
    draft.supplier = 'demo-paper'; draft.lines[0]!.unit = 'each';
    expect(problems(draft).some(problem => problem.field === 'receipt-p1')).toBe(true);
  });
  it('requires complete tracking only for directly received tracked items', () => {
    const draft = purchaseScenario('tracking', today);
    expect(problems(draft).some(problem => problem.field === 'batch-p1')).toBe(true);
    expect(problems(draft).some(problem => problem.field === 'serials-p2')).toBe(true);
    draft.details.tracking = { p1: { location: 'demo-store', batch: 'INK-OCT26', expiry: '2027-10-31', serials: '' }, p2: { location: 'demo-store', batch: '', expiry: '', serials: 'SCAN-1\nSCAN-2' } };
    expect(problems(draft)).toEqual([]);
    draft.details.tracking.p2!.serials = 'SCAN-1\nSCAN-1';
    expect(problems(draft).some(problem => problem.message.includes('unique'))).toBe(true);
    draft.details.receiptIntent = 'DEFERRED';
    expect(problems(draft)).toEqual([]);
    expect(draft.details.tracking.p2!.serials).toBe('SCAN-1\nSCAN-1');
  });
  it('rejects the same item serial across two directly received rows', () => {
    const draft = purchaseScenario('tracking', today);
    draft.lines = [{ ...draft.lines[1]!, key: 'p1' }, { ...draft.lines[1]!, key: 'p2' }];
    draft.details.tracking = { p1: { location: 'demo-store', batch: '', expiry: '', serials: 'S-1\nS-2' }, p2: { location: 'demo-store', batch: '', expiry: '', serials: 'S-1\nS-3' } };
    expect(problems(draft).some(problem => problem.message.includes('another line'))).toBe(true);
  });
  it('keeps custom typed fields descriptive and out of calculations', () => {
    const draft = purchaseExample(today);
    draft.details.custom = { cf_purchase_project: 'Office', cf_purchase_parcels: '2', cf_discount: '999999' };
    const normalized = normalizePurchaseCustom(draft.details, policy.details);
    expect(normalized.custom.cf_purchase_parcels).toBe(2);
    expect(purchaseWorkspacePreview({ ...draft, details: normalized }).total).toBe(57230000n);
    draft.details.custom.cf_purchase_parcels = '1.2';
    expect(problems(draft).some(problem => problem.field === 'cf_purchase_parcels')).toBe(true);
  });
  it('refuses a presentation total outside DECIMAL(19,4) without rounding it down', () => {
    const draft = purchaseScenario('untaxed', today);
    draft.lines = [{ ...draft.lines[0]!, amount: '900000000000000' }, { ...draft.lines[0]!, key: 'p2', amount: '900000000000000' }];
    draft.evidence!.signature = purchaseEvidenceSignature(draft);
    expect(purchaseWorkspacePreview(draft).total).toBeNull();
  });
});
describe('local attachment safety and failure states', () => {
  it('checks size, extension, MIME and header without a transport', async () => {
    const png = new File([new Uint8Array([137, 80, 78, 71, 13, 10, 26, 10])], 'invoice.png', { type: 'image/png' });
    expect(await checkPurchaseAttachment(png, 1024)).toBeNull();
    expect(await checkPurchaseAttachment(png, 4)).toMatch(/size limit/);
    expect(await checkPurchaseAttachment(new File(['<svg/>'], 'bill.svg', { type: 'image/svg+xml' }), 1024)).toMatch(/matching file type/);
    expect(await checkPurchaseAttachment(new File(['<script>test</script>'], 'bill.png', { type: 'image/png' }), 1024)).toMatch(/does not match/);
    expect(await checkPurchaseAttachment(new File(['%PDF-1.7'], 'bill.pdf', { type: 'application/pdf' }), 1024)).toBeNull();
    expect(await checkPurchaseAttachment(new File([], 'empty.pdf', { type: 'application/pdf' }), 1024)).toMatch(/non-empty/);
  });
});
