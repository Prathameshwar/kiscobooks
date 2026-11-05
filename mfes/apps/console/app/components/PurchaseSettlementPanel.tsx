'use client';

import { Button, Checkbox, Select, TextField, useFormatters } from '@janso/ui';
import { purchaseWorkspacePreview } from '../lib/purchase-workspace';
import * as D from '../lib/fixed-decimal';
import type { PurchaseDetailEditorProps } from './PurchaseDetailEditor';

export function PurchaseSettlementPanel({ draft, policy, disabled, setDetails, error, number }: PurchaseDetailEditorProps) {
  const { money, date } = useFormatters(), preview = purchaseWorkspacePreview(draft), details = draft.details;
  const eligible = policy.details.advances.filter(advance => advance.supplier === draft.supplier && advance.currency === policy.currency);
  const accounts = policy.details.paymentAccounts.filter(account => account.currency === policy.currency && account.method === details.payment.method);
  const payment = (values: Partial<typeof details.payment>) => setDetails(current => ({ ...current, payment: { ...current.payment, ...values } }));
  return <>
    <p className="janso-entry-workspace__caption">Plan how this bill will be settled. No advance is applied and no payment is recorded by this preview.</p>
    <div className="janso-form-grid janso-entry-detail__pair">
      <div data-purchase-detail-field="termsDays"><TextField label="Credit days" inputMode="numeric" value={details.termsDays} disabled={disabled} maxLength={4}
        error={error('termsDays')} onChange={event => setDetails(current => ({ ...current, termsDays: event.target.value }))} /></div>
      <Select label="Credit terms basis" value={details.termsBasis} disabled={disabled}
        options={[{ value: 'INVOICE_DATE', label: 'Supplier invoice date' }, { value: 'POSTING_DATE', label: 'Posting date' }]}
        onChange={value => setDetails(current => ({ ...current, termsBasis: value as typeof current.termsBasis }))} />
    </div>
    <p className="janso-entry-detail__figure">Due date <strong>{preview.settlement.dueDate ? date(preview.settlement.dueDate) : '—'}</strong></p>
    <fieldset className="janso-entry-detail__group" data-purchase-detail-field="advances"><legend>Eligible advances · supplied balances</legend>
      {!eligible.length ? <p>No eligible example advances for this supplier and currency.</p> : null}
      {eligible.map(advance => {
        const selected = details.advances.find(entry => entry.id === advance.id);
        return <div key={advance.id} className="janso-entry-detail__group-row">
          <Checkbox checked={!!selected} disabled={disabled} hint={'Available ' + money(advance.available)}
            onChange={event => setDetails(current => ({ ...current, advances: event.target.checked ? [...current.advances, { id: advance.id, amount: advance.available }] : current.advances.filter(entry => entry.id !== advance.id) }))}>{advance.label}</Checkbox>
          {selected ? number(`advance-${advance.id}`, `Advance amount · ${advance.label}`, selected.amount, amount => setDetails(current => ({ ...current, advances: current.advances.map(entry => entry.id === advance.id ? { ...entry, amount } : entry) }))) : null}
        </div>;
      })}
      {details.advances.filter(selected => !eligible.some(advance => advance.id === selected.id)).map(selected => <div key={selected.id} className="janso-entry-detail__group-row"><p className="janso-error">A retained advance does not match this supplier or currency.</p>
        {!disabled ? <Button type="button" variant="ghost" onClick={() => setDetails(current => ({ ...current, advances: current.advances.filter(entry => entry.id !== selected.id) }))}>Remove ineligible advance</Button> : null}</div>)}
      {error('advances') ? <p className="janso-error" role="alert">{error('advances')}</p> : null}
    </fieldset>
    <fieldset className="janso-entry-detail__group"><legend>Proposed payment</legend>
      {number('paymentAmount', 'Payment to record', details.payment.amount, amount => payment({ amount }), { hint: 'An instruction only. The full bill total stays unchanged.' })}
      <div className="janso-form-grid janso-entry-detail__pair"><Select label="Payment method" value={details.payment.method} disabled={disabled}
        options={[{ value: 'BANK', label: 'Bank' }, { value: 'CASH', label: 'Cash' }]} onChange={method => payment({ method: method as typeof details.payment.method })} />
        <div data-purchase-detail-field="paymentAccount"><Select label="Payment account" value={details.payment.account} disabled={disabled}
          options={[{ value: '', label: 'Choose an account when paying' }, ...accounts.map(account => ({ value: account.id, label: account.label }))]}
          error={error('paymentAccount')} onChange={account => payment({ account })} /></div></div>
      <TextField label="Payment reference" value={details.payment.reference} disabled={disabled} maxLength={100} onChange={event => payment({ reference: event.target.value })} />
    </fieldset>
    <div className="janso-entry-detail__calculation"><p>Full bill total <strong>{preview.total === null ? '—' : money(D.format(preview.total))}</strong></p><p>Remaining if applied <strong>{preview.settlement.remaining === null ? '—' : money(D.format(preview.settlement.remaining))}</strong></p></div>
    {preview.total === null ? <p className="janso-entry-workspace__caption">Remaining balance cannot be calculated until bill-total evidence is available.</p> : null}
  </>;
}
