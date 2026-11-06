'use client';

import { useCallback, useEffect, useLayoutEffect, useMemo, useReducer, useRef, useState, type ReactNode } from 'react';
import { Badge, Button, DisplayConfigProvider, Drawer, Modal, Notice, Select, TextField, useDisplayConfig, useFormatters, type SearchSelectLoader } from '@janso/ui';
import { useUnsavedChanges } from '../lib/use-unsaved-changes';
import { PURCHASE_DEMO_POLICY, isBlankPurchaseLine, newPurchaseWorkspace, purchaseWorkspacePreview, purchaseWorkspaceProblems, purchaseWorkspaceReducer,
  type PurchaseLine, type PurchaseProblem, type PurchaseWorkspaceAction, type PurchaseWorkspaceDraft, type PurchaseWorkspacePolicy } from '../lib/purchase-workspace';
import * as D from '../lib/fixed-decimal';
import type { PurchaseQuickCreate } from '../lib/purchase-quick-create';
import { PurchaseWorkspaceHeader } from './PurchaseWorkspaceHeader';
import { PurchaseWorkspaceGrid } from './PurchaseWorkspaceGrid';
import { PurchaseWorkspaceTotals } from './PurchaseWorkspaceTotals';
import { PurchaseDetailSections } from './PurchaseDetailSections';
import { PurchaseDetailsPanel } from './PurchaseDetailsPanel';
import { PurchaseLineEditor } from './PurchaseLineEditor';
import { PurchaseStockDetails } from './PurchaseStockDetails';
import { PurchaseBatchChooser } from './PurchaseBatchChooser';
import type { PurchaseTracking } from '../lib/purchase-stock';
import { PURCHASE_SCENARIOS, purchaseScenario } from '../lib/purchase-workspace-scenarios';
import type { PurchasePanel } from '../lib/purchase-workspace-details';

export type PurchaseWorkspaceController = {
  live?: boolean;
  /** Live page only: the page header, and the cards that follow the lines. The synthetic previews keep the heading and totals rail. */
  header?: ReactNode; sections?: ReactNode; total?: string | null;
  /** Live page only: what the footer's figure is called until Accounting has calculated the bill. */
  linesLabel?: string;
  /** Live page only: why the bill is review-only, when that is not simply a missing permission. */
  reviewNotice?: ReactNode;
  draft: PurchaseWorkspaceDraft; dispatch: (action: PurchaseWorkspaceAction) => void;
  readOnly: boolean; pending: boolean; title: string; note: string; dirty: boolean;
  banner: (examples: ReactNode) => ReactNode; onTransientChange: (active: boolean) => void;
  actions: (editor: { validate: () => boolean; review: () => void }) => ReactNode;
  serverProblems?: readonly PurchaseProblem[];
  /** Live page only: create-from-here for the supplier and expense-account lookups. A missing entry hides its icon. */
  quickCreate?: PurchaseQuickCreate;
  batchPrompt?: { lineKey: string; itemId: string; profile: PurchaseTracking } | null;
  closeBatchPrompt?: () => void;
};
type PurchaseWorkspaceProps = {
  today: string; canCreate: boolean; policy?: PurchaseWorkspacePolicy; initialDraft?: PurchaseWorkspaceDraft;
  onDemoSave?: () => Promise<void>;
  controller?: PurchaseWorkspaceController;
  supplierLookup?: SearchSelectLoader;
};
export function PurchaseCostRestricted() {
  return <div className="janso-entry-workspace"><h1>Purchase voucher</h1><Notice tone="info" title="Purchase costs are restricted">This workspace needs access to purchase rates and bill totals. Ask your administrator for the appropriate access.</Notice></div>;
}
/** Synthetic money keeps its fixture currency. Company formatting preferences still apply. */
export function PurchaseWorkspace(props: PurchaseWorkspaceProps) {
  const config = useDisplayConfig();
  const policy = props.policy ?? PURCHASE_DEMO_POLICY;
  const display = useMemo(() => ({ ...config, currency: policy.currency, currencySymbol: policy.currencySymbol }), [config, policy.currency, policy.currencySymbol]);
  if (policy.costAccess === 'DENIED') return <PurchaseCostRestricted />;
  return <DisplayConfigProvider config={display}>{props.controller
    ? <PurchaseWorkspaceBody {...props} policy={policy} draft={props.controller.draft} reduce={props.controller.dispatch} />
    : <LocalPurchaseWorkspace {...props} policy={policy} />}</DisplayConfigProvider>;
}

