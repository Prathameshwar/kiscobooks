'use client';
import { useEffect, useRef, useState } from 'react';
import type { components } from '@janso/api-client/accounting';
import { Button, Card, CardBody, Checkbox, FormActions, Notice, ReviewList, SectionHeader, Skeleton, TextField, businessToday, useDisplayConfig, useFormatters } from '@janso/ui';
import { useServiceCommand, useServiceRead, type ServicePage } from '../lib/service-resource';
import { stockBase, stockRequest, useStockFields } from '../lib/stock';
import { trackingId } from '../lib/stock-tracking-resources';
import { validMasterDate } from '../lib/catalog-masters';
import { AccountingFailure, AccountingReference } from './AccountingConfigurationCommon';
import { AccessFocusErrors, useAccessDraft } from './AccessCommon';

type Policy = components['schemas']['StockAccountPolicyDetail'];
type PolicyInput = components['schemas']['StockAccountPolicyCreate'];
const accounts = [{ key: 'inventory_account_id', label: 'Inventory asset account', hint: 'Asset: carries the value of company-owned inventory.' }, { key: 'receipt_clearing_account_id', label: 'Goods received clearing', hint: 'Liability: accrues goods received before the supplier invoice.' }, { key: 'dispatch_clearing_account_id', label: 'Goods dispatched clearing', hint: 'Asset: retains carrying value until the customer invoice.' }, { key: 'opening_offset_account_id', label: 'Opening balance offset', hint: 'Equity: offsets a combined stock and GL opening.' }, { key: 'variance_account_id', label: 'Stock variance account', hint: 'Expense: records reviewed differences on linked supplier returns.' }] as const;
type AccountKey = typeof accounts[number]['key'];
const blank = Object.fromEntries(accounts.map(account => [account.key, ''])) as Record<AccountKey, string>;

