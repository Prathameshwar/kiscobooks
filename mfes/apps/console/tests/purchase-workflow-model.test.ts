import { describe, expect, it } from 'vitest';
import { PURCHASE_DEMO_POLICY, purchaseExample } from '../app/lib/purchase-workspace';
import { assertPurchaseWorkflowResult, copyPurchaseDraft, createPurchaseMemoryAdapter, makePurchaseCommand, purchaseMasterChanges, purchaseWorkflowExample, type PurchaseWorkflowCommand, type PurchaseWorkflowRecord } from '../app/lib/purchase-workflow';
const context = { company: 'company-a', year: '2026' }, today = '2026-10-31';
const withKey = (request: ReturnType<typeof makePurchaseCommand>, key = 'test-key') => ({ ...request, key });

describe('Purchase in-memory lifecycle contract', () => {
  it('creates and revises one demo record with exact strings and isolated copies', async () => {
    const adapter = createPurchaseMemoryAdapter(context), draft = purchaseExample(today);
    const request = withKey(makePurchaseCommand(context, null, draft, 'SAVE'));
    const first = await adapter.request<PurchaseWorkflowRecord>(request);
    expect(first).toMatchObject({ revision: 1, status: 'DRAFT', context });
    expect(first.draft.lines[0]!.rate).toBe('125');
    first.draft.lines[0]!.rate = '999';
    expect((await adapter.latest(first.id)).draft.lines[0]!.rate).toBe('125');
    draft.invoice = 'PC-NEW';
    const second = await adapter.request<PurchaseWorkflowRecord>(withKey(makePurchaseCommand(context, first, draft, 'SAVE'), 'key-2'));
    expect(second).toMatchObject({ id: first.id, revision: 2 });
    expect(second.draft.invoice).toBe('PC-NEW');
  });
  it('recovers an uncertain create once with the identical body/key', async () => {
    const adapter = createPurchaseMemoryAdapter(context), draft = purchaseExample(today);
    adapter.setOutcome('UNCERTAIN'); const command = withKey(makePurchaseCommand(context, null, draft, 'SAVE'));
    await expect(adapter.request(command)).rejects.toMatchObject({ status: 503 });
    const result = await adapter.request<PurchaseWorkflowRecord>(command);
    expect(result).toMatchObject({ id: 'DEMO-LOCAL-1', revision: 1 });
    expect(await adapter.request(command)).toEqual(result);
    const changed = withKey(makePurchaseCommand(context, null, { ...draft, invoice: 'OTHER' }, 'SAVE'));
    await expect(adapter.request(changed)).rejects.toMatchObject({ status: 409 });
  });
  it('keeps known refusals atomic and accepts a later safe command', async () => {
    for (const outcome of ['VALIDATION', 'FAILURE', 'REFUSED'] as const) {
      const adapter = createPurchaseMemoryAdapter(context); adapter.setOutcome(outcome);
      await expect(adapter.request(withKey(makePurchaseCommand(context, null, purchaseExample(today), 'SAVE')))).rejects.toMatchObject({ status: outcome === 'VALIDATION' ? 422 : outcome === 'REFUSED' ? 403 : 400 });
      await expect(adapter.latest('DEMO-LOCAL-1')).rejects.toMatchObject({ status: 404 });
    }
  });
  it('requires an eligible current draft before submission and freezes its revision', async () => {
    const adapter = createPurchaseMemoryAdapter(context), record = purchaseWorkflowExample('DRAFT', context, today)!; adapter.seed(record);
    const submitted = await adapter.request<PurchaseWorkflowRecord>(withKey(makePurchaseCommand(context, record, record.draft, 'SUBMIT')));
    expect(submitted).toMatchObject({ status: 'SUBMITTED', revision: 4 });
    await expect(adapter.request(withKey(makePurchaseCommand(context, submitted, submitted.draft, 'SAVE'), 'another'))).rejects.toMatchObject({ status: 409 });
    const fresh = createPurchaseMemoryAdapter(context);
    await expect(fresh.request(withKey(makePurchaseCommand(context, null, record.draft, 'SUBMIT')))).rejects.toMatchObject({ status: 422 });
  });
  it('creates a separate correction and preserves the rejected original and reason', async () => {
    const adapter = createPurchaseMemoryAdapter(context), original = purchaseWorkflowExample('REJECTED', context, today)!; adapter.seed(original);
    await expect(adapter.request(withKey(makePurchaseCommand(context, original, original.draft, 'CORRECT')))).rejects.toMatchObject({ status: 409 });
    const corrected = await adapter.request<PurchaseWorkflowRecord>(withKey(makePurchaseCommand(context, original, original.draft, 'CORRECT', 'Correct invoice reference'), 'correction'));
    expect(corrected.id).not.toBe(original.id);
    expect(corrected).toMatchObject({ status: 'DRAFT', revision: 1, correctionOf: { id: original.id, revision: 3, reason: 'Correct invoice reference' } });
    expect(await adapter.latest(original.id)).toEqual(original);
  });
  it.each(['SUBMIT', 'CORRECT'] as const)('refuses %s when its body differs from the saved revision', async action => {
    const adapter = createPurchaseMemoryAdapter(context), original = purchaseWorkflowExample(action === 'CORRECT' ? 'REJECTED' : 'DRAFT', context, today)!;
    adapter.seed(original);
    const changed = { ...original.draft, invoice: 'UNREVIEWED' };
    await expect(adapter.request(withKey(makePurchaseCommand(context, original, changed, action, 'Correct reference')))).rejects.toMatchObject({ status: 409 });
    expect(await adapter.latest(original.id)).toEqual(original);
  });
  it('refreshes a changed supplier snapshot while retaining unchanged historical receipt labels', async () => {
    const adapter = createPurchaseMemoryAdapter(context), original = purchaseWorkflowExample('MASTER_CHANGED', context, today)!;
    adapter.seed(original);
    const kept = await adapter.request<PurchaseWorkflowRecord>(withKey(makePurchaseCommand(context, original, original.draft, 'SAVE'), 'unchanged'));
    expect(kept.snapshot).toEqual(original.snapshot);
    const draft = copyPurchaseDraft(original.draft);
    draft.supplier = 'demo-services';
    draft.payable = 'demo-services-inr';
    draft.details.receipts = [];
    draft.details.receiptIntent = 'DEFERRED';
    draft.details.advances = [];
    const saved = await adapter.request<PurchaseWorkflowRecord>(withKey(makePurchaseCommand(context, kept, draft, 'SAVE')));
    expect(saved.snapshot.supplier).toEqual({ id: draft.supplier, label: PURCHASE_DEMO_POLICY.suppliers.find(supplier => supplier.id === draft.supplier)!.label });
    expect(saved.snapshot.receipts).toEqual([]);
    expect(saved.snapshot.subjects[0]!.label).toBe(original.snapshot.subjects[0]!.label);
  });
  it('refuses stale writes without replacing the newer revision', async () => {
    const adapter = createPurchaseMemoryAdapter(context), original = purchaseWorkflowExample('DRAFT', context, today)!; adapter.seed(original);
    adapter.setOutcome('STALE');
    const changed = { ...original.draft, invoice: 'MY-EDIT' };
    await expect(adapter.request(withKey(makePurchaseCommand(context, original, changed, 'SAVE')))).rejects.toMatchObject({ status: 409 });
    const latest = await adapter.latest(original.id);
    expect(latest.revision).toBe(4); expect(latest.draft.invoice).toBe(original.draft.invoice);
    expect(latest.draft.details.notes).toMatch(/Another example editor/);
  });
  it('denies commands and seeded records from another company or financial year', async () => {
    const adapter = createPurchaseMemoryAdapter(context);
    for (const other of [{ ...context, company: 'company-b' }, { ...context, year: '2027' }]) {
      await expect(adapter.request(withKey(makePurchaseCommand(other, null, purchaseExample(today), 'SAVE')))).rejects.toMatchObject({ status: 403 });
      expect(() => adapter.seed(purchaseWorkflowExample('DRAFT', other, today)!)).toThrow(/another company or year/);
    }
  });
  it('compares current master names without mutating stored supplier/item/receipt snapshots', () => {
    const record = purchaseWorkflowExample('MASTER_CHANGED', context, today)!, before = JSON.stringify(record);
    expect(purchaseMasterChanges(record, PURCHASE_DEMO_POLICY)).toHaveLength(3);
    expect(JSON.stringify(record)).toBe(before);
  });
  it('validates response scope, revision, identity, status and exact draft before replacing inputs', async () => {
    const adapter = createPurchaseMemoryAdapter(context), request = withKey(makePurchaseCommand(context, null, purchaseExample(today), 'SAVE'));
    const result = await adapter.request<PurchaseWorkflowRecord>(request), body = request.body as PurchaseWorkflowCommand;
    expect(() => assertPurchaseWorkflowResult(result, context, body)).not.toThrow();
    for (const changed of [{ ...result, context: { ...context, company: 'other' } }, { ...result, status: 'APPROVED' as const }, { ...result, draft: { ...result.draft, invoice: 'OTHER' } }, { ...result, revision: 0 }, { ...result, revision: 7 }]) {
      expect(() => assertPurchaseWorkflowResult(changed, context, body)).toThrow();
    }
  });
  it('copies local immutable files and discards all tab records explicitly', async () => {
    const draft = purchaseExample(today), file = new File(['%PDF-'], 'bill.pdf', { type: 'application/pdf' });
    draft.details.attachments = [{ id: 'f1', file, name: file.name, size: file.size, status: 'ready' }];
    const copy = copyPurchaseDraft(draft); expect(copy.details.attachments[0]!.file).toBe(file);
    expect(copy.details.attachments[0]).not.toBe(draft.details.attachments[0]);
    const adapter = createPurchaseMemoryAdapter(context), record = await adapter.request<PurchaseWorkflowRecord>(withKey(makePurchaseCommand(context, null, draft, 'SAVE')));
    adapter.discard(); await expect(adapter.latest(record.id)).rejects.toMatchObject({ status: 404 });
  });
});
