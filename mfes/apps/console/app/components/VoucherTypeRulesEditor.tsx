'use client';

import { useState } from 'react';
import {
  Button,
  Checkbox,
  Card,
  CardBody,
  ErrorState,
  FormActions,
  Notice,
  PageHeader,
  PageNavigation,
  Skeleton,
  asErrorStatus,
} from '@janso/ui';
import { goTo } from '../lib/navigate';
import { kindLabel } from '../lib/voucher-kinds';
import {
  draftFromPolicy,
  otherControls,
  policyFromDraft,
  rulesChanged,
  validateRules,
  type RulesDraft,
} from '../lib/voucher-type-policy';
import { TYPES_ROOT, typeHref, useKindCapabilities, useVoucherType, useVoucherTypeWrites } from '../lib/voucher-types';
import { VoucherTypeRules } from './VoucherTypeRules';
import {PurchaseCalculationPresetsEditor} from './PurchaseCalculationPresetsEditor';
import {readCalculationPolicy,validateCalculationPolicy,type PurchaseCalculationPolicy} from '../lib/purchase-calculation';

/**
 * Changing a voucher type's entry rules.
 *
 * A save is a **new revision**, not an edit in place: the service keeps every revision, and an issued
 * voucher keeps the one it was raised under. A draft still open on an earlier revision is asked to adopt
 * the current one before it can go further. The form therefore refuses to send an untouched
 * draft (a no-op revision is noise in the history), tells each wrong field what is wrong once a save
 * has been tried, and preserves policy fields outside the controls shown here. Standard Purchase
 * also exposes invoice entry and account supply selection without resetting other invoice rules.
 *
 * The version it was read at travels with the save. If someone else revised the type in between, the
 * service refuses with a conflict and the page says so and offers to reload, rather than overwriting
 * their revision with a stale one.
 */
