'use client';

import { useCallback, useEffect, useId, useRef, useState, type ReactNode, type RefObject } from 'react';
import { Button, Checkbox, ConfirmDialog, Drawer, ExternalLinkIcon, Notice, Select, TextField } from '@janso/ui';
import {MasterOpeningStep} from './MasterOpeningStep';
import {openingDirty,openingPayload,useMasterOpening} from '../lib/master-opening';
import { AccountingReference } from './AccountingConfigurationCommon';
import { assertAccountingRecord, useAccountingCommand } from '../lib/accounting-configuration';
import type { AccountingRecord } from '../lib/accounting-configuration-resources';
import { cleanGstin, defaultExpenseGroup, expenseAccountRequest, GST_STATUS_OPTIONS, gstinRequired, loadExpenseGroups, QUICK_CREATE_LIMITS, supplierRequest,
  type ExpenseAccountDraft, type ExpenseGroup, type GstStatus, type QuickCreated, type SupplierDraft } from '../lib/purchase-quick-create';
import { requestFailure } from '../lib/service-call';
import { limitMasterCode } from '../lib/accounting-master-code';

type Command = ReturnType<typeof useAccountingCommand>;
type Created = AccountingRecord & { name?: string | null; code?: string | null; status?: string; kind?: string; group_id?: string | null; inventory_affected?: boolean; posting_policy?: string };

const createdFrom = (record: Created, fallback: string): QuickCreated => ({ id: record.id, label: record.name || fallback, ...(record.code ? { meta: record.code } : {}) });

/**
 * The drawer chrome both creations share: the purpose line, the way a failed or unconfirmed request is
 * said, the way out to the full master page, and the discard guard. What a person typed is never thrown
 * away by a stray click on the scrim or an Escape, and a request whose outcome is unknown is never
 * "cancelled" without saying so.
 */
function QuickCreateShell({ title, thing, intro, submit, pendingLabel, command, dirty, canSubmit = true, size = 'md', formClassName = '', inline, fullForm, formRef, onSubmit, onClose, children }: {
  title: string; thing: string; intro: string; submit: string; pendingLabel: string; command: Command; dirty: boolean; canSubmit?: boolean;
  size?: 'md' | 'lg'; formClassName?: string;
  /** The server field keys the form shows beside their fields; any other rejected field is listed in the notice. */
  inline: readonly string[];
  /** The master page with every field, for whatever this short form leaves out. It opens in a new tab so the bill stays as it is. */
  fullForm: { href: string; label: string };
  formRef: RefObject<HTMLFormElement | null>;
  onSubmit: () => void; onClose: () => void; children: ReactNode;
}) {
  const formId = useId();
  const [discard, setDiscard] = useState(false);
  const { failure, pending, uncertain } = command;
  // The drawer itself will not dismiss while busy, and Cancel is disabled then, so this is never reached in flight.
  const close = useCallback(() => { if (dirty || uncertain) setDiscard(true); else onClose(); }, [dirty, uncertain, onClose]);
  const rest = Object.entries(failure?.fields ?? {}).filter(([key]) => !inline.includes(key === 'ledger.code' ? 'code' : key.replace(/^(party|tax_registration)\./, '')));
  // A rejected form says so beside its fields; repeating "validation failed" above them adds nothing.
  const beside = failure?.status === 422 && !rest.length && Object.keys(failure.fields ?? {}).length > 0;
  return <>
    <Drawer open title={title} size={size} busy={pending} onClose={close} footer={<>
      <a className="janso-btn janso-btn--ghost console-quick-create__full" href={fullForm.href} target="_blank" rel="noopener noreferrer">
        <ExternalLinkIcon size={16} aria-hidden="true" />{fullForm.label}<span className="janso-visually-hidden"> (opens in a new tab)</span></a>
      <Button type="button" variant="ghost" disabled={pending} onClick={close}>Cancel</Button>
      <Button type="submit" form={formId} loading={pending} loadingLabel={pendingLabel} disabled={!canSubmit}>{uncertain ? 'Retry' : submit}</Button>
    </>}>
      {/* The bill's keyboard handlers and form live above this portal in the React tree; Enter here is this form's alone. */}
      <form ref={formRef} id={formId} noValidate className={'console-quick-create' + (formClassName ? ' ' + formClassName : '')} data-quick-create-form
        onSubmit={event => { event.preventDefault(); event.stopPropagation(); onSubmit(); }} onKeyDown={event => { if (event.key === 'Enter') event.stopPropagation(); }}>
        <p className="janso-fine console-quick-create__wide">{intro}</p>
        {failure && uncertain
          ? <div className="console-quick-create__wide"><Notice tone="warning" title="We could not confirm the result">
            Retry sends the same request again, so the {thing} cannot be created twice. If you cancel instead, check the list before creating it again.</Notice></div>
          : failure && !beside
            ? <div className="console-quick-create__wide"><Notice tone="danger" title={`The ${thing} was not created`}>{failure.message}{rest.length ? <ul>{rest.map(([key, message]) => <li key={key}>{message}</li>)}</ul> : null}</Notice></div>
            : null}
        {children}
      </form>
    </Drawer>
    <ConfirmDialog open={discard} title={uncertain ? `Close without confirming the ${thing}?` : `Discard this new ${thing}?`} confirmLabel={uncertain ? 'Close anyway' : 'Discard'} cancelLabel={uncertain ? 'Keep it open' : 'Keep editing'}
      onCancel={() => setDiscard(false)} onConfirm={() => { setDiscard(false); onClose(); }}>
      {uncertain ? `It may already have been created. Look for it in the list before creating it again.` : `What you have typed here will be lost. The bill itself is not affected.`}
    </ConfirmDialog>
  </>;
}

