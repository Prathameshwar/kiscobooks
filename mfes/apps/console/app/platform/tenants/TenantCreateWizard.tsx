'use client';

import { useEffect, useRef, useState } from 'react';
import type { components } from '@janso/api-client/identity';
import { Button, Checkbox, ConfirmDialog, Notice, PageNavigation, PasswordField, ReviewList, SectionHeader, Select, TextField, ThemeSwitcher, WizardLayout, Wordmark } from '@janso/ui';
import { administrationDirectoryReturn, administrationLink, administrationReturn } from '../../lib/administration-navigation';
import { PlatformError, platformCall, platformFailure, type PlatformFailure } from '../../lib/platform-api';
import { goTo } from '../../lib/navigate';
import { useEditorDraft } from '../useEditorDraft';

type Choices = components['schemas']['TenantChoices'];
type Created = components['schemas']['PlatformTenantCreated'];
type Registration = components['schemas']['PendingRegistration'];
type Available = components['schemas']['AvailableAdministrator'];
type Draft = { name: string; country_code: string; state_code: string; administrator_name: string; administrator_email: string; administrator_mode: string; password_choice: string };
const initial: Draft = { name: '', country_code: 'IN', state_code: '', administrator_name: '', administrator_email: '', administrator_mode: 'new', password_choice: 'generate' };
const steps = ['Tenant details', 'Administrator', 'Review & create'];
const descriptions = ['Name your workspace and choose its location.', 'Create an administrator or select an available account.', 'Check the details, then create the tenant and activate its administrator.'];
const fieldStep: Record<string, number> = { name: 0, country_code: 0, state_code: 0, administrator_name: 1, administrator_email: 1, administrator_password: 1, recipient_confirmed: 1 };
const emailValid = (value: string) => value.length <= 320 && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());