export function VoucherTypeRulesEditor({ company, id }: { company: string; id: string }) {
  const read = useVoucherType(company, id);
  const writes = useVoucherTypeWrites(company);
  // The kind's own sections narrow what is offered. If they cannot be read the form still works and the service decides.
  const capabilities = useKindCapabilities(company);
  const [edited, setEdited] = useState<RulesDraft | null>(null);
  const [touched, setTouched] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const [editedInvoice, setEditedInvoice] = useState<Record<string, unknown> | null | undefined>();
  const [editedCalculation,setEditedCalculation]=useState<PurchaseCalculationPolicy|null>(null);
  const type = read.data;
  const kindSections = capabilities.kinds.find((entry) => entry.kind === type?.kind)?.planned_sections;

  const draft = edited ?? draftFromPolicy(type?.policy ?? null);
  const errors = touched ? validateRules(draft, kindSections) : {};
  const purchase = type?.kind === 'PURCHASE' && type.profile === 'STANDARD';
  const savedCalculation=readCalculationPolicy((type?.policy as {purchase_calculation?:PurchaseCalculationPolicy}|undefined)?.purchase_calculation);
  const calculation=editedCalculation??savedCalculation;
  const calculationChanged=purchase&&editedCalculation!==null&&JSON.stringify(calculation)!==JSON.stringify(savedCalculation);
  const savedInvoice = (type?.policy?.invoice ?? null) as Record<string, unknown> | null;
  const invoice = editedInvoice === undefined ? savedInvoice : editedInvoice;
  const invoiceChanged = purchase && editedInvoice !== undefined && JSON.stringify(invoice) !== JSON.stringify(savedInvoice);
  const changed = !!type && (rulesChanged(type.policy ?? null, draft) || invoiceChanged||calculationChanged);
  const locked = writes.pending || writes.uncertain || leaving;
  const detailHref = typeHref(id);

  const change = (patch: Partial<RulesDraft>) => {
    writes.clear();
    setEdited({ ...draft, ...patch });
  };

  function reload() {
    writes.clear();
    setEdited(null);
    setEditedInvoice(undefined);
    setEditedCalculation(null);
    setTouched(false);
    read.refresh();
  }

  async function save(): Promise<void> {
    if (!type) return;
    setTouched(true);
    if (Object.keys(validateRules(draft, kindSections)).length || purchase&&validateCalculationPolicy(calculation,invoice).length || !changed) return;
    const revised = await writes.revise(id, {
      expectedVersion: type.row_version,
      policy: { ...policyFromDraft(type.policy ?? null, draft), ...(invoiceChanged ? { invoice } : {}),...(calculationChanged?{purchase_calculation:calculation}:{}) },
    });
    if (revised) {
      setLeaving(true);
      goTo(`${detailHref}?saved=revised`);
    }
  }

  const crumbs = [
    { label: 'Masters', href: '/masters' },
    { label: 'Voucher types', href: TYPES_ROOT },
    { label: type?.name ?? 'Voucher type', href: detailHref },
    { label: 'Edit rules' },
  ];

  if (read.failure) {
    return (
      <div className="janso-page">
        <PageNavigation back={{ href: TYPES_ROOT, label: 'voucher types' }} breadcrumbs={crumbs} />
        <ErrorState status={asErrorStatus(read.failure.status)} detail={read.failure.message} />
      </div>
    );
  }

  const others = otherControls(type?.policy ?? null).filter(label => !purchase || label !== 'Invoice');

  return (
    <div className="janso-page">
      <PageNavigation back={{ href: detailHref, label: 'voucher type' }} breadcrumbs={crumbs} />
      <PageHeader
        title={type ? `Edit rules — ${type.name}` : 'Edit rules'}
        lede={
          type?.kind
            ? `The entry rules for ${kindLabel(type.kind).toLowerCase()} vouchers of this type. Saving creates revision ${(type.current_revision ?? 1) + 1}; issued vouchers keep the revision they were raised under, and drafts still open on an earlier one are asked to adopt this one.`
            : undefined
        }
      />
      {read.loading || capabilities.loading || !type ? (
        <Skeleton lines={6} />
      ) : type.status !== 'ACTIVE' ? (
        <Notice tone="warning">
          This voucher type is retired, so its rules can no longer be changed. <a className="janso-link" href={detailHref}>Back to the voucher type</a>
        </Notice>
      ) : (
        <Card>
          <CardBody>
            <div className="janso-flow">
              {others.length ? (
                <Notice>
                  This type also carries {others.join(', ').toLowerCase()} controls. They are not edited here and are kept as they are.
                </Notice>
              ) : null}
              <VoucherTypeRules draft={draft} errors={errors} disabled={locked} kindSections={kindSections} onChange={change} />
              {purchase && <fieldset className="janso-flow"><legend>Purchase invoice entry</legend>
                <Checkbox checked={!!invoice} disabled={locked} onChange={event => {
                  writes.clear(); setEditedInvoice(event.target.checked ? savedInvoice ?? {} : null);
                }}>Enable purchase invoice entry</Checkbox>
                <Checkbox checked={!!invoice && (!Array.isArray(invoice.allowed_supply_kinds) || invoice.allowed_supply_kinds.includes('ACCOUNT'))}
                  disabled={locked || !invoice} onChange={event => {
                    if (!invoice) return;
                    const kinds = Array.isArray(invoice.allowed_supply_kinds) ? invoice.allowed_supply_kinds as string[] : ['ACCOUNT', 'GOODS', 'SERVICE'];
                    writes.clear(); setEditedInvoice({ ...invoice, allowed_supply_kinds: event.target.checked
                      ? [...new Set([...kinds, 'ACCOUNT'])] : kinds.filter(kind => kind !== 'ACCOUNT') });
                  }}>Allow account purchase lines</Checkbox>
                <Checkbox checked={!!invoice && (!Array.isArray(invoice.allowed_supply_kinds) || invoice.allowed_supply_kinds.includes('SERVICE'))}
                  disabled={locked || !invoice} hint="GST on a supplier bill is recorded on service lines, so a bill with GST needs this."
                  onChange={event => {
                    if (!invoice) return;
                    const kinds = Array.isArray(invoice.allowed_supply_kinds) ? invoice.allowed_supply_kinds as string[] : ['ACCOUNT', 'GOODS', 'SERVICE'];
                    writes.clear(); setEditedInvoice({ ...invoice, allowed_supply_kinds: event.target.checked
                      ? [...new Set([...kinds, 'SERVICE'])] : kinds.filter(kind => kind !== 'SERVICE') });
                  }}>Allow service purchase lines</Checkbox>
                <Checkbox checked={!!invoice?.manual_discounts_allowed} disabled={locked||!invoice} onChange={event=>{if(invoice){writes.clear();setEditedInvoice({...invoice,manual_discounts_allowed:event.target.checked});}}}>Allow Purchase discounts</Checkbox>
                <Checkbox checked={!!invoice?.charges_allowed} disabled={locked||!invoice} onChange={event=>{if(invoice){writes.clear();setEditedInvoice({...invoice,charges_allowed:event.target.checked});}}}>Allow Purchase charges</Checkbox>
              </fieldset>}
              {purchase&&(invoice||calculation.presets.length>0)&&<PurchaseCalculationPresetsEditor value={calculation} invoice={invoice} disabled={locked} onChange={value=>{writes.clear();setEditedCalculation(value);}}/>}
              {purchase&&!invoice&&!!calculation.presets.length&&<Notice tone="danger">Remove the calculation formulas before disabling purchase invoice entry.</Notice>}
              {Object.keys(errors).length ? <Notice tone="danger">Fix the highlighted fields, then save again.</Notice> : null}
              {writes.uncertain ? (
                <Notice tone="warning">
                  The result of the last attempt is not known. Save again to retry the same request — it will not create a second revision.
                </Notice>
              ) : writes.failure ? (
                <Notice tone="danger">
                  {writes.failure}
                  {/* Only a conflict means this page is out of date; reloading after a refused value would throw the edits away for nothing. */}
                  {writes.status === 409 ? (
                    <>
                      {' '}
                      <Button variant="ghost" onClick={reload}>
                        Reload this type
                      </Button>
                    </>
                  ) : null}
                </Notice>
              ) : null}
            </div>
          </CardBody>
          <FormActions>
            <a className="janso-btn janso-btn--ghost" href={detailHref}>
              Cancel
            </a>
            <Button loading={writes.pending} disabled={writes.pending || leaving || (!changed && !writes.uncertain)} onClick={() => void save()}>
              {writes.uncertain ? 'Try again' : 'Save as revision ' + ((type.current_revision ?? 1) + 1)}
            </Button>
          </FormActions>
        </Card>
      )}
    </div>
  );
}