/** Field error: what this form found, else what the service said (under any of the keys it may use). */
const fieldError = (errors: Record<string, string>, command: Command, key: string) =>
  errors[key] ?? command.failure?.fields?.[key] ?? command.failure?.fields?.['party.' + key] ?? command.failure?.fields?.['tax_registration.' + key] ?? (key === 'code' ? command.failure?.fields?.['ledger.code'] : undefined);

function focusInvalid(form: HTMLElement | null, errors: Record<string, string>) {
  const key = Object.keys(errors)[0];
  form?.querySelector<HTMLElement>(`[name="${key}"], [data-field="${key}"] input`)?.focus();
}

/** What both drawers do the same way: the draft, what is wrong with it, whether it may be edited, and where the cursor starts. */
function useQuickCreateForm<T extends object>(initial: T, onCreated: (created: QuickCreated) => void) {
  const command = useAccountingCommand();
  const [draft, setDraft] = useState<T>(initial);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const form = useRef<HTMLFormElement>(null), name = useRef<HTMLInputElement>(null), latest = useRef(onCreated);
  // The newest callback, so a request that finishes after the bill re-rendered reports to the bill as it is now.
  latest.current = onCreated;
  useEffect(() => { name.current?.focus(); }, []);
  const locked = command.pending || command.uncertain;
  const set = (patch: Partial<T>) => {
    if (locked) return;
    if (command.failure) command.clear();
    setErrors({});
    setDraft(current => ({ ...current, ...patch }));
  };
  return { command, draft, errors, setErrors, form, name, latest, locked, set };
}

/**
 * New supplier, from the purchase bill. One command creates the supplier, its supplier role and its payable
 * account (Accounting's defaults) and, for an Indian supplier, the GST registration the person chose, so what
 * comes back can be billed straight away. Addresses and contacts belong to the full supplier form.
 */
