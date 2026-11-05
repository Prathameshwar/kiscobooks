import { PURCHASE_DEMO_POLICY, purchaseWorkspacePreview, purchaseWorkspaceProblems, type PurchaseWorkspaceDraft, type PurchaseWorkspacePolicy } from './purchase-workspace';
import { purchaseScenario } from './purchase-workspace-scenarios';
import type { ServiceReader } from './service-resource';
import type { ServiceRequest } from './service-call';

/** UI-only contract. Never pass these commands to a service client. */
export type PurchaseContext = { company: string; year: string };
export type PurchaseStatus = 'DRAFT' | 'SUBMITTED' | 'APPROVED' | 'REJECTED';
export type PurchaseWorkflowRecord = {
  context: PurchaseContext; id: string; revision: number; status: PurchaseStatus;
  draft: PurchaseWorkspaceDraft; rejection: string | null;
  correctionOf: { id: string; revision: number; reason: string } | null;
  snapshot: { supplier: { id: string; label: string }; subjects: { id: string; label: string }[]; receipts: { id: string; label: string }[] };
};
export type PurchaseWorkflowAction = 'SAVE' | 'SUBMIT' | 'CORRECT';
export type PurchaseWorkflowCommand = {
  context: PurchaseContext; action: PurchaseWorkflowAction; id: string | null; revision: number | null;
  draft: PurchaseWorkspaceDraft; reason: string;
};
export type PurchaseDemoOutcome = 'SUCCESS' | 'VALIDATION' | 'FAILURE' | 'STALE' | 'UNCERTAIN' | 'REFUSED';
export const PURCHASE_DEMO_OUTCOMES = [
  { value: 'SUCCESS', label: 'Normal completion' }, { value: 'VALIDATION', label: 'Validation refusal' },
  { value: 'FAILURE', label: 'Known failure · safe to edit' }, { value: 'STALE', label: 'Stale draft revision' },
  { value: 'UNCERTAIN', label: 'Response lost · recover same command' }, { value: 'REFUSED', label: 'Permission refused' },
];
export const PURCHASE_WORKFLOW_EXAMPLES = [
  { value: 'NEW', label: 'New bill' }, { value: 'DRAFT', label: 'Saved draft · resume editing' },
  { value: 'SUBMITTED', label: 'Submitted · review only' }, { value: 'APPROVED', label: 'Approved · review only' },
  { value: 'REJECTED', label: 'Rejected · correction required' }, { value: 'MASTER_CHANGED', label: 'Draft · master names changed' },
];
export function samePurchaseContext(a: PurchaseContext, b: PurchaseContext): boolean { return a.company === b.company && a.year === b.year; }
export function purchaseWorkflowPath(context: PurchaseContext): string { return '/purchase-ui/' + encodeURIComponent(context.company) + '/' + encodeURIComponent(context.year); }

