'use client';

import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Button, Notice, PasswordField, Select, TextField } from '@janso/ui';
import { AuthShell } from '../components/AuthShell';
import { MIN_PASSWORD_LENGTH, MAX_PASSWORD_LENGTH, PASSWORD_RULE_MESSAGE, parseRegistration, registrationErrors, type RegistrationErrors, type RegistrationInput } from '../lib/registration-input';
import { parseChoices, regionErrors, type RegistrationChoices } from '../lib/registration-regions';

const blank: RegistrationInput = { name: '', username: '', email: '', password: '', password_repeat: '', country_code: '', state_code: '', workspace_name: '' };
export default function SignupPage() {
  const [availability, setAvailability] = useState<'checking' | 'ready' | 'unavailable'>('checking');
  const [workspaceEnabled, setWorkspaceEnabled] = useState(false);
  // The local provider accepts either username or email for sign-in.
  const [eitherSignIn, setEitherSignIn] = useState(false);
  const [input, setInput] = useState<RegistrationInput>(blank);
  const [options, setOptions] = useState<RegistrationChoices | null>(null);
  const [retry, setRetry] = useState(0);
  const [fields, setFields] = useState<RegistrationErrors>({});
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [created, setCreated] = useState(false);
  const [invitationReturn, setInvitationReturn] = useState<string | null>(null);
  const success = useRef<HTMLDivElement>(null);
  const form = useRef<HTMLFormElement>(null);
  const submitting = useRef(false);
  useEffect(() => {
    const candidate = new URLSearchParams(window.location.search).get('returnTo');
    if (!candidate || candidate.length > 2048 || !candidate.startsWith('/') || candidate.startsWith('//')) return;
    try {
      const url = new URL(candidate, window.location.origin);
      const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
      if (url.origin === window.location.origin && url.pathname === '/accept' &&
          uuid.test(url.searchParams.get('tenant') ?? '') && uuid.test(url.searchParams.get('invitation') ?? '') && !url.hash) {
        url.searchParams.delete('resume');
        setInvitationReturn(url.pathname + url.search);
      }
    } catch { /* Keep the ordinary signup flow. */ }
  }, []);
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    setAvailability('checking');
    fetch('/api/registration', { cache: 'no-store', signal: controller.signal }).then(response => response.ok ? response.json() : null)
      .then(value => {
        if (!active) return;
        const choices = parseChoices(value?.options);
        if (value?.enabled !== true || value?.mode !== 'manual-review' || !choices) { setOptions(null); setAvailability('unavailable'); return; }
        setOptions(choices);
        setWorkspaceEnabled(value.workspace_enabled === true);
        setEitherSignIn(value.sign_in === 'username_or_email');
        setInput(current => ({ ...current,
          country_code: choices.countries.some(item => item.code === current.country_code) ? current.country_code :
            choices.countries.some(item => item.code === 'IN') ? 'IN' : '',
          state_code: choices.states.some(item => item.code === current.state_code && item.country_code === current.country_code) ? current.state_code : '',
        }));
        setAvailability('ready');
      })
      .catch(() => { if (active) setAvailability('unavailable'); });
    return () => { active = false; controller.abort(); };
  }, [retry]);
  useEffect(() => { if (created) success.current?.focus(); }, [created]);
  useEffect(() => { if (!pending && error) focusError(fields); }, [pending, error, fields]);
  function change(key: keyof RegistrationInput, value: string) {
    setInput(current => ({ ...current, [key]: value, ...(key === 'country_code' ? { state_code: '' } : {}) }));
    setFields(current => ({ ...current, [key]: undefined, ...(key === 'country_code' ? { state_code: undefined } : {}) }));
    setError(null);
  }
  function focusError(errors: RegistrationErrors) {
    const key = Object.keys(errors)[0];
    if (key) (form.current?.elements.namedItem(key) as HTMLInputElement | null)?.focus();
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (submitting.current || availability !== 'ready' || !options) return;
    const normalized = parseRegistration(input)!;
    const validation = { ...registrationErrors(normalized), ...regionErrors(normalized, options) };
    setFields(validation);
    if (Object.keys(validation).length) { setError('Please check the highlighted fields.'); focusError(validation); return; }
    submitting.current = true;
    setPending(true); setError(null);
    try {
      const inviteUrl = invitationReturn ? new URL(invitationReturn, window.location.origin) : null;
      const account = Object.fromEntries(Object.entries(normalized).filter(([key]) => key !== 'workspace_name'));
      const payload = workspaceEnabled ? { ...account, ...(inviteUrl ? {
        invitation_tenant: inviteUrl.searchParams.get('tenant'), invitation_id: inviteUrl.searchParams.get('invitation'),
      } : {}) } : account;
      const response = await fetch('/api/registration', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload), signal: AbortSignal.timeout(25_000) });
      const result = await response.json();
      if (response.status === 201 && result.created === true && result.status === 'pending-review') {
        setInput(blank); setCreated(true);
      } else {
        // Only known, fixed field messages are displayed; never echo provider errors or credentials.
        const safe: RegistrationErrors = {};
        for (const key of Object.keys(blank) as (keyof RegistrationInput)[]) if (typeof result.fields?.[key] === 'string') {
          safe[key] = key === 'username' ? 'Choose another username. This one cannot be used.' :
            key.startsWith('password') ? 'Check your password and confirmation.' : 'Check this account detail.';
        }
        setFields(safe); focusError(safe);
        setError(response.status === 429 ? 'Too many attempts. Please wait a minute and try again.' :
          response.status === 422 ? 'These account details cannot be used. Check the fields or contact your administrator.' :
          'Account creation is temporarily unavailable. Please try again later.');
      }
    } catch { setError('We could not confirm account creation. Please contact your administrator before trying again.'); }
    finally { setPending(false); submitting.current = false; setInput(current => ({ ...current, password: '', password_repeat: '' })); }
  }
  const states = options?.states.filter(item => item.country_code === input.country_code) ?? [];
  // Only the country and state choices come from the server. While they load, everything else
  // stays usable, so the first seconds of a slow load are not a form that looks switched off.
  const checking = availability === 'checking';
  return <AuthShell registration>
    <div className="auth__form-head">
      <h1 className="auth__title">{created ? 'Your account is created' : 'Create your account'}</h1>
      <p className="auth__subtitle">{created ? 'One more step before you can sign in.' : invitationReturn ? 'Create an account to accept your workspace invitation.' : 'A clear start for your business books.'}</p>
    </div>
    {created ? <div className="janso-registration__success" ref={success} tabIndex={-1} aria-label="Account created">
      <Notice tone="success">Awaiting administrator approval</Notice>
      <ol className="janso-registration__steps">
        <li>Your administrator will check your details and verify your email address manually.</li>
        <li>{invitationReturn ? 'They will activate your account. You can then accept your invitation.' : 'They will activate your account and create your workspace automatically.'}</li>
        <li>{eitherSignIn ? 'Once approved, sign in with your username or email address and the password you chose.' : 'Once approved, sign in with the username and password you chose.'}</li>
      </ol>
      <p className="janso-registration__review">Ask your platform administrator to review and approve your account. Approval details are emailed when delivery is configured, or your administrator can share the access link directly.</p>
      {invitationReturn ? <><p className="janso-registration__review">Once your account is approved and your email is verified, return to the invitation and sign in.</p>
        <a className="janso-link" href={invitationReturn}>Return to invitation</a></>
        : <a className="janso-link" href="/login">Back to sign in</a>}
    </div> : <>
      {availability === 'unavailable' ? <><Notice tone="warning">Account creation is currently unavailable. Contact your platform administrator.</Notice><Button variant="ghost" onClick={() => setRetry(current => current + 1)}>Try again</Button></> : null}
      {error ? <div className="auth__alert"><Notice tone="danger">{error}</Notice></div> : null}
      <form className="janso-registration__form" onSubmit={submit} ref={form} noValidate aria-label="Create account" aria-busy={pending || checking}>
        <fieldset className="janso-registration__section" disabled={pending || availability === 'unavailable'}>
          <legend>Your details</legend>
          <div className="janso-registration__fields">
            <div className="janso-registration__pair">
              <TextField name="name" label="Full name" autoComplete="name" maxLength={100} required value={input.name} error={fields.name} onChange={e => change('name', e.target.value)} />
              <TextField name="username" label="Username" autoComplete="username" autoCapitalize="none" spellCheck={false} maxLength={64} required value={input.username} error={fields.username} hint={checking ? 'Lowercase letters, numbers, . _ or -' : eitherSignIn ? 'Used to sign in; you can also use your email address. Lowercase letters, numbers, . _ or -' : 'Used to sign in. Lowercase letters, numbers, . _ or -'} onChange={e => change('username', e.target.value)} />
            </div>
            <TextField name="email" label="Email address" type="email" autoComplete="email" maxLength={254} required value={input.email} error={fields.email} hint={invitationReturn ? 'Use the same address as your workspace invitation.' : 'Use an address your platform administrator can verify.'} onChange={e => change('email', e.target.value)} />
            <div className="janso-form-grid janso-form-grid--pair">
              <Select name="country_code" label="Country" autoComplete="country" value={input.country_code} required
                loading={checking} loadingLabel="Loading countries…" placeholder="Choose a country" error={fields.country_code}
                options={(options?.countries ?? []).map(item => ({ value: item.code, label: item.name }))}
                onChange={value => change('country_code', value)} />
              <Select name="state_code" label="State" autoComplete="address-level1" value={input.state_code}
                required={states.length > 0} disabled={!states.length} loading={checking} loadingLabel="Loading states…"
                placeholder="Choose a state" error={fields.state_code}
                hint={input.country_code && !states.length ? 'No states are available for this country.' : undefined}
                options={states.map(item => ({ value: item.code, label: item.name }))} onChange={value => change('state_code', value)} />
            </div>
          </div>
        </fieldset>
        <fieldset className="janso-registration__section" disabled={pending || availability === 'unavailable'}>
          <legend>Secure your account</legend>
          <div className="janso-registration__fields janso-registration__passwords">
            <div><PasswordField name="password" label="Password" purpose="new" minLength={MIN_PASSWORD_LENGTH} maxLength={MAX_PASSWORD_LENGTH * 2} required value={input.password} error={fields.password} hint={<span className="janso-visually-hidden">{PASSWORD_RULE_MESSAGE}</span>} avoid={[input.username, input.email]} onChange={e => change('password', e.target.value)} /></div>
            <div><PasswordField name="password_repeat" label="Confirm password" purpose="new" showStrength={false} minLength={MIN_PASSWORD_LENGTH} maxLength={MAX_PASSWORD_LENGTH * 2} required value={input.password_repeat} error={fields.password_repeat} onChange={e => change('password_repeat', e.target.value)} /></div>
            <p id="registration-password-guidance" className="janso-registration__password-guidance">{PASSWORD_RULE_MESSAGE}</p>
          </div>
        </fieldset>
        <Button type="submit" block disabled={availability !== 'ready'} loading={pending} loadingLabel="Creating account…">Create account</Button>
      </form>
      <p className="auth__foot">Already have an account? <a className="janso-link" href="/login">Sign in</a></p>
      {invitationReturn ? <p className="auth__foot"><a className="janso-link" href={invitationReturn}>Back to invitation</a></p> : null}
    </>}
  </AuthShell>;
}