export function TenantCreateWizard({ scope, returnTo }: { scope: string; returnTo?: string }) {
  const back = administrationReturn('tenants', returnTo), directory = administrationDirectoryReturn('tenants', back);
  const returnPath = '/platform/tenants/new' + (back !== '/platform/tenants' ? '?returnTo=' + encodeURIComponent(back) : '');
  const editor = useEditorDraft(scope + ':new', initial), { draft } = editor;
  const [step, setStep] = useState(0), [reached, setReached] = useState(0);
  const [choices, setChoices] = useState<Choices | null>(null), [loading, setLoading] = useState(true), [reload, setReload] = useState(0);
  const [error, setError] = useState<PlatformFailure | null>(null), [fields, setFields] = useState<Record<string, string>>({});
  const [password, setPassword] = useState(''), [confirmed, setConfirmed] = useState(false);
  const [candidate, setCandidate] = useState<Available | null>(null), [selected, setSelected] = useState<Available | null>(null);
  const [lookupPending, setLookupPending] = useState(false), [lookupMessage, setLookupMessage] = useState('');
  const [pending, setPending] = useState(false), [matching, setMatching] = useState<Registration | null>(null);
  const [created, setCreated] = useState<Created | null>(null), [copyMessage, setCopyMessage] = useState('');
  const busy = useRef(false), lookupVersion = useRef(0), generatedPassword = useRef<string | null>(null), root = useRef<HTMLDivElement>(null);
  const focusField = useRef<string | null>(null);
  const existing = draft.administrator_mode === 'existing';
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError(null);
    platformCall<Choices>('/v1/platform/tenant-options', 'GET', undefined, undefined, controller.signal)
      .then(value => {
        if (controller.signal.aborted) return;
        if (![value.countries, value.currencies, value.languages, value.timezones].every(items => items?.length) || !Array.isArray(value.states))
          throw { status: 503, message: 'Regional choices are unavailable. Try loading the form again.' };
        setChoices(value); setLoading(false);
      }).catch(value => { if (!controller.signal.aborted) { setChoices(null); setError(platformFailure(value)); setLoading(false); } });
    return () => controller.abort();
  }, [reload]);
  useEffect(() => () => { lookupVersion.current++; }, []);
  useEffect(() => {
    const name = focusField.current;
    if (!name) return;
    focusField.current = null;
    const frame = requestAnimationFrame(() => Array.from(root.current?.querySelectorAll<HTMLInputElement>('[name]') ?? []).find(input => input.name === name)?.focus());
    return () => cancelAnimationFrame(frame);
  }, [step, fields]);

  function secretChanged() { editor.touched.current = true; editor.key.current = crypto.randomUUID(); }
  function change(field: keyof Draft, value: string) {
    editor.change({ [field]: value, ...(field === 'country_code' ? { state_code: '' } : {}) });
    setFields(current => ({ ...current, [field]: '', ...(field === 'country_code' ? { state_code: '' } : {}) })); setError(null);
    if (field === 'administrator_email' || field === 'administrator_mode') {
      lookupVersion.current++; setLookupPending(false); setCandidate(null); setSelected(null); setLookupMessage(''); setConfirmed(false);
    }
    if (field === 'password_choice' || field === 'administrator_mode') { setPassword(''); generatedPassword.current = null; }
  }
  function tenantErrors(): Record<string, string> {
    const invalid: Record<string, string> = {};
    if (!draft.name.trim() || draft.name.length > 200 || /[\x00-\x1f\x7f]/.test(draft.name)) invalid.name = 'Enter a valid tenant name with up to 200 characters.';
    if (!choices?.countries.some(item => item.code === draft.country_code)) invalid.country_code = 'Choose an available country.';
    const states = choices?.states.filter(item => item.country_code === draft.country_code) ?? [];
    if (states.length && !states.some(item => item.code === draft.state_code) || draft.state_code && !states.some(item => item.code === draft.state_code)) invalid.state_code = 'Choose an available state for this country.';
    return invalid;
  }
  function administratorErrors(): Record<string, string> {
    const invalid: Record<string, string> = {};
    if (!emailValid(draft.administrator_email)) invalid.administrator_email = 'Enter a valid email address.';
    if (existing) {
      if (!selected || selected.email.toLowerCase() !== draft.administrator_email.trim().toLowerCase()) invalid.administrator_email = 'Find and select an available account with this email.';
    } else {
      if (!draft.administrator_name.trim() || draft.administrator_name.length > 100 || /[\x00-\x1f\x7f]/.test(draft.administrator_name)) invalid.administrator_name = 'Enter a valid name with up to 100 characters.';
      if (draft.password_choice === 'enter' && (Array.from(password).length < 12 || Array.from(password).length > 128 || /[\x00-\x1f\x7f]/.test(password))) invalid.administrator_password = 'Use 12 to 128 characters without control characters.';
      if (!confirmed) invalid.recipient_confirmed = 'Confirm that this person controls the email address.';
    }
    return invalid;
  }
  function showFields(invalid: Record<string, string>): boolean {
    setFields(invalid);
    const first = Object.keys(invalid)[0];
    if (!first) return true;
    focusField.current = first;
    if (fieldStep[first] !== undefined) setStep(fieldStep[first]);
    return false;
  }
  async function checkPending(email: string, version?: number): Promise<boolean> {
    const result = await platformCall<{ match: Registration | null }>(`/v1/platform/accounts/pending-registration?email=${encodeURIComponent(email.trim())}`);
    if (version !== undefined && version !== lookupVersion.current) return false;
    if (result.match) { setMatching(result.match); setStep(1); return false; }
    return true;
  }
  async function findAdministrator() {
    if (busy.current || lookupPending) return;
    if (!emailValid(draft.administrator_email)) { showFields({ administrator_email: 'Enter a valid email address.' }); return; }
    const version = ++lookupVersion.current;
    setLookupPending(true); setLookupMessage(''); setCandidate(null); setSelected(null); setError(null);
    try {
      if (!await checkPending(draft.administrator_email, version)) return;
      const value = await platformCall<{ available: Available | null }>(`/v1/platform/tenant-administrators/available?email=${encodeURIComponent(draft.administrator_email.trim())}`);
      if (version !== lookupVersion.current) return;
      setCandidate(value.available);
      setLookupMessage(value.available ? 'Select this account to use its current login.' : 'No unlinked active, verified account uses this email. You can create a new account instead.');
    } catch (value) { if (version === lookupVersion.current) setError(platformFailure(value)); }
    finally { if (version === lookupVersion.current) setLookupPending(false); }
  }
  async function advance(target = step + 1) {
    if (busy.current || lookupPending || loading || !choices || created) return;
    if (!showFields({ ...tenantErrors(), ...(target >= 2 ? administratorErrors() : {}) })) return;
    if (target < 2) { setStep(target); setReached(value => Math.max(value, target)); return; }
    busy.current = true; setPending(true); setError(null);
    try { if (await checkPending(draft.administrator_email)) { setStep(2); setReached(2); } }
    catch (value) { setError(platformFailure(value)); }
    finally { busy.current = false; setPending(false); }
  }
  async function create() {
    if (step !== 2 || busy.current || created || !choices || !showFields({ ...tenantErrors(), ...administratorErrors() })) return;
    busy.current = true; setPending(true); setError(null);
    try {
      if (!await checkPending(draft.administrator_email)) return;
      const submittedPassword = existing ? null : draft.password_choice === 'enter' ? password : (generatedPassword.current ??= crypto.randomUUID().replaceAll('-', '') + 'Aa1!');
      const value = await platformCall<Created>('/v1/platform/tenants', 'POST', {
        name: draft.name.trim(), country_code: draft.country_code, state_code: draft.state_code || null,
        administrator_name: draft.administrator_name.trim(), administrator_email: draft.administrator_email.trim(),
        administrator_mode: existing ? 'existing' : 'new', administrator_password: submittedPassword, recipient_confirmed: !existing && confirmed,
      }, editor.key.current);
      setCreated({ ...value, administrator_password: value.administrator_password ?? submittedPassword });
      editor.saved(); setPassword(''); generatedPassword.current = null;
    } catch (value) {
      const failure = platformFailure(value); setError(failure);
      const mapping: Record<string, string> = { default_country_code: 'country_code', default_state_code: 'state_code', primary_contact_email: 'administrator_email' };
      const invalid = Object.fromEntries(Object.entries(failure.fields ?? {}).map(([key, message]) => [mapping[key] ?? key, message || 'Check this value and try again.']));
      if (Object.keys(invalid).length) showFields(invalid);
    } finally { busy.current = false; setPending(false); }
  }
  function leave(event: React.MouseEvent<HTMLAnchorElement>) {
    if (pending || lookupPending || editor.touched.current && !window.confirm('Discard your unsaved tenant setup?')) event.preventDefault();
    else editor.saved();
  }
  async function copy(value: string, success: string) {
    try { await navigator.clipboard.writeText(value); setCopyMessage(success); }
    catch { setCopyMessage('Select and copy the details above.'); }
  }
  const label = (items: Choices['countries'] | undefined, value: string) => items?.find(item => item.code === value)?.name ?? value;
  const review = [
    { label: 'Tenant name', value: draft.name, step: 0 },
    { label: 'Country', value: label(choices?.countries, draft.country_code), step: 0 },
    { label: 'State', value: label(choices?.states, draft.state_code) || 'Not applicable', step: 0 },
    { label: 'Administrator', value: draft.administrator_name, step: 1 },
    { label: 'Administrator email', value: draft.administrator_email, step: 1 },
    { label: 'Account', value: existing ? `Existing account (${selected?.username ?? ''})` : 'New active, verified account', step: 1 },
    { label: 'Password', value: existing ? 'Keeps the existing password' : draft.password_choice === 'enter' ? 'Entered password, shared privately after creation' : 'Generated strong password, shown after creation', step: 1 },
  ];
  const unavailable = !choices && !loading;
  return <WizardLayout brand={<Wordmark size={28} nameSize="1.0625rem" />} headerEnd={<ThemeSwitcher />}
    steps={steps.map((entry, index) => ({ label: entry, complete: index === 0 ? !Object.keys(tenantErrors()).length : index === 1 ? !Object.keys(administratorErrors()).length : !!created }))}
    current={step} reached={reached} onStep={pending || lookupPending || created ? undefined : target => target <= step ? setStep(target) : void advance(target)}
    title={created ? 'Tenant created' : steps[step]} subtitle={created ? 'Your tenant and administrator are ready to use.' : descriptions[step]}
    progress={`Step ${step + 1} of 3`} notice={<>
      <PageNavigation breadcrumbs={[{ label: 'Platform administration', href: '/platform' }, { label: 'Tenants', href: directory }, { label: 'New tenant' }]} onNavigate={leave} />
      <PlatformError value={error} returnTo={returnPath} onNavigate={() => { editor.preserve(); editor.touched.current = false; }} />
      {editor.restored && !created ? <Notice>Your draft has been restored. Review it and confirm the administrator again. Passwords are not saved.</Notice> : null}
      <ConfirmDialog open={!!matching} title="Pending account registration found" confirmLabel="Yes, review account" cancelLabel="No, keep draft" onCancel={() => setMatching(null)} onConfirm={() => { if (matching) { editor.preserve(); editor.touched.current = false; goTo('/platform/accounts/' + matching.id); } }}>
        <p>{matching?.name} already registered with {matching?.email}. {matching?.workspace_name === '' ? 'This account joins an existing invitation; approval will not create a new tenant.' : `Approving the account will create ${matching?.workspace_name ?? 'the workspace chosen during review'}.`}</p>
        <p>Choose Yes to review and approve that registration, or No to keep this draft without creating another tenant.</p>
      </ConfirmDialog>
    </>} actions={created ? <>
      <a className="janso-btn janso-btn--ghost" href={back}>Return to directory</a>
      <a className="janso-btn janso-btn--primary" href={returnPath}>Create another tenant</a>
    </> : unavailable ? <><a className="janso-btn janso-btn--ghost" href={back} onClick={leave}>Cancel</a><Button type="button" onClick={() => setReload(value => value + 1)}>Retry loading form</Button></> : <>
      {step === 0 ? <a className="janso-btn janso-btn--ghost" href={back} onClick={leave}>Cancel</a> : <Button type="button" variant="ghost" disabled={pending || lookupPending} onClick={() => setStep(value => value - 1)}>Back</Button>}
      <Button type="submit" loading={pending} loadingLabel={step === 2 ? 'Creating tenant…' : 'Checking administrator…'} disabled={loading || lookupPending || !choices}>{step === 2 ? 'Create tenant' : 'Next'}</Button>
    </>} onSubmit={event => { event.preventDefault(); if (!created) void (step === 2 ? create() : advance()); }}>
    <div ref={root} className="janso-flow">
      {created ? <>
        <Notice tone="success">Tenant and administrator are ready.</Notice>
        <ReviewList items={[{ label: 'Tenant', value: created.name }, { label: 'Status', value: 'Active' }, { label: 'Administrator email', value: created.primary_contact_email }, { label: 'Administrator status', value: 'Active and email verified' }]} />
        <SectionHeader title="Share administrator access" description="The administrator can sign in immediately. No invitation acceptance is needed." />
        <Notice>{created.notification_status === 'queued' ? 'Account-ready email is queued. Manual sharing is also available.' : 'Automatic email is not configured. Copy and share the details below.'} Passwords are shared separately and are never emailed.</Notice>
        <TextField label="Sign-in username" readOnly value={created.administrator_username} />
        <TextField label="Sign-in link" readOnly value={created.sign_in_url} />
        <div className="janso-form-grid">
          <Button type="button" variant="ghost" onClick={() => void copy(created.sign_in_url, 'Access link copied.')}>Copy access link</Button>
          <Button type="button" variant="ghost" onClick={() => void copy(`Sign-in: ${created.sign_in_url}\nUsername: ${created.administrator_username}`, 'Sign-in details copied.')}>Copy sign-in details</Button>
        </div>
        {created.administrator_password ? <>
          <Notice tone="warning">This password is shown only once. Share it privately and ask the administrator to change it after sign-in.</Notice>
          <TextField label="One-time password" readOnly value={created.administrator_password} />
          <Button type="button" variant="ghost" onClick={() => void copy(created.administrator_password!, 'Password copied.')}>Copy password</Button>
        </> : <p>The selected administrator keeps their existing password.</p>}
        {copyMessage ? <p role="status">{copyMessage}</p> : null}
        <a className="janso-link" href={created.sign_in_url}>Open sign-in</a>
        <a className="janso-link" href={created.sign_in_url.replace(/\/login$/, '/change-password')}>Change password after sign-in</a>
        <a className="janso-link" href={administrationLink('/platform/tenants/' + created.id, directory)}>View tenant</a>
      </> : loading ? <p role="status">Loading tenant form…</p> : choices ? <>
        {step === 0 ? <>
          <TextField name="name" label="Tenant name" autoComplete="organization" required maxLength={200} value={draft.name} error={fields.name} onChange={event => change('name', event.target.value)} />
          <SectionHeader title="Location" description="Regional defaults for this workspace." />
          <div className="janso-form-grid janso-form-grid--pair">
            <Select name="country_code" label="Country" required placeholder="Choose a country" value={draft.country_code} error={fields.country_code} options={choices.countries.map(item => ({ value: item.code, label: item.name }))} onChange={value => change('country_code', value)} />
            <Select name="state_code" label="State" placeholder="Choose a state" value={draft.state_code} error={fields.state_code} required={choices.states.some(item => item.country_code === draft.country_code)} disabled={!choices.states.some(item => item.country_code === draft.country_code)} hint={!choices.states.some(item => item.country_code === draft.country_code) ? 'No states are available for this country.' : undefined} options={choices.states.filter(item => item.country_code === draft.country_code).map(item => ({ value: item.code, label: item.name }))} onChange={value => change('state_code', value)} />
          </div>
        </> : step === 1 ? <fieldset className="janso-setup__fields" disabled={pending}>
          <Select name="administrator_mode" label="Administrator account" value={draft.administrator_mode} options={[{ value: 'new', label: 'Create new account' }, { value: 'existing', label: 'Use existing account' }]} onChange={value => change('administrator_mode', value)} />
          {!existing ? <TextField name="administrator_name" label="Administrator full name" autoComplete="name" required maxLength={100} value={draft.administrator_name} error={fields.administrator_name} onChange={event => change('administrator_name', event.target.value)} /> : null}
          <TextField name="administrator_email" label="Administrator email" type="email" autoComplete="email" required maxLength={320} value={draft.administrator_email} error={fields.administrator_email} hint={existing ? 'Search by the exact email address. Only active, verified accounts not linked to a tenant are available.' : 'Use an email address you have checked with this person.'} onChange={event => change('administrator_email', event.target.value)} />
          {existing ? <>
            <Button type="button" variant="ghost" loading={lookupPending} loadingLabel="Finding account…" onClick={() => void findAdministrator()}>Find available account</Button>
            {lookupMessage ? <p role="status">{lookupMessage}</p> : null}
            {candidate && !selected ? <div className="janso-flow"><SectionHeader title="Available account" /><ReviewList items={[{ label: 'Name', value: candidate.name }, { label: 'Username', value: candidate.username }, { label: 'Email', value: candidate.email }]} /><Button type="button" onClick={() => { editor.change({ administrator_name: candidate.name }); setSelected(candidate); setFields({}); }}>Use this account</Button></div> : null}
            {selected ? <Notice tone="success">Selected {selected.name} ({selected.username}). Their current password is preserved.</Notice> : null}
          </> : <>
            <Select name="password_choice" label="Temporary password" value={draft.password_choice} options={[{ value: 'generate', label: 'Generate a strong password' }, { value: 'enter', label: 'Enter a password' }]} onChange={value => change('password_choice', value)} />
            {draft.password_choice === 'enter' ? <PasswordField name="administrator_password" label="Temporary password" purpose="new" required minLength={12} maxLength={128} value={password} error={fields.administrator_password} onChange={event => { secretChanged(); setPassword(event.target.value); setFields(current => ({ ...current, administrator_password: '' })); }} /> : <p className="janso-fine">A strong password will be generated after you confirm creation and displayed once for private sharing.</p>}
            <Checkbox name="recipient_confirmed" checked={confirmed} aria-invalid={!!fields.recipient_confirmed} onChange={event => { editor.touched.current = true; setConfirmed(event.target.checked); setFields(current => ({ ...current, recipient_confirmed: '' })); }}>I confirm this person controls the email address above.</Checkbox>
            {fields.recipient_confirmed ? <p role="alert">{fields.recipient_confirmed}</p> : null}
          </>}
        </fieldset> : <>
          <ReviewList items={review} onEdit={pending ? undefined : target => setStep(target)} />
          <Notice>The tenant and administrator will be active and approved. {existing ? 'The selected account keeps its password.' : 'The administrator email will be marked verified using your confirmation.'}</Notice>
          <p>Account-ready email is sent when delivery is configured. A copyable access link and login details are always available after creation.</p>
        </>}
      </> : null}
    </div>
    </WizardLayout>;
}
