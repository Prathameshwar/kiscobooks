'use client';

import { Button, EntryGrid, SearchSelect, Select, useDisplayConfig, useFormatters, type EntryColumn } from '@janso/ui';
import { PurchaseProductCreateLink, PurchaseQuickCreateButton } from './PurchaseQuickCreateButton';
import { useLayoutEffect, useRef, useState } from 'react';
import { PurchaseMobileLines } from './PurchaseMobileLines';
import { isBlankPurchaseLine, purchaseLineAmounts, purchaseSubjectLookup, type PurchaseLine, type PurchaseLineKind } from '../lib/purchase-workspace';
import * as D from '../lib/fixed-decimal';
import type { QuickCreateTarget } from '../lib/purchase-quick-create';
import { isTaxed } from '../lib/purchase-tax';
import type { PurchaseWorkspaceSectionProps } from './PurchaseWorkspaceHeader';
import { PurchaseSelectionBalance } from './PurchaseSelectionBalance';
import { PurchaseProductHistory } from './PurchaseProductHistory';
import { PurchaseBatchSummary } from './PurchaseBatchSummary';

export function PurchaseWorkspaceGrid({ draft, policy, dispatch, problems, disabled, onDetails, onEdit, onUnstorable, keepGrid, onCreateAccount, canCreateProduct }: PurchaseWorkspaceSectionProps & {
  onEdit: (key: string) => void; keepGrid: boolean; onCreateAccount?: (target: QuickCreateTarget) => void; canCreateProduct?: boolean;
  onDetails: (key: string) => void; onUnstorable: (key: string, field: string, problem: string | null) => void;
}) {
  const config = useDisplayConfig();
  const { money } = useFormatters();
  const panel = useRef<HTMLElement>(null), focusLine = useRef<string | undefined>(undefined), compactNow = useRef(false);
  const lastFocusedLine = useRef<string | undefined>(undefined);
  const [compact, setCompact] = useState(false);
  const [retainGrid, setRetainGrid] = useState(false);
  const [activeLine, setActiveLine] = useState<string | null>(null);
  useLayoutEffect(() => { if (compact && keepGrid) setRetainGrid(true); else if (!compact) setRetainGrid(false); }, [compact, keepGrid]);
  useLayoutEffect(() => {
    const measure = () => {
      if (!panel.current) return;
      const next = getComputedStyle(panel.current).getPropertyValue('--janso-entry-compact').trim() === '1';
      if (next === compactNow.current) return;
      const active = document.activeElement as HTMLElement | null;
      if (active && panel.current.contains(active)) focusLine.current = active.closest<HTMLElement>('[data-entry-row]')?.dataset.entryRow ?? active.closest<HTMLElement>('[data-purchase-mobile-line]')?.dataset.purchaseMobileLine;
      compactNow.current = next; setCompact(next);
    };
    measure();
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(measure);
    if (panel.current) observer?.observe(panel.current);
    window.addEventListener('resize', measure);
    return () => { observer?.disconnect(); window.removeEventListener('resize', measure); };
  }, []);
  useLayoutEffect(() => {
    if (!focusLine.current) return;
    const key = focusLine.current; focusLine.current = undefined;
    // A retained grid still owns its focused field. Move focus only when its DOM was replaced.
    if (document.activeElement && panel.current?.contains(document.activeElement)) return;
    const edit = [...panel.current?.querySelectorAll<HTMLButtonElement>('[data-purchase-edit-line]') ?? []].find(button => button.dataset.purchaseEditLine === key);
    const cell = [...panel.current?.querySelectorAll<HTMLElement>('[data-entry-row]') ?? []].find(cell => cell.dataset.entryRow === key);
    (edit ?? cell?.querySelector<HTMLElement>('input,button,select'))?.focus();
  }, [compact, keepGrid, retainGrid]);
  const problem = (line: PurchaseLine, field: string) => problems.find(entry => entry.lineKey === line.key && entry.field === field)?.message;
  const hasItems = draft.mode !== 'ACCOUNTS' || draft.lines.some(line => line.kind === 'ITEM' && !isBlankPurchaseLine(line));
  const hasKinds = draft.mode === 'MIXED' || draft.lines.some(line => !isBlankPurchaseLine(line) && line.kind !== (draft.mode === 'ACCOUNTS' ? 'ACCOUNT' : 'ITEM'));
  const selectedSupplierName = policy.suppliers.find(row => row.id === draft.supplier)?.label;
  const columns: EntryColumn<PurchaseLine>[] = [];
  if (hasKinds) columns.push({ key: 'kind', label: 'Line type', kind: 'custom', value: line => line.kind,
    render: (line, cell) => <span className="janso-entry-workspace__kind" {...cell.cellProps} aria-label={undefined} ref={cell.registerRef}><Select label={cell.cellProps['aria-label']} hideLabel value={line.kind} disabled={cell.disabled}
      options={[{ value: 'ITEM', label: 'Item' }, { value: 'ACCOUNT', label: 'Account' }]}
      onChange={kind => dispatch({ type: 'kind', key: line.key, kind: kind as PurchaseLineKind })} /></span> });
  columns.push({ key: 'subject', label: hasKinds ? 'Item or account' : draft.mode === 'ACCOUNTS' ? 'Expense / service account' : 'Item', kind: 'custom', pin: 'start', required: true,
    value: line => line.subject, renderKey: line => `${line.kind}:${line.label}:${line.unit}:${onCreateAccount ? 'account' : ''}:${canCreateProduct ? 'product' : ''}:${policy.stockCompany ?? ''}:${policy.supplierHistoryAccess ? 'history' : ''}:${draft.supplier}:${selectedSupplierName ?? ''}:${activeLine === line.key ? 'active' : ''}:${draft.postingDate}:${policy.currency}:${line.stock?.warehouseId ?? ''}:${policy.balanceAccess?.stock ? 'stock' : ''}:${policy.balanceAccess?.ledger ? 'ledger' : ''}`, problem: line => problem(line, 'subject'),
    render: (line, cell) => {
      const lookup = <span className="janso-entry-cell__lookup" {...cell.cellProps} aria-label={undefined} ref={cell.registerRef}>
        <SearchSelect label={cell.cellProps['aria-label']} hideLabel clearable={false} openOnFocus={false} scopeKey={line.kind}
          options={purchaseSubjectLookup(policy, line.kind) ? undefined : policy.subjects.filter(subject => subject.kind === line.kind)} loadOptions={purchaseSubjectLookup(policy, line.kind)} value={line.subject || null}
          selected={line.subject ? { id: line.subject, label: line.label } : null} disabled={cell.disabled}
          required
          placeholder={line.kind === 'ITEM' ? 'Find an item' : 'Find an expense account'} error={problem(line, 'subject')}
          onChange={(id, option) => { setActiveLine(line.key); dispatch({ type: 'subject', key: line.key, subject: policy.subjects.find(subject => subject.id === id && subject.kind === line.kind) ?? (id && option ? { id, label: option.label, meta: option.meta ?? '', kind: line.kind, unit: '' } : null) }); }} />
      </span>;
      const showBalance = activeLine === line.key && !!policy.stockCompany && !!line.subject;
      const showHistory = line.kind === 'ITEM' && !!line.subject && !!policy.stockCompany && !!policy.supplierHistoryAccess;
      const choice = <span className="janso-purchase-subject-choice">{lookup}{showBalance ? <PurchaseSelectionBalance company={policy.stockCompany!} kind={line.kind} subject={line.subject} postingDate={draft.postingDate} currency={policy.currency} warehouse={line.kind === 'ITEM' ? line.stock?.warehouseId : undefined} unit={line.unit} permitted={line.kind === 'ITEM' ? !!policy.balanceAccess?.stock : !!policy.balanceAccess?.ledger} /> : null}</span>;
      const history = showHistory ? <span className="janso-entry-cell__action"><PurchaseProductHistory key={`${policy.stockCompany}:${draft.supplier}:${line.subject}`} company={policy.stockCompany!} supplier={draft.supplier} supplierName={selectedSupplierName} product={line.subject} name={line.label || 'Product'} /></span> : null;
      // Outside the cell's own element: the grid reads Enter inside a cell as "next row", which would swallow the button's.
      const create = canCreateProduct && line.kind === 'ITEM'
        ? <span className="janso-entry-cell__action"><PurchaseProductCreateLink line={draft.lines.indexOf(line) + 1} disabled={cell.disabled} /></span>
        : onCreateAccount && line.kind === 'ACCOUNT'
          ? <span className="janso-entry-cell__action"><PurchaseQuickCreateButton label={`Create a new expense account for line ${draft.lines.indexOf(line) + 1}`} disabled={cell.disabled} onClick={() => onCreateAccount({ lineKey: line.key })} data-quick-create="account" /></span>
          : null;
      return history || create ? <span className="janso-entry-cell__with-action">{choice}{history}{create}</span> : choice;
    } });
  // A live account bill carries its own narration per line, so it is typed here rather than hidden behind line details.
  if (policy.live && !hasItems) columns.push({ key: 'description', label: 'Description', kind: 'text', placeholder: 'Defaults to the account name', value: line => line.description, problem: line => problem(line, 'description') });
  if (hasItems) {
    columns.push({ key: 'unit', label: 'Unit', kind: 'derived', value: line => line.kind === 'ITEM' ? line.unit || '—' : '—' });
    if (policy.stockCompany && draft.lines.some(line => line.kind === 'ITEM' && !!line.stock?.lotId)) columns.push({ key: 'batch', label: 'Batch', kind: 'custom', value: line => line.stock?.lotId ?? '',
      render: (line, cell) => <span {...cell.cellProps} ref={cell.registerRef}>{line.kind === 'ITEM' && line.stock?.lotId && policy.stockCompany
        ? <PurchaseBatchSummary company={policy.stockCompany} item={line.subject} batchId={line.stock.lotId} permitted={!!policy.canReadBatch} /> : '—'}</span> });
    for (const [key, label] of [['received', 'Receipt qty'], ['billed', 'Billed qty'], ['rate', 'Rate']] as const) {
      columns.push({ key, label, kind: key === 'rate' ? 'amount' : 'quantity', align: 'end', required: true,
        precision: key === 'rate' ? 4 : undefined,
        value: line => line.kind === 'ITEM' ? line[key] : '', readOnly: line => line.kind === 'ACCOUNT',
        requirePositive: key === 'billed', problem: line => problem(line, key) });
    }
  }
  // No discount column when the type forbids discounts: a column of read-only zeros says nothing.
  const plainBill = !!policy.live && policy.discountsAllowed === false && !hasItems;
  if (!plainBill) columns.push({ key: 'discount', label: 'Discount', kind: 'amount', align: 'end', value: line => line.discount,
    readOnly: () => policy.discountsAllowed === false,
    problem: line => problem(line, 'discount') });
  if (draft.mode !== 'ITEMS' || hasKinds) columns.push({ key: 'amount', label: plainBill ? 'Amount' : 'Base amount', kind: 'amount', precision: policy.live ? 4 : undefined, align: 'end', value: line => {
    if (line.kind === 'ACCOUNT') return line.amount;
    const amounts = purchaseLineAmounts(line);
    return amounts ? D.format(amounts.gross) : '';
  }, readOnly: line => line.kind === 'ITEM', problem: line => problem(line, 'amount') });
  if (!plainBill) columns.push({ key: 'net', label: 'Net amount', kind: 'derived', align: 'end', pin: 'end', value: line => {
    if (['received', 'billed', 'rate', 'amount', 'discount'].some(field => problem(line, field))) return '';
    const amounts = purchaseLineAmounts(line);
    return amounts ? money(D.format(amounts.net)) : '';
  } });

  return <section ref={panel} className="janso-entry-workspace__panel janso-entry-workspace__line-panel" aria-label="Purchase line entry" onFocusCapture={event => {
    const target = event.target as HTMLElement;
    const key = target.closest<HTMLElement>('[data-entry-row]')?.dataset.entryRow ?? target.closest<HTMLElement>('[data-purchase-mobile-line]')?.dataset.purchaseMobileLine;
    if (key) { lastFocusedLine.current = key; if (target.closest('[data-entry-col="subject"]')) setActiveLine(key); }
  }}>
    <div className="janso-entry-workspace__section-head"><div><h2>Bill lines</h2><p className="janso-entry-workspace__caption">{hasItems ? policy.live ? 'Enter the item and quantity, then open Line details to choose its warehouse, bin, batch and serials as needed.' : draft.details.receiptIntent === 'REFERENCE' ? 'Match billed quantities to existing receipts. Matched goods will not be received again.' : draft.details.receiptIntent === 'DEFERRED' ? 'Receipt quantities are planned for later. Billed quantities determine this bill.' : 'Receipt and billed quantities stay separate. Rates are entered manually.' : 'Enter expenses and services directly, without quantities.'}</p></div>
      <span className="janso-entry-workspace__caption">{draft.lines.filter(line => !isBlankPurchaseLine(line)).length} entered</span></div>
    {compact && (keepGrid || retainGrid) ? <div className="janso-entry-workspace__scroll-hint"><p>Finish editing in the grid, then switch to line cards. Scroll across to reach the field; your typed value is retained.</p><Button type="button" variant="ghost" disabled={keepGrid} onClick={() => { focusLine.current = draft.lines.find(line => line.key === lastFocusedLine.current)?.key ?? draft.lines[0]?.key; setRetainGrid(false); }}>Use line cards</Button></div> : null}
    {compact && !keepGrid && !retainGrid ? <PurchaseMobileLines draft={draft} policy={policy} dispatch={dispatch} problems={problems} disabled={disabled} onEdit={onEdit} /> : <>
    <EntryGrid<PurchaseLine> label="Purchase lines" rows={draft.lines} columns={columns} rowKey={line => line.key} disabled={disabled}
      readOnlyNote="Read-only line entry. You can review the saved quantities and amounts."
      onCellChange={(key, field, value) => dispatch({ type: 'line', key, patch: { [field]: value } })}
      onCellCommit={(key, field, value) => { if (field === 'received') dispatch({ type: 'receipt_commit', key, value }); }}
      onAddRow={() => dispatch({ type: 'add' })} onInsertRow={after => dispatch({ type: 'add', after })}
      onRemoveRow={key => dispatch({ type: 'remove', key })} onDuplicateRow={key => dispatch({ type: 'duplicate', key })}
      onMoveRow={(key, by) => dispatch({ type: 'move', key, by })} isRowBlank={isBlankPurchaseLine}
      onExpandRow={onDetails} expandLabel="Line and stock details" onCellUnstorable={onUnstorable}
      rowState={line => problems.some(entry => entry.lineKey === line.key) ? 'invalid' : undefined}
      rowNote={line => { const note = problems.find(entry => entry.lineKey === line.key); return note ? { message: note.message, tone: 'error' } : undefined; }} />
    <div className="janso-entry-workspace__grid-help"><span><kbd>Enter</kbd> next row · <kbd>Ctrl Enter</kbd> add line · <kbd>Alt Enter</kbd> details</span><span>{isTaxed(draft.tax) ? `Amounts in ${config.currency} · before GST, which Accounting calculates` : plainBill ? `Amounts in ${config.currency} · no tax on this bill` : `Net amounts in ${config.currency} · after line discount, before bill adjustments and tax`}</span></div>
    </>}
  </section>;
}
