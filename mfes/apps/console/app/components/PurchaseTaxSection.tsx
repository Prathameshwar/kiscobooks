'use client';

import { Button, ExternalLinkIcon, Notice, Select, TextField } from '@janso/ui';
import { AccountingReference } from './AccountingConfigurationCommon';
import { defaultKey, REGISTRATION_TYPE_LABELS, rowTaxStatus, TAX_CHOICE_HINTS, TAX_CHOICE_LABELS, type PurchaseTaxDraft, type PurchaseTaxFacts, type SupplierGst, type TaxResolution } from '../lib/purchase-tax';
import type { TaxFactFailures } from '../lib/use-purchase-tax-facts';

/** One expense account on the bill, and the lines it sits on. */
export type TaxAccount = { id: string; label: string; lines: readonly number[] };

const registration = (row: { number: string; state: string }) => [row.number || 'No number', row.state.replace(/^IN-/, '')].filter(Boolean).join(' · ');
const NEW_TAB = <><ExternalLinkIcon size={16} aria-hidden="true" /><span className="janso-visually-hidden"> (opens in a new tab)</span></>;

/**
 * How GST applies to the bill, under its "This bill carries no tax" box: how the supplier charged it, which of the
 * company's registrations it is under, where the service is received and when it was completed, and — account by
 * account, the way the bill is entered — what each expense account's tax setup says. Nothing here is a rate or an
 * amount: Accounting calculates those from the setup, and the calculation card shows them once it has.
 */
