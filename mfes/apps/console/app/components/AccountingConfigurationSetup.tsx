'use client';
import { useState } from 'react';
import type { components } from '@janso/api-client/accounting';
import { Button, Card, CardBody, CardHeader, ConfirmDialog, Notice, PageHeader, ReviewList, Select } from '@janso/ui';
import { accountingRequest, assertAccountingRecord, useAccountingCommand, useAccountingList } from '../lib/accounting-configuration';
import { accountingBack, accountingResource, accountingUUID, type AccountingRecord } from '../lib/accounting-configuration-resources';
import { requestFailure, type RequestFailure } from '../lib/service-call';
import { useAccessDraft } from './AccessCommon';
import { AccountingFailure, AccountingLoading, AccountingNavigation, AccountingReference } from './AccountingConfigurationCommon';

type Preview = components['schemas']['TemplatePreview'];
type Result = components['schemas']['TemplateResult'];
export function AccountingConfigurationSetup({ company, canManage, returnTo }: { company: string; canManage: boolean; returnTo?: string }) {
  const config = accountingResource('accounting-setup')!, setup = useAccountingList(company, config), command = useAccountingCommand();
  const [business, setBusiness] = useState(true), [registration, setRegistration] = useState<string | null>(null), [component, setComponent] = useState('SGST');
  const [preview, setPreview] = useState<Preview | null>(null), [reviewSelection, setReviewSelection] = useState<Record<string, unknown> | null>(null), [previewBusy, setPreviewBusy] = useState(false), [previewError, setPreviewError] = useState<RequestFailure | null>(null), [reviewing, setReviewing] = useState(false), [message, setMessage] = useState(''), [operation, setOperation] = useState<'initialize' | 'install' | null>(null);
  const guard = useAccessDraft(reviewing || command.uncertain, command.pending || previewBusy), back = accountingBack(returnTo), selection = { business_accounts: business, ...(registration ? { gst_registration_id: registration, local_component: component } : {}) };
  function clear() { if (command.pending || command.uncertain) return; setPreview(null); setReviewSelection(null); setPreviewError(null); setMessage(''); command.clear(); }
  async function initialize() {
    if (!canManage || command.pending || command.uncertain && operation !== 'initialize') return;
    setOperation('initialize');
    const saved = await command.execute<AccountingRecord>({ path: `/v1/companies/${company}/accounting-setup/initialize`, method: 'POST', body: {} }, value => assertAccountingRecord(value, company));
    if (saved) { setup.first(); setMessage('Company Accounting setup initialized. Review the chart before installing it.'); }
  }
  async function review() {
    if (!canManage || previewBusy || command.pending) return;
    if (command.uncertain && operation === 'install') { setReviewing(true); return; }
    if (command.uncertain) return;
    setPreviewBusy(true); setPreviewError(null); setPreview(null); command.clear();
    try {
      const value = await accountingRequest<Preview>({ path: `/v1/companies/${company}/accounting-setup/preview`, method: 'POST', body: selection });
      if (!value.version || !/^[0-9a-f]{64}$/i.test(value.content_hash) || !Array.isArray(value.groups) || !Array.isArray(value.accounts) || !Array.isArray(value.conflicts)) throw { status: 502, message: 'The chart review could not be verified.' };
      setPreview(value); setReviewSelection(selection); setReviewing(true);
    } catch (error) { setPreviewError(requestFailure(error, 'Accounting setup')); } finally { setPreviewBusy(false); }
  }
  async function install() {
    if (preview?.conflicts?.length) { setReviewing(false); return; }
    if (!canManage || !preview || !reviewSelection || preview.conflicts?.length || command.pending) return;
    if (command.blocked && !command.uncertain) { clear(); setReviewing(false); return; }
    setOperation('install');
    const value = await command.execute<Result>({ path: `/v1/companies/${company}/accounting-setup/install`, method: 'POST', body: reviewSelection }, result => { if (!accountingUUID.test(result.installation_id) || !Number.isSafeInteger(result.groups_created) || !Number.isSafeInteger(result.accounts_created)) throw { status: 502, message: 'The chart installation result could not be verified.' }; });
    if (value) { setReviewing(false); setPreview(null); setup.first(); setMessage(`Chart installed: ${value.groups_created} groups and ${value.accounts_created} accounts created; ${value.groups_updated ?? 0} groups updated.`); }
  }
  return <div className="janso-page"><AccountingNavigation title="Company Accounting setup" back={back} onLeave={guard.leave} /><PageHeader title="Company Accounting setup" lede="Initialize native books, then review and install the chart required for account configuration." /><AccountingFailure failure={setup.failure} retry={setup.first} />{setup.loading ? <AccountingLoading /> : !setup.failure && <Card><CardHeader title="Setup status" /><CardBody>{setup.data?.items.length ? <ReviewList items={[{ label: 'Base currency', value: String(setup.data.items[0].base_currency ?? 'Not readable') }, { label: 'Metadata version', value: String(setup.data.items[0].metadata_version ?? 'Not readable') }]} /> : <Notice>Accounting setup has not been initialized for this company.</Notice>}{canManage && (!setup.data?.items.length || command.uncertain && operation === 'initialize') && <Button onClick={() => void initialize()} loading={command.pending} disabled={command.uncertain && operation !== 'initialize'}>{command.uncertain ? 'Retry same initialization' : 'Initialize company Accounting'}</Button>}</CardBody></Card>}
    {message && <Notice tone="success">{message}</Notice>}<AccountingFailure failure={command.failure} write /><AccountingFailure failure={previewError} />
    <Card><CardHeader title="Chart selection" subtitle="Existing identities and names are preserved. Used or incompatible classifications block unsafe upgrades." /><CardBody><div className="janso-form-grid"><Select label="Business accounts" value={String(business)} options={[{ value: 'true', label: 'Include business accounts' }, { value: 'false', label: 'Groups only' }]} disabled={!canManage || command.blocked || previewBusy} onChange={value => { clear(); setBusiness(value === 'true'); }} /><AccountingReference company={company} source="identity:tax-registrations" value={registration} label="Optional GST registration" disabled={!canManage || command.blocked || previewBusy} onChange={value => { clear(); setRegistration(value); }} />{registration && <Select label="Local GST component" value={component} options={[{ value: 'SGST', label: 'SGST' }, { value: 'UTGST', label: 'UTGST' }]} disabled={command.blocked || previewBusy} onChange={value => { clear(); setComponent(value); }} />}</div>{!canManage && <Notice>Company Accounting setup manage permission is required to initialize or install a chart.</Notice>}<div className="janso-form-actions"><Button onClick={() => void review()} loading={previewBusy} disabled={!canManage || command.pending || command.uncertain && operation !== 'install'}>{command.uncertain && operation === 'install' ? 'Recover chart installation' : 'Review chart installation'}</Button></div></CardBody></Card>
    <Notice>Installation checks the current chart, company registrations and field permissions again. Conflicts block the operation. It does not create posted balances.</Notice>
    <ConfirmDialog open={reviewing} title={preview?.conflicts?.length ? 'Chart conflicts require attention' : 'Install the reviewed chart?'} confirmLabel={preview?.conflicts?.length ? 'Close review' : command.uncertain ? 'Retry same chart installation' : command.blocked ? 'Review again' : 'Install chart'} busy={command.pending} onCancel={() => { if (!command.pending) setReviewing(false); }} onConfirm={() => void install()}>{preview && <><ReviewList items={[{ label: 'Version', value: preview.version }, { label: 'Groups', value: String(preview.groups.length) }, { label: 'Accounts', value: String(preview.accounts.length) }, { label: 'Current installation', value: preview.installed ? 'Installed; review upgrade' : 'New installation' }]} /><p>{preview.groups.join(', ')}</p><p>{preview.accounts.join(', ')}</p>{(preview.conflicts ?? []).map(conflict => <Notice key={conflict} tone="danger">{conflict}</Notice>)}<AccountingFailure failure={command.failure} write /></>}</ConfirmDialog>{guard.confirmation}</div>;
}
