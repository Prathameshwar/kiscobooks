'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { AmountField, Button, Drawer, Modal, Notice, QuantityField, SearchSelect, Select, TextField, useFormatters } from '@janso/ui';
import { InlineCreate, PurchaseQuickCreateButton } from './PurchaseQuickCreateButton';
import type { QuickCreateTarget } from '../lib/purchase-quick-create';
import { purchaseLineAmounts, purchaseSubjectLookup, purchaseWorkspaceProblems, type PurchaseLine, type PurchaseWorkspaceDraft, type PurchaseWorkspacePolicy } from '../lib/purchase-workspace';
import { useUnsavedChanges } from '../lib/use-unsaved-changes';
import * as D from '../lib/fixed-decimal';

/** A staged full-line editor for compact entry; desktop keyboard entry keeps the same reducer. */
export function PurchaseLineEditor({ draft, line: original, ordinal, policy, canEdit, focusField, onCreateAccount, onApply, onClose }: {
  draft: PurchaseWorkspaceDraft; line: PurchaseLine; ordinal: number; policy: PurchaseWorkspacePolicy;
  canEdit: boolean; focusField?: string; onCreateAccount?: (target: QuickCreateTarget) => void; onApply: (line: PurchaseLine) => void; onClose: () => void;
}) {
  const [line, setLine] = useState(original), [attempted, setAttempted] = useState(false), [discard, setDiscard] = useState(false);
  const [raw, setRaw] = useState<Record<string, string>>({});
  const content = useRef<HTMLDivElement>(null), { money } = useFormatters();
  const dirty = JSON.stringify(line) !== JSON.stringify(original) || Object.keys(raw).length > 0;
  useUnsavedChanges(useCallback(() => dirty, [dirty]));
  const problems = purchaseWorkspaceProblems({ ...draft, lines: [line] }, policy).filter(problem => problem.lineKey === line.key && !problem.panel);
  const error = (field: string) => raw[field] ?? (attempted ? problems.find(problem => problem.field === field)?.message : undefined);
  const focus = (field: string) => [...content.current?.querySelectorAll<HTMLElement>('[data-purchase-line-field]') ?? []].find(element => element.dataset.purchaseLineField === field)?.querySelector<HTMLElement>('input,select,textarea,button')?.focus();
  useEffect(() => { if (focusField) { setAttempted(true); focus(focusField); } }, [focusField]);
  const change = (patch: Partial<PurchaseLine>) => setLine(current => ({ ...current, ...patch }));
  const close = () => dirty ? setDiscard(true) : onClose();
  const apply = () => {
    if (!canEdit) return;
    setAttempted(true); const first = Object.keys(raw)[0] ?? problems[0]?.field;
    if (first) { focus(first); return; } onApply(line);
  };
  const number = (field: 'received' | 'billed' | 'rate' | 'amount' | 'discount', label: string, quantity = false) => {
    const Control = quantity ? QuantityField : AmountField;
    return <div data-purchase-line-field={field}><Control label={label} value={line[field]} disabled={!canEdit || field === 'discount' && policy.discountsAllowed === false} error={error(field)}
      precision={field === 'rate' || policy.live && field === 'amount' ? 4 : undefined} unit={quantity ? line.unit : undefined} onChange={value => change({ [field]: value })}
      onUnstorable={message => setRaw(current => {
        if ((message === null && !(field in current)) || current[field] === message) return current;
        const next = { ...current }; if (message) next[field] = message; else delete next[field]; return next;
      })} /></div>;
  };
  const amounts = Object.keys(raw).length ? null : purchaseLineAmounts(line);
  return <>
    <Drawer open title={`${canEdit ? 'Edit' : 'Review'} purchase line ${ordinal}`} size="lg" onClose={close} footer={<>
      <Button type="button" variant={canEdit ? 'ghost' : 'primary'} onClick={close}>{canEdit ? 'Cancel line edit' : 'Done'}</Button>
      {canEdit ? <Button type="button" onClick={apply}>Apply line</Button> : null}
    </>}><div className="janso-entry-detail janso-entry-line-editor" ref={content}>
      <p className="janso-entry-workspace__caption">{canEdit ? 'Edit this line, then apply it to the bill. Other lines stay as entered.' : 'This revision is read-only.'}</p>
      {draft.mode === 'MIXED' ? <div data-purchase-line-field="kind"><Select label="Line type" value={line.kind} disabled={!canEdit || Object.keys(raw).length > 0} hint={Object.keys(raw).length ? 'Correct the invalid number before changing line type.' : undefined} options={[{ value: 'ITEM', label: 'Item' }, { value: 'ACCOUNT', label: 'Account / service' }]}
        onChange={kind => change({ kind: kind as PurchaseLine['kind'], subject: '', label: '', unit: '' })} /></div> : null}
      <div data-purchase-line-field="subject"><InlineCreate action={canEdit && onCreateAccount && line.kind === 'ACCOUNT' ? <PurchaseQuickCreateButton size="md" className="console-reference-create__action" label="Create a new expense account" onClick={() => onCreateAccount({ lineKey: line.key, apply: created => change({ subject: created.id, label: created.label, unit: '' }) })} data-quick-create="account" /> : undefined}><SearchSelect label={line.kind === 'ITEM' ? 'Item' : 'Expense / service account'} required disabled={!canEdit}
        scopeKey={line.kind} selected={line.subject ? { id: line.subject, label: line.label } : null} value={line.subject || null}
        options={purchaseSubjectLookup(policy, line.kind) ? undefined : policy.subjects.filter(subject => subject.kind === line.kind)} loadOptions={purchaseSubjectLookup(policy, line.kind)} error={error('subject')}
        onChange={(id, option) => { const subject = policy.subjects.find(subject => subject.id === id && subject.kind === line.kind); change({ subject: subject?.id ?? id ?? '', label: subject?.label ?? option?.label ?? '', unit: subject?.unit ?? '' }); }} /></InlineCreate></div>
      {line.label ? <p className="janso-entry-line-card__name">{line.label}</p> : null}
      {line.kind === 'ITEM' ? <><div className="janso-form-grid janso-entry-detail__pair">{number('received', 'Receipt quantity', true)}{number('billed', 'Billed quantity', true)}</div>
        {number('rate', 'Unit rate')}
        <div data-purchase-line-field="quantityReason"><TextField label="Quantity difference reason" value={line.quantityReason} disabled={!canEdit} maxLength={500}
          hint="Explain any difference between received and billed quantities." error={error('quantityReason')} onChange={event => change({ quantityReason: event.target.value })} /></div></> : number('amount', 'Base amount')}
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