/** Files are immutable and stay in memory; copy every mutable draft collection. */
export function copyPurchaseDraft(draft: PurchaseWorkspaceDraft): PurchaseWorkspaceDraft {
  const copy = JSON.parse(JSON.stringify({ ...draft, details: { ...draft.details, attachments: [] } })) as PurchaseWorkspaceDraft;
  copy.details.attachments = draft.details.attachments.map(file => ({ ...file }));
  return copy;
}
export function copyPurchaseRecord(record: PurchaseWorkflowRecord): PurchaseWorkflowRecord {
  return { ...record, context: { ...record.context }, draft: copyPurchaseDraft(record.draft),
    correctionOf: record.correctionOf ? { ...record.correctionOf } : null,
    snapshot: { supplier: { ...record.snapshot.supplier }, subjects: record.snapshot.subjects.map(subject => ({ ...subject })), receipts: record.snapshot.receipts.map(receipt => ({ ...receipt })) } };
}
function snapshots(draft: PurchaseWorkspaceDraft, policy: PurchaseWorkspacePolicy, previous?: PurchaseWorkflowRecord['snapshot']): PurchaseWorkflowRecord['snapshot'] {
  return { supplier: previous?.supplier.id === draft.supplier ? { ...previous.supplier } : { id: draft.supplier, label: policy.suppliers.find(supplier => supplier.id === draft.supplier)?.label ?? 'Unknown example supplier' },
    subjects: draft.lines.filter(line => line.subject).map(line => ({ id: line.subject, label: line.label })),
    receipts: draft.details.receipts.map(receipt => ({ id: receipt.sourceId, label: previous?.receipts.find(source => source.id === receipt.sourceId)?.label ?? policy.details.receipts.find(source => source.id === receipt.sourceId)?.label ?? 'Unavailable example receipt' })) };
}
export function purchaseMasterChanges(record: PurchaseWorkflowRecord, policy: PurchaseWorkspacePolicy): string[] {
  const result: string[] = [];
  const supplier = policy.suppliers.find(item => item.id === record.snapshot.supplier.id);
  if (!supplier || supplier.label !== record.snapshot.supplier.label) result.push(`Supplier: saved “${record.snapshot.supplier.label}”; current ${supplier ? '“' + supplier.label + '”' : 'unavailable'}.`);
  for (const subject of record.snapshot.subjects) {
    const current = policy.subjects.find(item => item.id === subject.id);
    if (!current || current.label !== subject.label) result.push(`Line item: saved “${subject.label}”; current ${current ? '“' + current.label + '”' : 'unavailable'}.`);
  }
  for (const receipt of record.snapshot.receipts) {
    const current = policy.details.receipts.find(item => item.id === receipt.id);
    if (!current || current.label !== receipt.label) result.push(`Receipt: saved “${receipt.label}”; current ${current ? '“' + current.label + '”' : 'unavailable'}.`);
  }
  return [...new Set(result)];
}
export function purchaseWorkflowExample(name: string, context: PurchaseContext, today: string): PurchaseWorkflowRecord | null {
  if (name === 'NEW') return null;
  const draft = purchaseScenario(name === 'MASTER_CHANGED' ? 'receipt' : 'goods', today);
  const record: PurchaseWorkflowRecord = { context: { ...context }, id: 'DEMO-' + name, revision: 3,
    status: ['SUBMITTED', 'APPROVED', 'REJECTED'].includes(name) ? name as PurchaseStatus : 'DRAFT',
    draft, rejection: name === 'REJECTED' ? 'Supplier invoice number does not match the supporting bill. Correct it and submit a new review.' : null,
    correctionOf: null, snapshot: snapshots(draft, PURCHASE_DEMO_POLICY) };
  if (name === 'MASTER_CHANGED') {
    record.snapshot.supplier.label = 'Paper & Co. · original trading name';
    record.snapshot.subjects[0]!.label = 'Notebooks · saved item description';
    record.draft.lines[0]!.label = record.snapshot.subjects[0]!.label;
    record.snapshot.receipts[0]!.label = 'GRN-104 · original receipt label';
  }
  return record;
}
export function makePurchaseCommand(context: PurchaseContext, record: PurchaseWorkflowRecord | null, draft: PurchaseWorkspaceDraft, action: PurchaseWorkflowAction, reason = ''): ServiceRequest {
  const body: PurchaseWorkflowCommand = { context: { ...context }, id: record?.id ?? null, revision: record?.revision ?? null, action, draft: copyPurchaseDraft(draft), reason: reason.trim() };
  return { path: purchaseWorkflowPath(context) + '/commands', method: 'POST', body };
}

/** Verify the result before allowing it to replace this company's visible revision. */
export function assertPurchaseWorkflowResult(value: PurchaseWorkflowRecord, context: PurchaseContext, command: PurchaseWorkflowCommand) {
  const expected = command.action === 'SUBMIT' ? 'SUBMITTED' : 'DRAFT';
  const valid = value && samePurchaseContext(value.context, context) && typeof value.id === 'string' && value.id.startsWith('DEMO-')
    && Number.isSafeInteger(value.revision) && value.revision > 0 && value.status === expected
    && (command.action === 'CORRECT' ? value.id !== command.id && value.correctionOf?.id === command.id && value.correctionOf.revision === command.revision && value.correctionOf.reason === command.reason
      : !command.id || value.id === command.id)
    && value.draft && JSON.stringify(value.draft) === JSON.stringify(command.draft)
    && (command.id && command.action !== 'CORRECT' ? value.revision === command.revision! + 1 : value.revision === 1);
  if (!valid) throw { status: 502, message: 'The demo response could not be verified. Recover the same command before continuing.' };
}

