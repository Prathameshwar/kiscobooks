'use client';
import { useEffect, useState } from 'react';
import { Button, Notice, PageHeader, PageNavigation, TextField } from '@janso/ui';
import type { components } from '@janso/api-client/vouchers';
import { productFieldRequest as request } from '../lib/product-fields';
import { voucherCommandRequest, type Choice, type FieldSet } from '../lib/voucher-fields';
import { voucherReferenceLabels } from '../lib/voucher-reference-labels';
import { editableDraft, purchaseDraftFromCapture, replacePurchaseDraft } from '../lib/voucher-draft-edit';
import { PurchaseValidationError, type PurchaseDraft } from '../lib/purchase-entry';
import { useServiceCommand, useServiceDestination } from '../lib/service-resource';
import { useAccessDraft } from './AccessCommon';
import { VoucherMoney, type MoneyInput } from './VoucherMoney';
import { PurchaseInvoice } from './PurchaseInvoice';
import { VoucherSummary } from './VoucherSummary';
import { withReturn } from '../lib/operate-navigation';

type Voucher = components['schemas']['VoucherDetail'];
type Capture = components['schemas']['VoucherInput'];
type Loaded = { voucher: Voucher; metadata: FieldSet; content: Capture; accounts: Choice[]; purchase: PurchaseDraft | null };
export function VoucherDraftEditor({ company, voucherId, typeId, currency, returnTo }: { company: string; voucherId: string; typeId: string; currency: string; returnTo?: string }) {
  const reviewHref = withReturn('/vouchers/' + voucherId, returnTo);
  const [loaded, setLoaded] = useState<Loaded | null>(null), [failure, setFailure] = useState(''), [loading, setLoading] = useState(true);
  const [money, setMoney] = useState<MoneyInput | null>(null), [purchase, setPurchase] = useState<PurchaseDraft | null>(null), [narration, setNarration] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({}), [purchaseBusy, setPurchaseBusy] = useState(false), [dirty, setDirty] = useState(false);
  const command = useServiceCommand(voucherCommandRequest, 'voucher draft'), destination = useServiceDestination(command.pending);
  const guard = useAccessDraft(dirty || command.uncertain, command.pending), locked = loading || command.pending || command.uncertain || purchaseBusy;
  useEffect(() => {
    const controller = new AbortController(); setLoaded(null); setLoading(true); setFailure('');
    async function load() {
      const base = `/v1/companies/${company}`;
      const voucher = await request<Voucher>('vouchers', 'GET', `${base}/vouchers/${voucherId}`, undefined, undefined, controller.signal);
      if (voucher.company_id !== company || voucher.id !== voucherId || voucher.status !== 'DRAFT' || !voucher.document_date) throw new Error('Only a readable draft for this company can be edited.');
      const query = new URLSearchParams({ date: voucher.document_date, ...(voucher.posting_date ? { posting_date: voucher.posting_date } : {}), ...(voucher.class_id ? { class_id: voucher.class_id } : {}) });
      const metadata = await request<FieldSet>('vouchers', 'GET', `${base}/voucher-types/${typeId}/field-set?${query}`, undefined, undefined, controller.signal);
      const content = editableDraft(company, voucherId, voucher, metadata), accounts: Choice[] = [], names: Record<string, string> = {};
      const targets = [...new Map([
        ...(content.financial?.accounts ?? []).map(row => ['accounts', row.account_id]),
        ...(content.invoice?.supplies ?? []).map(row => ['accounts', row.account_id]),
        ...(content.invoice?.party_account_id ? [['accounts', content.invoice.party_account_id]] : []),
        ...(content.parties ?? []).map(row => ['parties', row.party_id]),
      ].map(([resource, id]) => [resource + '/' + id, { resource, id }])).values()].slice(0, 200);
      const labels=await voucherReferenceLabels(company,targets,controller.signal);
      for(const target of targets){
        const row=labels.get(target.resource+'/'+target.id);
        if(row){names[target.id]=row.name??row.code??target.id;if(target.resource==='accounts')accounts.push(row);}
      }
      if (controller.signal.aborted) return;
      const purchase = content.invoice ? purchaseDraftFromCapture(company, content, names) : null;
      setLoaded({ voucher, metadata, content, accounts, purchase }); setPurchase(purchase); setMoney(content.financial ?? null); setNarration(content.narration ?? ''); setDirty(false);
    }
    void load().catch(error => { if (!controller.signal.aborted) setFailure(error instanceof Error ? error.message : 'Unable to load draft'); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [company, voucherId, typeId]);
  return <section className="janso-page">
    <PageNavigation back={{ href: reviewHref, label: 'voucher review' }} onNavigate={guard.leave} />
    <PageHeader title="Edit voucher draft" lede="Update the saved draft. Its type, dates and captured source versions remain pinned until a reference is explicitly replaced." />
    {loading && <p role="status">Loading draft and entry fields</p>}
    {failure && <Notice tone="warning">{failure}</Notice>}
    {loaded && <>
      <VoucherSummary company={company} voucher={loaded.voucher} />
      <form className="janso-flow" noValidate={!!purchase} onSubmit={event => { event.preventDefault(); void (async () => {
        setErrors({}); setFailure('');
        try {
          const content = { ...loaded.content, narration };
          if (purchase) {
            Object.assign(content, replacePurchaseDraft(company, loaded.content, purchase, loaded.metadata));
          } else content.financial = money;
          const result = await command.execute<Voucher>({ method: 'PUT', path: `/v1/companies/${company}/vouchers/${voucherId}`, body: { expected_version: loaded.voucher.row_version, content } }, row => {
            if (row.id !== voucherId || row.company_id !== company || row.status !== 'DRAFT' || !Number.isSafeInteger(row.row_version) || row.row_version <= loaded.voucher.row_version) throw { status: 502, message: 'The saved draft could not be verified. Retry the same save.' };
          });
          if (result) { setDirty(false); destination.setDestination(reviewHref); }
        } catch (error) { if (error instanceof PurchaseValidationError) setErrors({ [error.field]: error.message }); else setFailure(error instanceof Error ? error.message : 'Unable to prepare draft'); }
      })(); }}>
        <fieldset className="janso-fieldgroup janso-flow" disabled={locked}>
          {loaded.metadata.native.properties?.narration && <TextField label="Narration" value={narration} disabled={locked || loaded.metadata.native.properties.narration.readOnly} onChange={event => { setNarration(event.target.value); setDirty(true); }} />}
          {purchase ? <PurchaseInvoice company={company} currency={currency} metadata={loaded.metadata} value={purchase} errors={errors} onPendingChange={setPurchaseBusy} disabled={locked} onChange={value => { setPurchase(value); setErrors({}); setDirty(true); }} /> : <VoucherMoney company={company} currency={currency} metadata={loaded.metadata} value={money} knownAccounts={loaded.accounts} disabled={locked} onChange={value => { setMoney(value); setDirty(true); }} />}
        </fieldset>
        <div className="janso-custom-actions"><Button type="submit" disabled={command.pending || purchaseBusy || !dirty && !command.uncertain} loading={command.pending}>{command.uncertain ? 'Retry the same save' : 'Save draft changes'}</Button><a className="janso-link" href={reviewHref} onClick={guard.leave}>Cancel changes</a></div>
      </form>
      {command.failure && <Notice tone="danger">{command.failure.message}{command.uncertain ? ' Your changes are unconfirmed. Retry the same save to recover the result.' : ''}</Notice>}
    </>}
    {guard.confirmation}
  </section>;
}
