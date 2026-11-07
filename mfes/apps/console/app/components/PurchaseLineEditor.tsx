'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { AmountField, Button, Drawer, Modal, Notice, QuantityField, SearchSelect, Select, TextField, useFormatters } from '@janso/ui';
import { InlineCreate, PurchaseProductCreateLink, PurchaseQuickCreateButton } from './PurchaseQuickCreateButton';
import type { QuickCreateTarget } from '../lib/purchase-quick-create';
import { purchaseLineAmounts, purchaseSubjectLookup, purchaseWorkspaceProblems, type PurchaseLine, type PurchaseSubject, type PurchaseWorkspaceDraft, type PurchaseWorkspacePolicy } from '../lib/purchase-workspace';
import { purchaseItem } from '../lib/purchase-goods';
import { useUnsavedChanges } from '../lib/use-unsaved-changes';
import * as D from '../lib/fixed-decimal';
import { PurchaseStockDetails } from './PurchaseStockDetails';
import { PurchaseSelectionBalance } from './PurchaseSelectionBalance';
import { PurchaseProductHistory } from './PurchaseProductHistory';

/** A staged full-line editor for compact entry; desktop keyboard entry keeps the same reducer. */
export function PurchaseLineEditor({ draft, line: original, ordinal, policy, canEdit, focusField, onCreateAccount, canCreateProduct, onApply, onClose }: {
  draft: PurchaseWorkspaceDraft; line: PurchaseLine; ordinal: number; policy: PurchaseWorkspacePolicy;
  canEdit: boolean; focusField?: string; onCreateAccount?: (target: QuickCreateTarget) => void; canCreateProduct?: boolean; onApply: (line: PurchaseLine) => void; onClose: () => void;
}) {
  const [line, setLine] = useState(original), [attempted, setAttempted] = useState(false), [discard, setDiscard] = useState(false);
  // Live search results are not in policy.subjects until the connected controller verifies them.
  const [selectedSubject, setSelectedSubject] = useState<PurchaseSubject | null>(null);
  const [resolvingItem, setResolvingItem] = useState(false), [itemError, setItemError] = useState('');
  const [verifiedItemId, setVerifiedItemId] = useState<string | null>(null);
  const selectionRequest = useRef(0);
  const [raw, setRaw] = useState<Record<string, string>>({});
  const content = useRef<HTMLDivElement>(null), { money } = useFormatters();
  const dirty = JSON.stringify(line) !== JSON.stringify(original) || Object.keys(raw).length > 0;
  useUnsavedChanges(useCallback(() => dirty, [dirty]));
  const selection = selectedSubject?.id === line.subject && selectedSubject.kind === line.kind ? selectedSubject : null;
  const linePolicy = selection ? { ...policy, subjects: [...policy.subjects, selection] } : policy;
  const problems = purchaseWorkspaceProblems({ ...draft, lines: [line] }, linePolicy).filter(problem => problem.lineKey === line.key && !problem.panel);
  const error = (field: string) => raw[field] ?? (attempted ? problems.find(problem => problem.field === field)?.message : undefined);
  const focus = (field: string) => [...content.current?.querySelectorAll<HTMLElement>('[data-purchase-line-field]') ?? []].find(element => element.dataset.purchaseLineField === field)?.querySelector<HTMLElement>('input,select,textarea,button')?.focus();
  useEffect(() => { if (focusField) { setAttempted(true); focus(focusField); } }, [focusField]);
  const change = (patch: Partial<PurchaseLine>) => setLine(current => ({ ...current, ...patch }));
  const close = () => dirty ? setDiscard(true) : onClose();
  const apply = () => {
    if (!canEdit || resolvingItem) return;
    if (itemError) { setAttempted(true); focus('subject'); return; }
    setAttempted(true); const first = Object.keys(raw)[0] ?? problems[0]?.field;
    if (first) { focus(first); return; } onApply(line);
  };
  const number = (field: 'received' | 'billed' | 'rate' | 'amount' | 'discount', label: string, quantity = false) => {
    const Control = quantity ? QuantityField : AmountField;
    return <div data-purchase-line-field={field}><Control label={label} value={line[field]} disabled={!canEdit || field === 'discount' && policy.discountsAllowed === false} error={error(field)}
      precision={field === 'rate' || policy.live && field === 'amount' ? 4 : undefined} unit={quantity ? line.unit : undefined} onChange={value => setLine(current => ({ ...current, [field]: value,
        ...(field === 'billed' && current.kind === 'ITEM' && !current.received ? { received: value } : {}),
      }))}
      onCommit={field === 'received' ? value => setLine(current => current.kind === 'ITEM' && !current.billed && value ? { ...current, received: value, billed: value } : current) : undefined}
      onUnstorable={message => setRaw(current => {
        if ((message === null && !(field in current)) || current[field] === message) return current;
        const next = { ...current }; if (message) next[field] = message; else delete next[field]; return next;
      })} /></div>;
  };
  const amounts = Object.keys(raw).length ? null : purchaseLineAmounts(line);
  return <>
    <Drawer open title={`${canEdit ? 'Edit' : 'Review'} purchase line ${ordinal}`} size="lg" onClose={close} footer={<>
      <Button type="button" variant={canEdit ? 'ghost' : 'primary'} onClick={close}>{canEdit ? 'Cancel line edit' : 'Done'}</Button>
      {canEdit ? <Button type="button" onClick={apply} disabled={resolvingItem}>Apply line</Button> : null}
    </>}><div className="janso-entry-detail janso-entry-line-editor" ref={content}>
      <p className="janso-entry-workspace__caption">{canEdit ? 'Edit this line, then apply it to the bill. Other lines stay as entered.' : 'This revision is read-only.'}</p>
      {draft.mode === 'MIXED' ? <div data-purchase-line-field="kind"><Select label="Line type" value={line.kind} disabled={!canEdit || Object.keys(raw).length > 0} hint={Object.keys(raw).length ? 'Correct the invalid number before changing line type.' : undefined} options={[{ value: 'ITEM', label: 'Item' }, { value: 'ACCOUNT', label: 'Account / service' }]}
        onChange={kind => { selectionRequest.current++; setResolvingItem(false); setItemError(''); setVerifiedItemId(null); setSelectedSubject(null); change({ kind: kind as PurchaseLine['kind'], subject: '', label: '', unit: '', stock: undefined }); }} /></div> : null}
      <div data-purchase-line-field="subject"><InlineCreate action={canEdit && canCreateProduct && line.kind === 'ITEM' ? <PurchaseProductCreateLink line={ordinal} size="md" className="console-reference-create__action" /> : canEdit && onCreateAccount && line.kind === 'ACCOUNT' ? <PurchaseQuickCreateButton size="md" className="console-reference-create__action" label="Create a new expense account" onClick={() => onCreateAccount({ lineKey: line.key, apply: created => { setSelectedSubject({ id: created.id, label: created.label, meta: created.meta ?? '', kind: 'ACCOUNT', unit: '' }); change({ subject: created.id, label: created.label, unit: '' }); } })} data-quick-create="account" /> : undefined}><SearchSelect label={line.kind === 'ITEM' ? 'Item' : 'Expense / service account'} required disabled={!canEdit}
        scopeKey={line.kind} selected={line.subject ? { id: line.subject, label: line.label } : null} value={line.subject || null}
        options={purchaseSubjectLookup(policy, line.kind) ? undefined : policy.subjects.filter(subject => subject.kind === line.kind)} loadOptions={purchaseSubjectLookup(policy, line.kind)} error={error('subject')}
        onChange={(id, option) => {
          const request = ++selectionRequest.current;
          const subject = policy.subjects.find(subject => subject.id === id && subject.kind === line.kind);
          setItemError(''); setVerifiedItemId(null); setSelectedSubject(subject ?? (id && option ? { id, label: option.label, meta: option.meta ?? '', kind: line.kind, unit: '' } : null));
          change({ subject: subject?.id ?? id ?? '', label: subject?.label ?? option?.label ?? '', unit: subject?.unit ?? '', stock: id === line.subject ? line.stock : undefined });
          if (id && line.kind === 'ITEM' && policy.stockCompany) {
            setResolvingItem(true);
            void purchaseItem(policy.stockCompany, id).then(item => {
              if (selectionRequest.current !== request) return;
              setSelectedSubject({ id: item.id, label: item.label, meta: item.sku ?? '', kind: 'ITEM', unit: item.unit });
              setLine(current => current.subject === item.id ? { ...current, label: item.label, unit: item.unit } : current);
              setVerifiedItemId(item.id);
            }).catch(reason => { if (selectionRequest.current === request) { setItemError(reason instanceof Error ? reason.message : 'The product could not be verified.'); setSelectedSubject(null); } })
              .finally(() => { if (selectionRequest.current === request) setResolvingItem(false); });
          } else setResolvingItem(false);
        }} /></InlineCreate></div>
      {resolvingItem ? <p role="status">Checking product and its unit…</p> : null}
      {itemError ? <Notice tone="danger">{itemError}</Notice> : null}
      {line.label ? <p className="janso-entry-line-card__name">{line.label}</p> : null}
      {line.subject && policy.stockCompany ? <div className="janso-purchase-subject-tools"><PurchaseSelectionBalance company={policy.stockCompany} kind={line.kind} subject={line.subject} postingDate={draft.postingDate} currency={policy.currency} warehouse={line.kind === 'ITEM' ? line.stock?.warehouseId : undefined} unit={line.unit} permitted={line.kind === 'ITEM' ? !!policy.balanceAccess?.stock : !!policy.balanceAccess?.ledger} />{line.kind === 'ITEM' && policy.supplierHistoryAccess ? <PurchaseProductHistory key={`${policy.stockCompany}:${draft.supplier}:${line.subject}`} company={policy.stockCompany} supplier={draft.supplier} supplierName={policy.suppliers.find(row => row.id === draft.supplier)?.label} product={line.subject} name={line.label || 'Product'} /> : null}</div> : null}
      {line.kind === 'ITEM' ? <><div className="janso-form-grid janso-entry-detail__pair">{number('received', 'Receipt quantity', true)}{number('billed', 'Billed quantity', true)}</div>
        {number('rate', 'Unit rate')}
        {policy.stockCompany ? <PurchaseStockDetails company={policy.stockCompany} line={line} postingDate={draft.postingDate} canEdit={canEdit} access={policy.stockAccess} canReadBatch={policy.canReadBatch} canPrepareBatch={policy.canPrepareBatch} canPrepareSerial={policy.canPrepareSerial} promptForItem={verifiedItemId} onChange={stock => change({ stock })} /> : null}
        </> : number('amount', 'Base amount')}
      {number('discount', 'Line discount')}
      <div data-purchase-line-field="description"><TextField label="Line description" value={line.description} disabled={!canEdit} maxLength={1000} onChange={event => change({ description: event.target.value })} /></div>
      <div className="janso-entry-detail__calculation"><p>Line total before tax <strong>{amounts ? money(D.format(amounts.net)) : '—'}</strong></p></div>
      {attempted && (problems.length || Object.keys(raw).length) ? <Notice tone="danger" title="Check this line"><ul>{[...problems.map(problem => problem.message), ...Object.values(raw)].map((message, index) => <li key={index}>{message}</li>)}</ul></Notice> : null}
    </div></Drawer>
    <Modal open={discard} title="Discard line changes?" onClose={() => setDiscard(false)} footer={<><Button type="button" variant="ghost" onClick={() => setDiscard(false)}>Keep editing line</Button><Button type="button" onClick={onClose}>Discard line changes</Button></>}>
      <p className="janso-entry-workflow__dialog">This line will keep the values it had before the editor opened.</p>
    </Modal>
  </>;
}