export function StockAccountConfiguration({ company, canConfigure, generation, correctablePolicyId, onSaved }: { company: string; canConfigure: boolean; generation?: number; correctablePolicyId?: string | null; onSaved: () => void }) {
  const base = stockBase(company), metadata = useStockFields(company, 'account-policies'), display = useDisplayConfig(), format = useFormatters();
  const history = useServiceRead<ServicePage<components['schemas']['StockAccountPolicyListItem']>>(base + '/account-policies?limit=1&sort=-id', stockRequest);
  const latestId = history.data?.items[0]?.id;
  const latest = useServiceRead<Policy>(latestId ? base + '/account-policies/' + latestId : undefined, stockRequest, row => {
    if (row.company_id !== company || row.id !== latestId) throw { status: 502, message: 'Stock account ownership could not be verified.' };
  });
  const [values, setValues] = useState(blank), [date, setDate] = useState(businessToday(display.timezone)), [reason, setReason] = useState(''), [dirty, setDirty] = useState(false), [saved, setSaved] = useState(false), [errors, setErrors] = useState<Record<string, string>>({});
  const hydrated = useRef<string | null>(null), command = useServiceCommand(stockRequest, 'stock accounts'), guard = useAccessDraft(dirty || command.uncertain, command.pending);
  const retained = useRef<PolicyInput | null>(null);
  const [correctUnused, setCorrectUnused] = useState(false);
  const field = (key: string) => metadata.data?.fields.find(entry => entry.key === key);
  const writable = (key: string) => canConfigure && field(key)?.writable && field(key)?.readable && field(key)?.visible;
  useEffect(() => {
    if (!latest.data || hydrated.current === latest.data.id || dirty || command.pending || command.uncertain) return;
    hydrated.current = latest.data.id;
    setValues(Object.fromEntries(accounts.map(account => [account.key, latest.data?.[account.key] ?? ''])) as Record<AccountKey, string>);
  }, [latest.data, dirty, command.pending, command.uncertain]);
  function changed() { setDirty(true); setSaved(false); setErrors({}); if (!command.uncertain) command.clear(); }
  async function submit() {
    if (!canConfigure || command.pending || generation == null) return;
    const problems: Record<string, string> = {};
    for (const account of accounts) if (!trackingId.test(values[account.key]) || !writable(account.key)) problems[account.key] = 'Choose an authorised account for this purpose.';
    if (new Set(Object.values(values)).size !== accounts.length) problems.inventory_account_id = 'Use a different account for each purpose.';
    if (!validMasterDate(date)) problems.valid_from = 'Enter a valid effective date.';
    if (reason.trim().length < 3) problems.reason = 'Explain why these stock accounts are being configured.';
    setErrors(problems); if (Object.keys(problems).length) return;
    if (!command.uncertain) retained.current = { ...values, valid_from: date, reason: reason.trim(), expected_generation: generation, ...(correctUnused && correctablePolicyId === latestId ? { correct_unused_id: latestId } : {}) };
    const result = await command.execute<Policy>({ path: base + '/account-policies', method: 'POST', body: retained.current }, row => {
      if (row.company_id !== company || !trackingId.test(row.id)) throw { status: 502, message: 'The saved stock accounts could not be verified.' };
    });
    if (result) { setDirty(false); setSaved(true); setReason(''); history.refresh(); onSaved(); }
  }
  const locked = command.pending || command.uncertain;
  return <div className="janso-flow">
    <AccountingFailure failure={metadata.failure ?? history.failure ?? latest.failure} retry={() => { metadata.refresh(); history.refresh(); latest.refresh(); }} />
    <AccountingFailure failure={command.failure} write retry={command.uncertain ? undefined : () => { command.clear(); onSaved(); }} />
    {saved && <Notice tone="success">Stock accounts saved. The new mapping applies from {format.date(date)}.</Notice>}
    {metadata.loading || history.loading || latest.loading ? <Skeleton /> : <>
      <Card><CardBody><SectionHeader title="Latest published stock accounts" description="The effective date determines which mapping a posting uses, including scheduled changes." />{latest.data ? <ReviewList items={[{ label: 'Effective from', value: latest.data.valid_from ? format.date(latest.data.valid_from) : 'Protected' }, ...accounts.filter(account => field(account.key)?.readable && field(account.key)?.visible).map(account => ({ label: account.label, value: latest.data?.[account.key] ? <a className="janso-link" href={'/accounting/accounts/' + latest.data[account.key]}>View account</a> : 'Protected' }))]} /> : <Notice>Stock accounts have not been configured. Receipt, opening and issue postings require an explicit mapping.</Notice>}</CardBody></Card>
      {canConfigure && <form onSubmit={event => { event.preventDefault(); void submit(); }}>
        <AccessFocusErrors fields={{ ...command.failure?.fields, ...errors }} />
        <fieldset disabled={locked} className="janso-fieldgroup janso-flow"><Card><CardBody><div className="janso-flow"><SectionHeader title={latest.data ? 'Publish successor accounts' : 'Configure stock accounts'} description="Existing postings keep their original accounts. New mappings cannot rewrite a used date." />
          {latestId && correctablePolicyId === latestId && <Checkbox checked={correctUnused} onChange={event => { setCorrectUnused(event.target.checked); changed(); }} hint="Available only before this mapping has been used or stock posting has been prepared. The correction is audited. An initial mapping can be dated back to the opening date.">Correct the unused mapping</Checkbox>}
          {field('valid_from')?.readable && field('valid_from')?.visible && <TextField label="Effective from" type="date" value={date} required disabled={!writable('valid_from')} onChange={event => { setDate(event.target.value); changed(); }} error={errors.valid_from ?? command.failure?.fields?.valid_from} />}
          <div className="janso-form-grid">{accounts.filter(account => field(account.key)?.readable && field(account.key)?.visible).map(account => <AccountingReference key={account.key} company={company} source="accounts" filters="kind=GENERAL" label={account.label} hint={account.hint} value={values[account.key] || null} onChange={value => { setValues(current => ({ ...current, [account.key]: value ?? '' })); changed(); }} required disabled={!writable(account.key)} error={errors[account.key] ?? command.failure?.fields?.[account.key]} />)}</div>
          {field('reason')?.readable && field('reason')?.visible && <TextField label="Reason for configuration" value={reason} required maxLength={500} disabled={!writable('reason')} onChange={event => { setReason(event.target.value); changed(); }} error={errors.reason ?? command.failure?.fields?.reason} />}
        </div></CardBody></Card></fieldset>
        <FormActions><Button type="submit" loading={command.pending} disabled={generation == null || command.pending || !dirty || !writable('valid_from') || !writable('reason') || accounts.some(account => !writable(account.key))}>{command.uncertain ? 'Retry the same save' : 'Save stock accounts'}</Button></FormActions>
      </form>}
    </>}{guard.confirmation}
  </div>;
}
