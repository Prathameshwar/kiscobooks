'use client';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Button, Card, CardBody, Notice, SearchSelect, SectionHeader, TextField } from '@janso/ui';
import type { FieldSet } from '../lib/voucher-fields';
import { nativeProperties, purchaseAvailability, purchaseLookup, purchaseSource, supplierPayables, type PurchaseDraft, type PurchaseSource } from '../lib/purchase-entry';
import { payableCountIssue } from '../lib/purchase-workspace';

export function PurchaseInvoice({ company, currency, metadata, value, onChange, onPendingChange, disabled, errors = {} }: { company: string; currency: string; metadata: FieldSet; value: PurchaseDraft; onChange: (draft: PurchaseDraft) => void; onPendingChange: (pending: boolean) => void; disabled: boolean; errors?: Record<string, string> }) {
  const [busy, setBusy] = useState(false), [failure, setFailure] = useState('');
  const mounted = useRef(true);
  const fields = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!disabled && Object.keys(errors).length) fields.current?.querySelector<HTMLElement>('[aria-invalid="true"], [data-validation-summary]')?.focus();
  }, [errors, disabled]);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const suppliers = useMemo(() => purchaseLookup(company, 'suppliers'), [company]);
  const expenses = useMemo(() => purchaseLookup(company, 'expenses'), [company]);
  const unavailable = purchaseAvailability(metadata), locked = disabled || busy;
  const native = nativeProperties(metadata.native.properties?.invoice);
  async function select(resource: 'suppliers' | 'payables' | 'expenses', id: string | null, apply: (source: PurchaseSource | null) => void) {
    setFailure(''); if (!id) { apply(null); return; }
    apply(null); setBusy(true); onPendingChange(true);
    try { const source = await purchaseSource(company, resource, id, value.party?.id); if (mounted.current) apply(source); }
    catch (error) { if (mounted.current) setFailure(error instanceof Error ? error.message : 'Unable to verify the purchase reference.'); }
    finally { if (mounted.current) { setBusy(false); onPendingChange(false); } }
  }
  /** Choosing the supplier chooses its payable account: a supplier has exactly one, so there is no second picker. */
  async function chooseSupplier(id: string | null) {
    setFailure(''); onChange({ ...value, party: null, payable: null }); if (!id) return;
    setBusy(true); onPendingChange(true);
    try {
      const party = await purchaseSource(company, 'suppliers', id), accounts = await supplierPayables(company, party.id);
      if (!mounted.current) return;
      onChange({ ...value, party, payable: accounts.length === 1 ? accounts[0]! : null });
      const issue = payableCountIssue(accounts.length); if (issue) setFailure(issue);
    } catch (error) { if (mounted.current) setFailure(error instanceof Error ? error.message : 'Unable to verify the purchase reference.'); }
    finally { if (mounted.current) { setBusy(false); onPendingChange(false); } }
  }
  const selected = (source: PurchaseSource | null) => source ? { id: source.id, label: source.label } : undefined;
  return <Card><CardBody><div className="janso-flow" ref={fields}>
    <SectionHeader title="Account purchase bill" description="Record an untaxed supplier account bill. Preview and accept its calculation before submitting it for approval." />
    {unavailable ? <Notice tone="warning">{unavailable} <a className="janso-link" href="/masters/voucher-types">Review voucher types</a></Notice> : <fieldset className="janso-fieldgroup janso-flow" disabled={locked}>
      {busy && <p role="status">Verifying purchase reference</p>}
      {failure && <Notice tone="danger">{failure}</Notice>}
      <div className="janso-form-grid">
        <SearchSelect label="Supplier" error={errors.party ?? errors.payable} value={value.party?.id ?? null} selected={selected(value.party)} loadOptions={suppliers} scopeKey={company} minQueryLength={0} disabled={locked} onChange={id => void chooseSupplier(id)} />
        <TextField label="Supplier invoice reference" error={errors.reference} value={value.reference} required maxLength={100} onChange={event => onChange({ ...value, reference: event.target.value })} />
        <TextField label="Payment due date" error={errors.dueDate} type="date" value={value.dueDate} required onChange={event => onChange({ ...value, dueDate: event.target.value })} />
        {native.supplier_declared_total && <TextField label={'Supplier-declared total (' + currency + ')'} error={errors.declaredTotal} value={value.declaredTotal} inputMode="decimal" disabled={locked || native.supplier_declared_total.readOnly} hint="Optional. The calculated amount must agree with the supplier's bill under the configured policy." onChange={event => onChange({ ...value, declaredTotal: event.target.value })} />}
      </div>
      {errors.supplies && <p role="alert" tabIndex={-1} data-validation-summary>{errors.supplies}</p>}
      {value.supplies.map((line, index) => <fieldset className="janso-fieldgroup janso-flow" key={line.key}><legend>Purchase line {index + 1}</legend>
        <div className="janso-form-grid">
          <SearchSelect error={errors[line.key + '.account']} label={'Expense account ' + (index + 1)} value={line.account?.id ?? null} selected={selected(line.account)} loadOptions={expenses} scopeKey={company} minQueryLength={0} disabled={locked} onChange={id => void select('expenses', id, account => onChange({ ...value, supplies: value.supplies.map(row => row.key === line.key ? { ...row, account } : row) }))} />
          <TextField error={errors[line.key + '.description']} label={'Purchase description ' + (index + 1)} value={line.description} required maxLength={1000} onChange={event => onChange({ ...value, supplies: value.supplies.map(row => row.key === line.key ? { ...row, description: event.target.value } : row) })} />
          <TextField error={errors[line.key + '.amount']} label={'Purchase amount ' + (index + 1) + ' (' + currency + ')'} value={line.amount} required inputMode="decimal" onChange={event => onChange({ ...value, supplies: value.supplies.map(row => row.key === line.key ? { ...row, amount: event.target.value } : row) })} />
        </div>
        <Button type="button" variant="ghost" onClick={() => onChange({ ...value, supplies: value.supplies.filter(row => row.key !== line.key) })}>Remove purchase line {index + 1}</Button>
      </fieldset>)}
      <Button type="button" variant="ghost" disabled={locked || value.supplies.length >= Math.min(metadata.configuration.policy.max_lines ?? 200, 200)} onClick={() => onChange({ ...value, supplies: [...value.supplies, { key: crypto.randomUUID(), account: null, description: '', amount: '' }] })}>Add purchase line</Button>
      <Notice>Goods and tax-bearing purchases require their corresponding purchase workflow and configuration.</Notice>
    </fieldset>}
  </div></CardBody></Card>;
}