export function SupplierQuickCreate({ company, companyCountry, canTax, onCreated, onClose }: {
  company: string; companyCountry: string;
  /** Whether the actor may record tax registrations; without it the GST fields are not offered. */
  canTax: boolean;
  onCreated: (created: QuickCreated) => void; onClose: () => void;
}) {
  const { command, draft, errors, setErrors, form, name, latest, locked, set } = useQuickCreateForm<SupplierDraft>({
    name: '', code: '', countryCode: /^[A-Z]{2}$/.test(companyCountry) ? companyCountry : 'IN', gstStatus: 'REGULAR', stateCode: '', gstin: '',
  }, onCreated);
  const gst = canTax && draft.countryCode === 'IN';
  const [showOpening,setShowOpening]=useState(false);
  const opening=useMasterOpening(company,showOpening);
  const openingAccount={party:true,role:'SUPPLIER',kind:'PARTY',currencyMode:'BASE'};
  function verifyCreated(value:Created){
    assertAccountingRecord(value,company);
    if(value.status!=='ACTIVE')throw {status:502,message:'The supplier was created, but it could not be confirmed as active. Retry to confirm it.'};
  }
  async function submit() {
    if (command.pending) return;
    if(command.uncertain){const saved=await command.retry<Created>(verifyCreated);if(saved)latest.current(createdFrom(saved,draft.name.trim()));return;}
    const { body, errors: found } = supplierRequest(draft, { tax: canTax });
    const captured=showOpening?openingPayload(opening.draft,opening.metadata,openingAccount):{errors:{},opening:undefined};
    Object.assign(found,captured.errors);
    setErrors(found);
    if (!body||Object.keys(found).length) { focusInvalid(form.current, found); return; }
    const saved = await command.execute<Created>({ path: `/v1/companies/${company}/parties/create-with-details`, method: 'POST', body:{...body,...(captured.opening?{opening:captured.opening}:{})} }, verifyCreated);
    if (saved) latest.current(createdFrom(saved, body.name));
  }
  return <QuickCreateShell title="New supplier" thing="supplier" submit="Create supplier" pendingLabel="Creating supplier…" command={command} size="lg" formClassName="console-quick-create--supplier"
    inline={['name', 'code', 'country_code', 'registration_type', 'registration_number', 'state_code']} fullForm={{ href: '/accounting/suppliers/new', label: 'Full supplier form' }} formRef={form}
    intro="Creates the supplier with its payable account and selects it on this bill. Add addresses and contacts later."
    dirty={!!(draft.name.trim() || draft.code.trim() || draft.gstin.trim() || draft.stateCode)||openingDirty(opening.draft)} onSubmit={() => void submit()} onClose={onClose}>
    <div className="console-quick-create__wide">
      <TextField ref={name} label="Supplier name" name="name" required value={draft.name} maxLength={QUICK_CREATE_LIMITS.name} disabled={locked} autoComplete="off"
        error={fieldError(errors, command, 'name')}
        onChange={event => set({ name: event.target.value })} />
    </div>
    <TextField label="Supplier code" name="code" optionalNote="Optional" value={draft.code} maxLength={QUICK_CREATE_LIMITS.code * 2} disabled={locked} autoComplete="off"
      hint="Leave blank to generate an eight-character code. Manual codes allow printable text up to 40 characters."
      error={fieldError(errors, command, 'code')} onChange={event => set({ code: limitMasterCode(event.target.value) })} />
    <div data-field="country_code">
      <AccountingReference company={company} source="countries" label="Country" required value={draft.countryCode || null} disabled={locked}
        error={fieldError(errors, command, 'country_code')} onChange={value => set({ countryCode: value ?? '', stateCode: '' })} />
    </div>
    {gst ? <>
      <h3 className="console-quick-create__section">Tax registration</h3>
      <Select label="GST registration" name="registration_type" value={draft.gstStatus} disabled={locked} options={GST_STATUS_OPTIONS.map(option => ({ value: option.value, label: option.label }))}
        error={fieldError(errors, command, 'registration_type')} onChange={value => set({ gstStatus: value as GstStatus })} />
      {draft.gstStatus !== 'NONE' ? <div data-field="state_code">
        <AccountingReference company={company} source="states" filters="country_code=IN" label="State" required value={draft.stateCode || null} disabled={locked}
          error={fieldError(errors, command, 'state_code')} onChange={value => set({ stateCode: value ?? '' })} />
      </div> : null}
      {gstinRequired(draft.gstStatus) ? <div className="console-quick-create__wide">
        <TextField label="GSTIN" name="registration_number" required value={draft.gstin} maxLength={19} disabled={locked} autoComplete="off" autoCapitalize="characters" spellCheck={false}
          placeholder="e.g. 27ABCDE1234F1Z5" error={fieldError(errors, command, 'registration_number')} onChange={event => set({ gstin: cleanGstin(event.target.value) })} />
      </div> : null}
    </> : null}
    <div className="console-quick-create__wide console-quick-create__opening"><Checkbox checked={showOpening} disabled={locked} onChange={event=>setShowOpening(event.target.checked)}>Add opening balance</Checkbox>
    {showOpening&&<MasterOpeningStep {...opening} account={openingAccount} onChange={value=>{if(!locked){if(command.failure)command.clear();opening.setDraft(value);setErrors({});}}} disabled={locked} errors={{...command.failure?.fields,...errors}}/>}</div>
  </QuickCreateShell>;
}

/**
 * New expense account, from a bill line. Only what an account bill accepts can be made here: a general,
 * postable, non-stock account under a group whose head is an expense head — so what is created is always
 * selectable on the line that asked for it.
 */