export function PurchaseTaxSection({ company, tax, resolution, facts, failures, loading, accounts, supplierId, editable, locked, showProblems, canManage, onChange, onReload }: {
  company: string; tax: PurchaseTaxDraft; resolution: TaxResolution; facts: PurchaseTaxFacts; failures: TaxFactFailures; loading: boolean;
  accounts: readonly TaxAccount[]; supplierId: string; editable: boolean; locked: boolean; showProblems: boolean; canManage: boolean;
  onChange: (patch: Partial<PurchaseTaxDraft>) => void; onReload: () => void;
}) {
  const disabled = !editable || locked;
  const problem = (field: string) => showProblems ? resolution.problems.find(entry => entry.field === field)?.message : undefined;
  const choice = tax.choice === 'REVERSE' ? 'REVERSE' : 'FORWARD';
  const supplier = resolution.supplier;
  const failure = failures.companies ?? failures.supplier ?? failures.defaults;
  return <div className="janso-purchase-tax" role="group" aria-label="GST on this bill">
    <p className="janso-purchase-tax__lede">Accounting works out the GST from each expense account’s tax setup. Tell it how the supplier charged it and which registration the bill is under.</p>
    {failure ? <Notice tone="warning" title="Tax details could not be read"><p>{failure}</p><Button variant="ghost" disabled={locked} onClick={onReload}>Read the tax details again</Button></Notice> : null}
    <div className="janso-purchase-tax__fields">
      <div data-purchase-field="taxChoice"><Select label="How GST is charged" required value={choice} disabled={disabled}
        options={(['FORWARD', 'REVERSE'] as const).map(value => ({ value, label: TAX_CHOICE_LABELS[value] }))} hint={TAX_CHOICE_HINTS[choice]}
        onChange={value => onChange({ choice: value === 'REVERSE' ? 'REVERSE' : 'FORWARD' })} /></div>
      <div data-purchase-field="companyRegistration">{resolution.companies.length > 1 || !resolution.company && resolution.companies.length > 0
        ? <Select label="Your GST registration" required value={resolution.company?.id ?? ''} disabled={disabled} error={problem('companyRegistration')}
          options={[...(resolution.company ? [] : [{ value: '', label: 'Choose a registration' }]), ...resolution.companies.map(row => ({ value: row.id, label: registration(row) + (row.primary ? ' · primary' : '') }))]}
          onChange={value => onChange({ companyRegistration: value, placeOfSupply: '' })} />
        : <dl className="janso-purchase-static"><dt className="janso-purchase-static__label">Your GST registration</dt>
          <dd className="janso-purchase-static__value">{resolution.company ? registration(resolution.company) : facts.companies === null && !failures.companies ? 'Reading…' : 'None in force'}</dd>
          {problem('companyRegistration') ? <dd className="janso-error" role="alert">{problem('companyRegistration')}</dd> : <dd className="janso-purchase-static__hint">The bill is raised under this registration.</dd>}</dl>}</div>
      <div data-purchase-field="placeOfSupply"><AccountingReference company={company} source="states" filters="country_code=IN" label="Place of supply" required value={resolution.place || null} disabled={disabled}
        error={problem('placeOfSupply')} hint={tax.placeOfSupply ? undefined : 'Follows your registration’s state until you choose another.'} onChange={value => onChange({ placeOfSupply: value ?? '' })} /></div>
      <div data-purchase-field="completionDate"><TextField label="Service completion date" required type="date" value={tax.completionDate || resolution.completion} disabled={disabled}
        error={problem('completionDate')} hint={tax.completionDate ? undefined : 'Follows the supplier invoice date until you choose another.'} onChange={event => onChange({ completionDate: event.target.value })} /></div>
      <div data-purchase-field="supplierRegistration">{resolution.supplierOptions.length > 1
        ? <Select label="Supplier’s GST registration" required value={supplier.kind === 'ready' ? supplier.registration.id : ''} disabled={disabled} error={problem('supplierRegistration')}
          options={[...(supplier.kind === 'ready' ? [] : [{ value: '', label: 'Choose the one on the invoice' }]), ...resolution.supplierOptions.map((row: SupplierGst) => ({ value: row.id, label: registration(row) }))]} onChange={value => onChange({ supplierRegistration: value })} />
        : <dl className="janso-purchase-static"><dt className="janso-purchase-static__label">Supplier’s GST registration</dt>
          <dd className="janso-purchase-static__value">{supplier.kind === 'ready' ? registration(supplier.registration)
            : supplier.kind === 'unselected' ? 'Choose the supplier first' : supplier.kind === 'unread' ? (failures.supplier ? 'Could not be read' : 'Reading…') : supplier.kind === 'none' ? 'None on record' : supplier.kind === 'ineligible' ? (REGISTRATION_TYPE_LABELS[supplier.type] ?? 'Not regular') : 'Choose the one on the invoice'}</dd>
          {supplier.kind === 'unread' && problem('supplierRegistration') ? <dd className="janso-error" role="alert">{problem('supplierRegistration')}</dd> : null}
          <dd className="janso-purchase-static__hint">{supplier.kind === 'ready' ? `${REGISTRATION_TYPE_LABELS[supplier.registration.type] ?? supplier.registration.type} registration, read from the supplier’s tax registrations.` : 'Read from the supplier’s tax registrations.'}</dd></dl>}</div>
    </div>
    {supplier.kind === 'none' || supplier.kind === 'ineligible' ? <div data-purchase-field="supplierRegistration"><Notice tone="warning" title={supplier.kind === 'none' ? 'The supplier has no GST registration on record' : 'GST can only be recorded for a regular GST supplier'}>
      <p>{resolution.problems.find(entry => entry.field === 'supplierRegistration')?.message}</p>
      {canManage && supplierId ? <p><a className="janso-link" href={'/accounting/party-tax-registrations/new?party_id=' + supplierId} target="_blank" rel="noopener noreferrer">Open the supplier’s tax registrations{NEW_TAB}</a></p> : null}
      <Button variant="ghost" disabled={locked} onClick={onReload}>Read the tax details again</Button></Notice></div> : null}
    {accounts.length ? <section aria-label="Tax by expense account" className="janso-purchase-tax__accounts">
      <h3>Tax by expense account</h3>
      <ul className="janso-purchase-tax__lines">{accounts.map(account => {
        const status = rowTaxStatus(tax.choice, facts.defaults.get(defaultKey(account.id, resolution.completion)));
        return <li key={account.id} data-tone={status.tone}>
          <span className="janso-purchase-tax__account"><strong>{account.label}</strong><span className="janso-purchase-tax__where">{account.lines.length === 1 ? 'Line ' : 'Lines '}{account.lines.join(', ')}</span></span>
          <span className="janso-purchase-tax__status">{status.text}{status.fix && canManage ? <> <a className="janso-link" href={'/accounting/account-tax-defaults/new?account_id=' + account.id} target="_blank" rel="noopener noreferrer">Set its tax default{NEW_TAB}</a></> : null}</span>
        </li>;
      })}</ul>
    </section> : null}
    {loading && !failure ? <p className="janso-purchase-tax__note" role="status">Reading the tax setup…</p> : null}
  </div>;
}