export type PurchaseMemoryAdapter = {
  request: ServiceReader; seed: (record: PurchaseWorkflowRecord) => void;
  latest: (id: string) => Promise<PurchaseWorkflowRecord>;
  setOutcome: (outcome: PurchaseDemoOutcome) => void;
  discard: () => void;
};
/** Bounded per-workspace memory, with no fetch, storage, timers or financial effects. */
export function createPurchaseMemoryAdapter(context: PurchaseContext, policy = PURCHASE_DEMO_POLICY): PurchaseMemoryAdapter {
  const records = new Map<string, PurchaseWorkflowRecord>();
  const receipts = new Map<string, { signature: string; value: PurchaseWorkflowRecord }>();
  let next = 1, outcome: PurchaseDemoOutcome = 'SUCCESS';
  const latest = async (id: string) => { const record = records.get(id); if (!record) throw { status: 404, message: 'This demo record is no longer available in this tab.' }; return copyPurchaseRecord(record); };
  const request: ServiceReader = async <T,>(request: ServiceRequest): Promise<T> => {
    const body = request.body as PurchaseWorkflowCommand;
    if (request.path !== purchaseWorkflowPath(context) + '/commands' || !body || !samePurchaseContext(body.context, context)) throw { status: 403, message: 'The demo command belongs to another company or financial year.' };
    if (!request.key || request.method !== 'POST') throw { status: 400, message: 'A demo command key and POST method are required.' };
    const signature = JSON.stringify(body), prior = receipts.get(request.key);
    if (prior) {
      if (prior.signature !== signature) throw { status: 409, message: 'A command key cannot be reused for different entries.' };
      return copyPurchaseRecord(prior.value) as T;
    }
    const selected = outcome; outcome = 'SUCCESS';
    if (selected === 'VALIDATION') throw { status: 422, message: 'The example validator refused the supplier invoice reference. Your entries are retained.', fields: { invoice: 'Check the invoice reference against the supplier bill.' } };
    if (selected === 'FAILURE') throw { status: 400, message: 'The demo command failed before any change. Your entries are retained; edit or retry.' };
    if (selected === 'REFUSED') throw { status: 403, message: 'The example denied write access. Your entries are retained for review.' };
    const original = body.id ? records.get(body.id) : undefined;
    if (body.id && !original) throw { status: 404, message: 'The original demo draft is unavailable. Keep your entries or start a separate demo bill.' };
    if (selected === 'STALE' && original) {
      const changed = copyPurchaseRecord(original); changed.revision += 1; changed.draft.details.notes = 'Another example editor updated this draft.'; records.set(changed.id, changed);
    }
    const current = body.id ? records.get(body.id) : undefined;
    if (current && current.revision !== body.revision) throw { status: 409, message: 'A newer demo revision exists. Review it before replacing your entries.' };
    if (!['SAVE', 'SUBMIT', 'CORRECT'].includes(body.action)) throw { status: 422, message: 'Unsupported demo transition.' };
    if (body.action === 'CORRECT' ? current?.status !== 'REJECTED' || !body.reason : current && current.status !== 'DRAFT') throw { status: 409, message: 'This demo revision does not allow that action.' };
    if (body.action === 'SUBMIT' && !current) throw { status: 422, message: 'Save this demo draft before review and submission.' };
    if (body.action !== 'SAVE' && current && JSON.stringify(body.draft) !== JSON.stringify(current.draft)) throw { status: 409, message: 'This action must use the exact saved revision. Save and review changes first.' };
    const problems = purchaseWorkspaceProblems(body.draft, policy);
    if (body.action !== 'CORRECT' && problems.length) throw { status: 422, message: problems[0]!.message, fields: { [problems[0]!.field]: problems[0]!.message } };
    if (body.action === 'SUBMIT' && purchaseWorkspacePreview(body.draft).total === null) throw { status: 422, message: 'Submission needs complete supplied calculation evidence. Keep this as a demo draft.' };
    const correction = body.action === 'CORRECT';
    const record: PurchaseWorkflowRecord = { context: { ...context }, id: correction || !current ? 'DEMO-LOCAL-' + next++ : current.id,
      revision: correction || !current ? 1 : current.revision + 1,
      status: body.action === 'SUBMIT' ? 'SUBMITTED' : 'DRAFT', draft: copyPurchaseDraft(body.draft), rejection: null,
      correctionOf: correction ? { id: current!.id, revision: current!.revision, reason: body.reason } : current?.correctionOf ?? null,
      snapshot: snapshots(body.draft, policy, current?.snapshot) };
    records.set(record.id, copyPurchaseRecord(record)); receipts.set(request.key, { signature, value: copyPurchaseRecord(record) });
    if (selected === 'UNCERTAIN') throw { status: 503, message: 'The demo response was lost. Its result is unconfirmed; retry the same command.' };
    return copyPurchaseRecord(record) as T;
  };
  return { request, latest, discard: () => { records.clear(); receipts.clear(); }, setOutcome: value => { outcome = value; }, seed: record => {
    if (!samePurchaseContext(record.context, context)) throw Error('Cannot seed another company or year.'); records.set(record.id, copyPurchaseRecord(record));
  } };
}