export function ExpenseAccountQuickCreate({ company, onCreated, onClose }: {
  company: string; onCreated: (created: QuickCreated) => void; onClose: () => void;
}) {
  const { command, draft, errors, setErrors, form, name, latest, locked, set } = useQuickCreateForm<ExpenseAccountDraft>({ name: '', code: '', groupId: '', description: '' }, onCreated);
  const [groups, setGroups] = useState<ExpenseGroup[] | null>(null), [loadFailure, setLoadFailure] = useState(''), [attempt, setAttempt] = useState(0);
  const [showOpening,setShowOpening]=useState(false);
  const opening=useMasterOpening(company,showOpening);
  const openingAccount={party:false,kind:'GENERAL',currencyMode:'BASE'};
  useEffect(() => {
    const controller = new AbortController();
    setGroups(null); setLoadFailure('');
    loadExpenseGroups(company, controller.signal).then(found => {
      if (controller.signal.aborted) return;
      setGroups(found);
      // The choice is disabled until the groups are here, so there is no pick to protect yet.
      set({ groupId: defaultExpenseGroup(found) });
    }, error => { if (!controller.signal.aborted) setLoadFailure(requestFailure(error, 'Accounting').message); });
    return () => controller.abort();
  }, [company, attempt]);
  function verifyCreated(value:Created){
    assertAccountingRecord(value,company);
    if(value.status!=='ACTIVE'||value.kind!=='GENERAL'||value.inventory_affected!==false||value.posting_policy!=='MANUAL_ALLOWED'||value.group_id!==draft.groupId)
      throw {status:502,message:'The account was created, but it could not be confirmed as a postable expense account. Retry to confirm it.'};
  }
  async function submit() {
    if (command.pending || !groups) return;
    if(command.uncertain){const saved=await command.retry<Created>(verifyCreated);if(saved)latest.current(createdFrom(saved,draft.name.trim()));return;}
    const { body, errors: found } = expenseAccountRequest(draft, groups);
    const captured=showOpening?openingPayload(opening.draft,opening.metadata,openingAccount):{errors:{},opening:undefined};
    Object.assign(found,captured.errors);
    setErrors(found);
    if (!body||Object.keys(found).length) { focusInvalid(form.current, found); return; }
    const saved = await command.execute<Created>({ path: `/v1/companies/${company}/accounts/create-active`, method: 'POST', body:{...body,...(captured.opening?{opening:captured.opening}:{})} }, verifyCreated);
    if (saved) latest.current(createdFrom(saved, body.name));
  }
  return <QuickCreateShell title="New expense account" thing="expense account" submit="Create account" pendingLabel="Creating account…" command={command}
    inline={['name', 'code', 'group_id', 'description']} fullForm={{ href: '/accounting/accounts/new', label: 'Full account form' }} formRef={form}
    intro="Creates an expense account you can post bills to, and selects it on this line."
    dirty={!!(draft.name.trim() || draft.code.trim() || draft.description.trim())||openingDirty(opening.draft)} canSubmit={!!groups?.length} onSubmit={() => void submit()} onClose={onClose}>
    {loadFailure ? <div className="console-quick-create__wide"><Notice tone="danger" title="Account groups could not be loaded" action={<Button type="button" variant="ghost" onClick={() => setAttempt(value => value + 1)}>Try again</Button>}>{loadFailure}</Notice></div> : null}
    {groups && !groups.length ? <div className="console-quick-create__wide"><Notice tone="warning" title="No expense groups are available">An expense account has to sit under a group of an expense head. Ask an administrator to add one under Account groups.</Notice></div> : null}
    <div className="console-quick-create__wide">
      <TextField ref={name} label="Account name" name="name" required value={draft.name} maxLength={QUICK_CREATE_LIMITS.name} disabled={locked} autoComplete="off"
        error={fieldError(errors, command, 'name')} placeholder="e.g. Office rent"
        onChange={event => set({ name: event.target.value })} />
    </div>
    <TextField label="Account code" name="code" optionalNote="Optional" value={draft.code} maxLength={QUICK_CREATE_LIMITS.code * 2} disabled={locked} autoComplete="off"
      hint="Leave blank to generate an eight-character code. Manual codes allow printable text up to 40 characters."
      error={fieldError(errors, command, 'code')} onChange={event => set({ code: limitMasterCode(event.target.value) })} />
    <Select label="Account group" name="group_id" required value={draft.groupId} disabled={locked || !groups?.length} placeholder={groups ? 'Choose a group' : 'Loading groups…'}
      options={(groups ?? []).map(group => ({ value: group.id, label: group.name }))} error={fieldError(errors, command, 'group_id')}
      onChange={value => set({ groupId: value })} />
    <div className="console-quick-create__wide">
      <TextField label="Description" name="description" optionalNote="Optional" value={draft.description} maxLength={QUICK_CREATE_LIMITS.description} disabled={locked} autoComplete="off"
        error={fieldError(errors, command, 'description')} onChange={event => set({ description: event.target.value })} />
    </div>
    <div className="console-quick-create__wide"><Checkbox checked={showOpening} disabled={locked} onChange={event=>setShowOpening(event.target.checked)}>Add opening balance</Checkbox>
    {showOpening&&<MasterOpeningStep {...opening} account={openingAccount} onChange={value=>{if(!locked){if(command.failure)command.clear();opening.setDraft(value);setErrors({});}}} disabled={locked} errors={{...command.failure?.fields,...errors}}/>}</div>
  </QuickCreateShell>;
}
