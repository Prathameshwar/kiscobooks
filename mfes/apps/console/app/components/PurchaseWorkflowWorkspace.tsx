'use client';

import { useCallback, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { Badge, Button, DisplayConfigProvider, Modal, Notice, Select, TextField, useDisplayConfig, type SearchSelectLoader } from '@janso/ui';
import { PurchaseCostRestricted, PurchaseWorkspace } from './PurchaseWorkspace';
import { PurchaseWorkflowReview } from './PurchaseWorkflowReview';
import { useServiceCommand } from '../lib/service-resource';
import { useDraftNavigation } from '../lib/use-draft-navigation';
import { PURCHASE_DEMO_POLICY, newPurchaseWorkspace, purchaseWorkspacePreview, purchaseWorkspaceReducer, type PurchaseWorkspaceAction, type PurchaseWorkspaceDraft, type PurchaseWorkspacePolicy } from '../lib/purchase-workspace';
import { PURCHASE_DEMO_OUTCOMES, PURCHASE_WORKFLOW_EXAMPLES, assertPurchaseWorkflowResult, copyPurchaseDraft, copyPurchaseRecord, createPurchaseMemoryAdapter, makePurchaseCommand, purchaseMasterChanges, purchaseWorkflowExample, samePurchaseContext,
  type PurchaseContext, type PurchaseDemoOutcome, type PurchaseMemoryAdapter, type PurchaseWorkflowAction, type PurchaseWorkflowCommand, type PurchaseWorkflowRecord } from '../lib/purchase-workflow';
import type { ServiceRequest } from '../lib/service-call';

export type PurchaseWorkflowPermissions = { create: boolean; edit: boolean; submit: boolean };
type Props = {
  context: PurchaseContext; today: string; permissions: PurchaseWorkflowPermissions; policy?: PurchaseWorkspacePolicy;
  initialExample?: string; initialDraft?: PurchaseWorkspaceDraft;
  supplierLookup?: SearchSelectLoader;
  createAdapter?: (context: PurchaseContext, policy: PurchaseWorkspacePolicy) => PurchaseMemoryAdapter;
};
/** A company/year change unmounts every draft, pending response, adapter and local file. */
export function PurchaseWorkflowWorkspace(props: Props) {
  const display = useDisplayConfig(), policy = props.policy ?? PURCHASE_DEMO_POLICY;
  if (policy.costAccess === 'DENIED') return <PurchaseCostRestricted />;
  return <DisplayConfigProvider config={{ ...display, currency: policy.currency, currencySymbol: policy.currencySymbol }}>
    <PurchaseWorkflowSession key={JSON.stringify(props.context)} {...props} policy={policy} />
  </DisplayConfigProvider>;
}

function PurchaseWorkflowSession({ context, today, permissions, policy = PURCHASE_DEMO_POLICY, initialExample = 'NEW', initialDraft, createAdapter = createPurchaseMemoryAdapter, supplierLookup }: Props) {
  const [adapter] = useState(() => createAdapter(context, policy));
  const [initial] = useState(() => {
    const record = purchaseWorkflowExample(initialExample, context, today);
    if (record) adapter.seed(record);
    return record;
  });
  const [record, setRecord] = useState(initial);
  const [draft, setDraft] = useState(() => initial ? copyPurchaseDraft(initial.draft) : initialDraft ?? newPurchaseWorkspace(today));
  const [baseline, setBaseline] = useState(() => JSON.stringify(draft));
  const [archive, setArchive] = useState<PurchaseWorkflowRecord[]>([]);
  const [example, setExample] = useState(initialExample);
  const [resume, setResume] = useState('');
  const [outcome, setOutcome] = useState<PurchaseDemoOutcome>('SUCCESS');
  const [transient, setTransient] = useState(false);
  const [generation, setGeneration] = useState(0);
  const [review, setReview] = useState(false);
  const [correct, setCorrect] = useState(false);
  const [reason, setReason] = useState('');
  const [reasonError, setReasonError] = useState(false);
  const [latest, setLatest] = useState<PurchaseWorkflowRecord | null>(null);
  const [loadingLatest, setLoadingLatest] = useState(false);
  const [readError, setReadError] = useState<string | null>(null);
  const [confirmation, setConfirmation] = useState<{ title: string; proceed: () => void } | null>(null);
  const [blockedNotice, setBlockedNotice] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const command = useServiceCommand(adapter.request, 'Purchase demo adapter');
  const retained = useRef<ServiceRequest | null>(null), busy = useRef(false), alive = useRef(true);
  useLayoutEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  const dirty = JSON.stringify(draft) !== baseline;
  const conflict = command.failure?.status === 409 && !command.uncertain;
  const refused = command.failure?.status === 403;
  const locked = command.pending || command.uncertain || loadingLatest;
  useLayoutEffect(() => { if (!locked && !transient) setBlockedNotice(false); }, [locked, transient]);
  const editable = !locked && !conflict && !refused && (!record ? permissions.create : record.status === 'DRAFT' && permissions.edit);
  const atRisk = dirty || archive.length > 0;
  const ask = (title: string, proceed: () => void) => {
    if (locked || transient) { setBlockedNotice(true); return; }
    if (atRisk) setConfirmation({ title, proceed }); else proceed();
  };
  useDraftNavigation({ atRisk, blocked: locked || transient, requestLeave: proceed => setConfirmation({ title: 'Leave purchase preview?', proceed }), onBlocked: () => setBlockedNotice(true) });
  const onTransientChange = useCallback((value: boolean) => setTransient(value), []);
  const dispatch = (action: PurchaseWorkspaceAction) => {
    if (!editable || busy.current) return;
    command.clear(); setMessage(null); setDraft(current => purchaseWorkspaceReducer(current, action));
  };
  const showRecord = (next: PurchaseWorkflowRecord | null) => {
    if (next && !samePurchaseContext(next.context, context)) { setReadError('This example belongs to another company or financial year.'); return; }
    command.clear(); retained.current = null; setRecord(next ? copyPurchaseRecord(next) : null);
    const nextDraft = next ? copyPurchaseDraft(next.draft) : newPurchaseWorkspace(today);
    setDraft(nextDraft); setBaseline(JSON.stringify(nextDraft)); setGeneration(value => value + 1);
    setReview(false); setCorrect(false); setReason(''); setLatest(null); setReadError(null); setMessage(null); setBlockedNotice(false);
  };
  const perform = async (action: PurchaseWorkflowAction, retry = false) => {
    if (busy.current || !retry && (locked || conflict || refused)) return;
    if (!retry && (action === 'CORRECT' ? !permissions.create || !permissions.edit || record?.status !== 'REJECTED' : action === 'SUBMIT' ? !permissions.submit || !record || record.status !== 'DRAFT' || dirty || transient : !editable || transient)) return;
    const request = retry ? retained.current : makePurchaseCommand(context, record, draft, action, reason);
    if (!request) return;
    retained.current = request; busy.current = true;
    if (!retry) adapter.setOutcome(outcome);
    const result = await command.execute<PurchaseWorkflowRecord>(request, value => assertPurchaseWorkflowResult(value, context, request.body as PurchaseWorkflowCommand));
    busy.current = false;
    if (!alive.current) return;
    if (!result) { setReview(false); setCorrect(false); return; }
    setArchive(current => [...current.filter(entry => entry.id !== result.id), copyPurchaseRecord(result)]);
    setRecord(result); setDraft(copyPurchaseDraft(result.draft)); setBaseline(JSON.stringify(result.draft));
    retained.current = null; setReview(false); setCorrect(false); setReason(''); setBlockedNotice(false);
    setMessage(result.status === 'SUBMITTED' ? 'Demo submitted for review in this tab. Nothing has been approved or posted.' : action === 'CORRECT' ? 'A separate correction draft is ready. The rejected original is unchanged.' : 'Demo draft kept in this tab. It is not saved to a service; leaving or reloading loses it.');
  };
  const readLatest = async () => {
    if (!record || locked || busy.current) return;
    setLoadingLatest(true); setReadError(null);
    try {
      const value = await adapter.latest(record.id);
      if (alive.current) {
        if (!samePurchaseContext(value.context, context) || value.id !== record.id) throw Error('scope');
        setLatest(value);
      }
    } catch { if (alive.current) setReadError('The latest demo revision could not be verified. Your current entries are retained. Retry loading.'); }
    finally { if (alive.current) setLoadingLatest(false); }
  };
  const masterChanges = record ? purchaseMasterChanges(record, policy) : [];
  // Keep saved labels in selected controls; comparisons above use today's unchanged masters.
  const displayPolicy = useMemo(() => !record ? policy : ({ ...policy,
    suppliers: policy.suppliers.map(supplier => supplier.id === record.snapshot.supplier.id ? { ...supplier, label: record.snapshot.supplier.label } : supplier),
    details: { ...policy.details, receipts: policy.details.receipts.map(receipt => {
      const saved = record.snapshot.receipts.find(source => source.id === receipt.id);
      return saved ? { ...receipt, label: saved.label } : receipt;
    }) },
  }), [record, policy]);
  const status = record?.status ?? 'NEW';
  const title = status === 'NEW' ? 'New purchase' : status === 'DRAFT' ? record?.correctionOf ? 'Correct purchase draft' : 'Edit purchase draft' : 'Review purchase bill';
  const banner = (examples: ReactNode) => <div className="janso-entry-workflow">
    <section className="janso-entry-workflow__bar" aria-label="Purchase workflow">
      <div><Badge tone={status === 'REJECTED' ? 'danger' : status === 'APPROVED' ? 'success' : 'info'}>{status === 'NEW' ? 'New · demo' : status.charAt(0) + status.slice(1).toLowerCase() + ' · demo'}</Badge>
        <p className="janso-entry-workspace__caption">{record ? `${record.id} · revision ${record.revision}` : 'No demo record yet'} · {dirty || transient ? 'Edits to save' : 'No unapplied edits'}</p></div>
      <a className="janso-link" href="/vouchers">Back to vouchers</a>
    </section>
    <details className="janso-entry-workflow__examples"><summary>Explore workflow examples</summary>
      {examples}
      <div className="janso-form-grid">
        <Select label="Workflow example" value={example} options={PURCHASE_WORKFLOW_EXAMPLES} disabled={locked} onChange={setExample} />
        <Select label="Next demo command outcome" value={outcome} options={PURCHASE_DEMO_OUTCOMES.map(option => ({ ...option, disabled: option.value === 'STALE' && !record }))} disabled={locked} onChange={value => setOutcome(value as PurchaseDemoOutcome)} />
      </div>
      <div className="janso-entry-workflow__buttons"><Button type="button" variant="ghost" disabled={locked} onClick={() => ask('Replace the current purchase example?', () => {
        const next = purchaseWorkflowExample(example, context, today); if (next) adapter.seed(next); showRecord(next);
      })}>Open workflow example</Button>
        {archive.length ? <><Select label="Drafts in this tab" value={resume} disabled={locked} options={[{ value: '', label: 'Choose a demo record' }, ...archive.map(entry => ({ value: entry.id, label: `${entry.draft.invoice} · ${entry.status.toLowerCase()} · r${entry.revision}` }))]} onChange={setResume} />
          <Button type="button" variant="ghost" disabled={locked || !resume} onClick={() => ask('Open another demo record?', () => { const next = archive.find(entry => entry.id === resume); if (next) showRecord(next); })}>Resume selected demo</Button></> : null}
        {atRisk ? <Button type="button" variant="ghost" disabled={locked} onClick={() => ask('Discard all demo drafts in this tab?', () => { adapter.discard(); setArchive([]); setResume(''); showRecord(null); })}>Discard tab drafts</Button> : null}
      </div>
      <p className="janso-entry-workspace__caption">Examples and recovery outcomes are simulated. Tab drafts and selected files disappear when you leave or reload.</p>
    </details>
    {record?.rejection ? <Notice tone="danger" title="Purchase rejected"><p>{record.rejection}</p>{permissions.create && permissions.edit ? <Button type="button" variant="ghost" disabled={locked} onClick={() => { setCorrect(true); setReasonError(false); }}>Correct purchase</Button> : <p>Creating a correction requires create and edit permission.</p>}</Notice> : null}
    {record?.correctionOf ? <Notice tone="info" title="Correction draft">Corrects {record.correctionOf.id}, revision {record.correctionOf.revision}. {record.correctionOf.reason}</Notice> : null}
    {status === 'SUBMITTED' || status === 'APPROVED' ? <Notice tone="info" title="Read-only revision">This {status.toLowerCase()} example is frozen. Approval here is a sample status; it does not post stock, tax, payables or payments.</Notice> : null}
    {record?.status === 'DRAFT' && !permissions.edit ? <Notice tone="info" title="Draft review only">Editing an existing draft requires voucher edit permission.</Notice> : null}
    {masterChanges.length ? <Notice tone="warning" title="Master details have changed"><p>Saved descriptions are retained. Current labels are shown for comparison; no source facts have been replaced.</p><ul>{masterChanges.map(change => <li key={change}>{change}</li>)}</ul></Notice> : null}
    {message ? <div role="status"><Notice tone="info" title="Demo workflow result">{message}</Notice></div> : null}
    {command.failure ? <Notice tone={conflict ? 'warning' : 'danger'} title={command.uncertain ? 'Demo result unconfirmed' : conflict ? 'A newer revision exists' : refused ? 'Write access refused' : 'Demo command did not complete'}>
      <p>{command.failure.message}</p>
      {command.failure.fields ? <ul>{Object.entries(command.failure.fields).map(([field, text]) => <li key={field}>{field === 'invoice' ? 'Supplier invoice number' : 'Purchase detail'}: {text}</li>)}</ul> : null}
      {command.uncertain ? <p>Entries are frozen. Recover the same command before editing, switching examples or changing company/year.</p> : null}
      {conflict && record ? <Button type="button" variant="ghost" disabled={locked} onClick={() => void readLatest()}>Compare latest demo revision</Button> : null}
    </Notice> : null}
    {readError ? <Notice tone="danger" title="Latest revision unavailable">{readError}<Button type="button" variant="ghost" disabled={locked} onClick={() => void readLatest()}>Retry loading latest</Button></Notice> : null}
    {blockedNotice ? <Notice tone="warning" title="Finish the current action">Close the detail panel, or recover the pending/unconfirmed command, before leaving or changing examples.</Notice> : null}
  </div>;
  return <>
    <PurchaseWorkspace key={generation} today={today} canCreate={permissions.create || !!record && permissions.edit} policy={displayPolicy} supplierLookup={supplierLookup} controller={{ draft, dispatch,
      readOnly: !editable, pending: command.pending || loadingLatest, title, dirty: dirty || transient, onTransientChange,
      serverProblems: command.failure?.fields ? Object.entries(command.failure.fields).map(([field, text]) => ({ key: 'demo:' + field, field, message: text })) : [],
      note: command.uncertain ? 'Unconfirmed · editing frozen' : command.pending ? 'Checking demo command…' : record ? 'Provisional · This tab only' : 'Provisional · Not saved', banner,
      actions: ({ validate, review: openReview }) => <>
        <Button type="button" variant="ghost" disabled={locked} onClick={openReview}>Review bill</Button>
        {command.pending ? <Button type="button" loading loadingLabel="Checking demo command…">Checking demo command…</Button>
          : command.uncertain ? <Button type="button" onClick={() => void perform((retained.current?.body as PurchaseWorkflowCommand).action, true)}>Recover same demo command</Button>
          : editable ? <Button type="button" loading={command.pending} disabled={transient} onClick={() => { if (validate()) void perform('SAVE'); }}>Save demo draft</Button> : null}
        {record?.status === 'DRAFT' && permissions.submit && !dirty && editable && !command.failure ? <Button type="button" variant="ghost" disabled={transient || locked} onClick={() => {
          if (validate()) { if (purchaseWorkspacePreview(draft).total === null) setMessage('Submission needs complete supplied calculation evidence. Keep this as a demo draft or load a supported example.'); else setReview(true); }
        }}>Review & submit demo</Button> : null}
      </> }} />
    {review && record ? <PurchaseWorkflowReview draft={draft} record={record} pending={command.pending} onClose={() => setReview(false)} onConfirm={() => void perform('SUBMIT')} /> : null}
    <Modal open={correct} title="Create correction draft" busy={locked} onClose={() => setCorrect(false)} footer={<>
      <Button type="button" variant="ghost" disabled={locked} onClick={() => setCorrect(false)}>Keep rejected original</Button>
      <Button type="button" loading={command.pending} onClick={() => { if (!reason.trim()) { setReasonError(true); document.querySelector<HTMLInputElement>('[name="purchase-correction-reason"]')?.focus(); } else void perform('CORRECT'); }}>Create demo correction</Button>
    </>}><p className="janso-entry-workflow__dialog">The rejected revision stays unchanged. A separate editable demo draft will keep its supplier, source facts and correction lineage.</p>
      <TextField label="Reason for correction" name="purchase-correction-reason" required value={reason} maxLength={500} disabled={locked} error={reasonError && !reason.trim() ? 'Describe what you will correct.' : undefined} onChange={event => setReason(event.target.value)} />
    </Modal>
    <Modal open={!!latest} title="Compare demo revisions" size="lg" onClose={() => setLatest(null)} footer={<>
      <Button type="button" variant="ghost" onClick={() => setLatest(null)}>Keep my entries</Button>
      <Button type="button" variant="ghost" disabled={!permissions.create} onClick={() => {
        const copy = copyPurchaseDraft(draft); showRecord(null); setDraft(copy); setBaseline(JSON.stringify(newPurchaseWorkspace(today))); setLatest(null);
      }}>Copy my entries to a new demo</Button>
      <Button type="button" onClick={() => { if (latest) setConfirmation({ title: 'Replace your entries with the latest revision?', proceed: () => showRecord(latest) }); }}>Use latest demo revision</Button>
    </>}>
      {latest ? <div className="janso-entry-workspace__details janso-entry-workflow__dialog"><Notice tone="warning" title="No automatic overwrite">Your inputs are retained until you choose a revision. Copying creates a separate demo bill; it does not merge into the newer revision.</Notice>
        <div className="janso-entry-workflow__comparison"><section><h3>Your entries · r{record?.revision}</h3><p>{draft.invoice}</p><p>{draft.details.notes || 'No purchase notes'}</p></section><section><h3>Latest demo · r{latest.revision}</h3><p>{latest.draft.invoice}</p><p>{latest.draft.details.notes || 'No purchase notes'}</p></section></div></div> : null}
    </Modal>
    <Modal open={!!confirmation} title={confirmation?.title ?? 'Leave purchase preview?'} onClose={() => setConfirmation(null)} footer={<>
      <Button type="button" variant="ghost" onClick={() => setConfirmation(null)}>Stay with this purchase</Button>
      <Button type="button" onClick={() => { const next = confirmation?.proceed; setConfirmation(null); next?.(); }}>Discard current entries and continue</Button>
    </>}><p className="janso-entry-workflow__dialog">Current edits may be discarded. Demo drafts and selected files are held only in this tab; leaving or reloading loses them. No service save has occurred.</p></Modal>
  </>;
}