function LocalPurchaseWorkspace(props: PurchaseWorkspaceProps) {
  const { today, initialDraft } = props;
  const [draft, reduce] = useReducer(purchaseWorkspaceReducer, initialDraft ?? newPurchaseWorkspace(today));
  return <PurchaseWorkspaceBody {...props} draft={draft} reduce={reduce} />;
}

/** One editor/draft shape for local component review and the controlled workflow preview. */
function PurchaseWorkspaceBody({ today, canCreate, policy = PURCHASE_DEMO_POLICY, initialDraft, onDemoSave, controller, draft, reduce, supplierLookup }: PurchaseWorkspaceProps & {
  draft: PurchaseWorkspaceDraft; reduce: (action: PurchaseWorkspaceAction) => void;
}) {
  const initial = useRef(JSON.stringify(initialDraft ?? newPurchaseWorkspace(today)));
  const [attempted, setAttempted] = useState(false);
  const [unstorable, setUnstorable] = useState<ReadonlyMap<string, PurchaseProblem>>(new Map());
  const [openLine, setOpenLine] = useState<string | null>(null);
  const [lineEdit, setLineEdit] = useState<{ key: string; field?: string } | null>(null);
  const [detailTarget, setDetailTarget] = useState<string | null>(null);
  const [panel, setPanel] = useState<PurchasePanel | null>(null);
  const [panelField, setPanelField] = useState<string | undefined>();
  const [scenario, setScenario] = useState('goods');
  const [generation, setGeneration] = useState(0);
  const [removed, setRemoved] = useState<{ line: PurchaseLine; index: number } | null>(null);
  const [review, setReview] = useState(false);
  const [replace, setReplace] = useState(false);
  const [localSaving, setSaving] = useState(false);
  const saving = controller?.pending ?? localSaving;
  const editable = canCreate && !controller?.readOnly;
  const [result, setResult] = useState<'demo' | 'failed' | null>(null);
  const root = useRef<HTMLDivElement>(null);
  const { money, date } = useFormatters();
  const dispatch = (action: PurchaseWorkspaceAction) => {
    if (!editable || saving) return;
    setResult(null);
    if (action.type === 'remove') {
      const index = draft.lines.findIndex(entry => entry.key === action.key);
      if (index >= 0) setRemoved({ line: draft.lines[index]!, index });
    }
    reduce(action);
  };
  const reportUnstorable = useCallback((lineKey: string, field: string, message: string | null) => {
    const key = `${lineKey}:${field}`;
    setUnstorable(current => {
      if ((message === null && !current.has(key)) || current.get(key)?.message === message) return current;
      const next = new Map(current);
      if (message === null) next.delete(key);
      else next.set(key, { key, field, lineKey, message });
      return next;
    });
  }, []);
  const rawProblems = [...unstorable.values()].filter(problem => draft.lines.some(line => line.key === problem.lineKey));
  const dirty = controller?.dirty ?? (JSON.stringify(draft) !== initial.current || rawProblems.length > 0);
  useUnsavedChanges(useCallback(() => !controller && dirty, [controller, dirty]));
  const transient = rawProblems.length > 0 || !!panel || !!openLine || !!lineEdit || !!controller?.batchPrompt;
  const onTransientChange = controller?.onTransientChange;
  useLayoutEffect(() => { onTransientChange?.(transient); return () => onTransientChange?.(false); }, [onTransientChange, transient]);
  useEffect(() => {
    if (openLine && detailTarget) document.querySelector<HTMLInputElement>('[name="purchase-' + detailTarget + '"]')?.focus();
  }, [openLine, detailTarget]);
  const preview = useMemo(() => purchaseWorkspacePreview(draft, rawProblems.length > 0), [draft, rawProblems.length]);
  const allProblems = [...purchaseWorkspaceProblems(draft, policy).filter(problem => !unstorable.has(problem.key)), ...rawProblems, ...controller?.serverProblems ?? []];
  const problems = attempted ? allProblems : [...rawProblems, ...controller?.serverProblems ?? []];
  const retained = draft.mode === 'MIXED' ? 0 : draft.lines.filter(line => !isBlankPurchaseLine(line) && line.kind !== (draft.mode === 'ITEMS' ? 'ITEM' : 'ACCOUNT')).length;
  const line = draft.lines.find(entry => entry.key === openLine);
  const editedLine = draft.lines.find(entry => entry.key === lineEdit?.key);
  const promptLine = draft.lines.find(entry => entry.key === controller?.batchPrompt?.lineKey && entry.kind === 'ITEM' && entry.subject === controller?.batchPrompt?.itemId && !entry.stock?.lotId);
  const goToProblem = (problem: PurchaseProblem) => {
    if (problem.panel && policy.details.panels[problem.panel].available) { setPanelField(problem.field); setPanel(problem.panel); return; }
    if (problem.lineKey && [...root.current?.querySelectorAll<HTMLElement>('[data-purchase-mobile-line]') ?? []].some(card => card.dataset.purchaseMobileLine === problem.lineKey)) { setLineEdit({ key: problem.lineKey, field: problem.field }); return; }
    if (problem.lineKey && problem.field === 'description') { setDetailTarget(problem.field); setOpenLine(problem.lineKey); return; }
    // The payable account has no control of its own: a problem with it is a problem with the supplier.
    const field = problem.field === 'payable' ? 'supplier' : problem.field;
    const fields = root.current?.querySelectorAll<HTMLElement>(problem.lineKey ? '[data-entry-row]' : '[data-purchase-field]');
    const wrapper = [...fields ?? []].find(element => problem.lineKey ? element.dataset.entryRow === problem.lineKey && element.dataset.entryCol === field : element.dataset.purchaseField === field);
    const target = wrapper?.matches('input,button,select') ? wrapper : wrapper?.querySelector<HTMLElement>('input,select,button');
    target?.focus();
    target?.scrollIntoView?.({ block: 'center' });
  };
  const validate = () => { setAttempted(true); if (allProblems.length) { goToProblem(allProblems[0]!); return false; } return true; };
  const firstServerProblem = controller?.serverProblems?.[0];
  useEffect(() => { if (firstServerProblem) goToProblem(firstServerProblem); }, [firstServerProblem?.key, firstServerProblem?.message]);
  const loadExample = () => {
    dispatch({ type: 'replace', draft: purchaseScenario(scenario, today) });
    setUnstorable(new Map()); setAttempted(false); setOpenLine(null); setReplace(false); setRemoved(null); setGeneration(current => current + 1);
  };
  const saveDemo = async () => {
    if (!canCreate || saving || !validate()) return;
    setSaving(true); setResult(null);
    try { await (onDemoSave?.() ?? Promise.resolve()); setResult('demo'); }
    catch { setResult('failed'); }
    finally { setSaving(false); }
  };
  // The live page shows what has been typed, labelled as such, until Accounting has calculated the bill.
  const typedTotal = preview.activeCount === 0 || preview.net === null ? '—' : money(D.format(preview.net));
  const amount = controller?.live ? controller.total ? money(controller.total) : typedTotal : preview.total === null ? '—' : money(D.format(preview.total));
  const totalLabel = controller?.live && !controller.total ? controller.linesLabel ?? 'Lines total' : 'Bill total';
  const exampleControls = <div className="janso-entry-workflow__buttons"><Select label="Example scenario" value={scenario} disabled={!editable || saving} options={PURCHASE_SCENARIOS} onChange={setScenario} />
    <Button variant="ghost" type="button" disabled={!editable || saving} onClick={() => dirty ? setReplace(true) : loadExample()}>Load example bill</Button></div>;
  return <div ref={root} className="janso-entry-frame janso-entry-workspace">
    {controller?.live && controller.header ? controller.header
      : <div className="janso-entry-workspace__heading"><div><div className="janso-entry-workspace__eyebrow">Purchases / {controller?.live ? 'Supplier bill' : controller ? 'Workflow preview' : 'New bill'}</div><h1>{controller?.title ?? 'New purchase'}</h1><p>Capture your supplier bill, with every detail in its place.</p></div>{!controller ? <Badge tone="info">UI preview</Badge> : null}</div>}
    {!controller?.live ? <div className="janso-entry-workspace__preview"><span><strong>Preview workspace</strong> · Synthetic examples in {policy.currency}. Changes stay on this page and are lost on reload.</span>
      {!controller ? exampleControls : null}</div> : null}
    {controller?.banner(exampleControls)}
    {attempted && allProblems.length ? <Notice tone="danger" title={`${allProblems.length} ${allProblems.length === 1 ? 'detail needs' : 'details need'} correction before this Purchase can be saved or submitted`}>
      <ul>{allProblems.slice(0, 5).map(problem => <li key={problem.key}><Button type="button" variant="ghost" onClick={() => goToProblem(problem)}>{problem.message}</Button></li>)}</ul>
      {allProblems.length > 5 ? <p>Correct these first, then review the remaining {allProblems.length - 5} {allProblems.length - 5 === 1 ? 'detail' : 'details'}.</p> : null}
    </Notice> : null}
    {!canCreate ? controller?.reviewNotice ?? <Notice tone="info" title="Review only">You do not have permission to create vouchers for this company.</Notice> : null}
    {result ? <div role="status"><Notice tone={result === 'demo' ? 'info' : 'danger'} title={result === 'demo' ? 'Demo draft only' : 'Demo action failed'}>
      {result === 'demo' ? 'This bill has not been saved. Keep this page open; reloading will discard your changes.' : 'Your entries are still here. Retry the demo action when you are ready.'}</Notice></div> : null}
    <div className={'janso-entry-workspace__layout' + (controller?.live ? ' janso-entry-workspace__layout--single' : '')}>
      <div className="janso-entry-workspace__main">
        <PurchaseWorkspaceHeader draft={draft} policy={policy} dispatch={dispatch} problems={problems} disabled={!editable || saving} supplierLookup={supplierLookup} onCreateSupplier={controller?.quickCreate?.supplier} />
        {retained > 0 ? <Notice tone="warning" title={`${retained} ${retained === 1 ? 'line is' : 'lines are'} retained from another mode`}>
          All entered details are preserved. Choose a matching entry mode to continue. {policy.modes.includes('MIXED') ? <Button variant="ghost" type="button" disabled={!editable || saving} onClick={() => dispatch({ type: 'mode', mode: 'MIXED' })}>Use Mixed mode</Button> : null}</Notice> : null}
        {controller?.live ? null : <div className="janso-entry-workspace__identity" role="group" aria-label="Current purchase bill"><strong title={draft.invoice}>{draft.invoice || 'New supplier bill'}</strong><span>{preview.activeCount} {preview.activeCount === 1 ? 'line' : 'lines'} · {policy.currency}</span></div>}
        <PurchaseWorkspaceGrid key={generation} draft={draft} policy={policy} dispatch={dispatch} problems={problems} disabled={!editable || saving} onDetails={key => { setDetailTarget(null); setOpenLine(key); }} onEdit={key => setLineEdit({ key })} keepGrid={rawProblems.length > 0} onUnstorable={reportUnstorable} onCreateAccount={controller?.quickCreate?.account} canCreateProduct={controller?.quickCreate?.product} />
        {removed ? <div className="janso-entry-workspace__preview" role="status"><span>Line removed: {removed.line.label || 'empty line'}</span><Button variant="ghost" type="button" disabled={!editable || saving} onClick={() => { dispatch({ type: 'restore', ...removed }); setRemoved(null); }}>Undo removal</Button></div> : null}
        <PurchaseDetailSections draft={draft} policy={policy} disabled={saving} onOpen={next => { setPanelField(undefined); setPanel(next); }} />
        {controller?.live ? controller.sections : null}
      </div>
      {controller?.live ? null : <PurchaseWorkspaceTotals draft={draft} preview={preview} problems={problems} onProblem={goToProblem} />}
    </div>
    <footer className="janso-entry__actions janso-entry-workspace__actions" role="group" aria-label="Purchase actions">
      <div className="janso-entry__actions-total"><span>{totalLabel}</span><strong>{amount}</strong></div>
      <span className="janso-entry__actions-note">{controller?.note ?? (saving ? 'Checking the demo draft…' : 'Provisional · Not saved')}</span>
      {controller ? controller.actions({ validate, review: () => setReview(true) }) : <>
        <Button variant="ghost" type="button" disabled={saving} onClick={() => { if (!canCreate || validate()) setReview(true); }}>Review bill</Button>
        {canCreate ? <Button type="button" loading={saving} loadingLabel="Checking demo…" onClick={() => void saveDemo()}>Save demo draft</Button> : null}</>}
    </footer>
    {panel ? <PurchaseDetailsPanel key={`${generation}:${panel}`} panel={panel} draft={draft} policy={policy} canEdit={editable && !saving} focusField={panelField}
      onApply={details => { dispatch({ type: 'details', details }); setPanel(null); setPanelField(undefined); }} onClose={() => { setPanel(null); setPanelField(undefined); }} /> : null}
    {editedLine ? <PurchaseLineEditor key={editedLine.key} draft={draft} line={editedLine} ordinal={draft.lines.indexOf(editedLine) + 1} policy={policy} canEdit={editable && !saving} focusField={lineEdit?.field} onCreateAccount={controller?.quickCreate?.account} canCreateProduct={controller?.quickCreate?.product}
      onApply={next => { dispatch({ type: 'line', key: next.key, patch: next }); setLineEdit(null); }} onClose={() => setLineEdit(null)} /> : null}
    {promptLine && controller?.batchPrompt && policy.stockCompany && !saving ? <PurchaseBatchChooser key={`${promptLine.key}:${promptLine.subject}`} company={policy.stockCompany} item={promptLine.subject} name={promptLine.label} postingDate={draft.postingDate}
      profile={controller.batchPrompt.profile} canCreate={!!policy.canPrepareBatch} onClose={() => controller.closeBatchPrompt?.()}
      onSelect={batch => { dispatch({ type: 'line', key: promptLine.key, patch: { stock: { ...(promptLine.stock ?? { warehouseId: '', binId: '', lotId: '', unitIds: [] }), lotId: batch.id, unitIds: [] } } }); controller.closeBatchPrompt?.(); }} /> : null}
    <Drawer open={!!line} title={`Line ${draft.lines.findIndex(entry => entry.key === openLine) + 1} details`} onClose={() => setOpenLine(null)}
      footer={<Button type="button" onClick={() => setOpenLine(null)}>Done</Button>}>
      {line ? <div className="janso-entry-workspace__details"><h3>{line.label || 'Choose an item or account in the bill'}</h3>
        {line.kind === 'ITEM' && policy.stockCompany ? <PurchaseStockDetails company={policy.stockCompany} line={line} postingDate={draft.postingDate} canEdit={editable && !saving} access={policy.stockAccess} canReadBatch={policy.canReadBatch} canPrepareBatch={policy.canPrepareBatch} onChange={stock => dispatch({ type: 'line', key: line.key, patch: { stock } })} /> : null}
        <TextField label="Line description" name="purchase-description" value={line.description} disabled={!editable || saving} maxLength={1000}
          hint="Optional details to help identify this purchase." onChange={event => dispatch({ type: 'line', key: line.key, patch: { description: event.target.value } })} />
        {line.kind === 'ITEM' ? <p className="janso-entry-workspace__caption">Receipt quantity: {line.received || '—'} {line.unit} · Billed quantity: {line.billed || '—'} {line.unit}. Direct bills require equal quantities.</p> : <p className="janso-entry-workspace__caption">Account and service lines are entered as amounts. Quantities do not affect this line.</p>}
        <p className="janso-entry-workspace__caption">Edits apply to this page immediately.</p>
      </div> : null}
    </Drawer>
    <Modal open={replace} title="Load the example bill?" onClose={() => setReplace(false)} footer={<><Button variant="ghost" type="button" onClick={() => setReplace(false)}>Keep my entries</Button><Button type="button" onClick={loadExample}>Replace with example</Button></>}>
      <p>This replaces your current entries with a synthetic supplier bill. Your current entries have not been saved.</p>
    </Modal>
    <Modal open={review} title="Review purchase bill" size="lg" onClose={() => setReview(false)} footer={<Button type="button" onClick={() => setReview(false)}>Back to bill</Button>}>
      <div className="janso-entry-workspace__details"><Notice tone="info" title={controller?.live ? 'Review entries' : 'Preview only'}>Reviewing this bill does not save, submit or post it.</Notice>
        <dl className="janso-entry-workspace__review"><dt>Supplier</dt><dd>{policy.suppliers.find(supplier => supplier.id === draft.supplier)?.label ?? 'Not selected'}</dd><dt>Supplier invoice</dt><dd>{draft.invoice || 'Not entered'}</dd><dt>Invoice date</dt><dd>{date(draft.invoiceDate)}</dd><dt>Posting date</dt><dd>{date(draft.postingDate)}</dd><dt>Entered lines</dt><dd>{preview.activeCount}</dd><dt>Provisional bill total</dt><dd>{amount}</dd></dl>
        {policy.live && draft.lines.some(row => row.kind === 'ITEM' && !isBlankPurchaseLine(row)) ? <div><h3>Stock destinations</h3><ul>{draft.lines.filter(row => row.kind === 'ITEM' && !isBlankPurchaseLine(row)).map(row => <li key={row.key}>{row.label || 'Product'}: {row.stock?.warehouseId ? `warehouse ${row.stock.warehouseId.slice(-8)}` : 'default purchase warehouse'}{row.stock?.binId ? ` · bin ${row.stock.binId.slice(-8)}` : ''}{row.stock?.lotId ? ` · batch ${row.stock.lotId.slice(-8)}` : ''}{row.stock?.unitIds.length ? ` · ${row.stock.unitIds.length} serials` : ''}</li>)}</ul></div> : null}
        {preview.total === null ? <p>Tax and bill total need refreshed calculation evidence.</p> : null}
      </div>
    </Modal>
  </div>;
}
