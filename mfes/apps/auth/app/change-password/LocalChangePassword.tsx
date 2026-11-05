'use client';

import { useEffect, useRef, useState, type FormEvent } from 'react';
import { signOut } from 'next-auth/react';
import { Button, Notice, PageNavigation, PasswordField } from '@janso/ui';
import { AuthShell } from '../components/AuthShell';
import { MESSAGES } from '../lib/local-auth-shared';
import { consoleUrl } from '../lib/navigate';
import { MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH, PASSWORD_RULE_MESSAGE, passwordAcceptable } from '../lib/registration-input';

type Fields = { current?: string; password?: string; repeat?: string };

/**
 * Local provider: the whole change happens here. Identity verifies the current password, ends
 * every session for the account and revokes its refresh tokens, so on success this browser's
 * session is already dead server-side; signing out clears the local cookie and sends the person
 * to sign in with the new password. Nothing is persisted and the fields are emptied after each try.
 */
export function LocalChangePassword() {
  const [current, setCurrent] = useState('');
  const [password, setPassword] = useState('');
  const [repeat, setRepeat] = useState('');
  const [fields, setFields] = useState<Fields>({});
  const [error, setError] = useState<string | null>(null);
  const [expired, setExpired] = useState(false);
  const [changed, setChanged] = useState(false);
  const [pending, setPending] = useState(false);
  const [failures, setFailures] = useState(0);
  const submitting = useRef(false);
  const form = useRef<HTMLFormElement>(null);
  const focusName = useRef<'current' | 'password' | 'repeat'>('current');
  useEffect(() => {
    if (failures) (form.current?.elements.namedItem(focusName.current) as HTMLInputElement | null)?.focus();
  }, [failures]);

  function fail(message: string, problems: Fields = {}) {
    setFields(problems); setError(message);
    focusName.current = problems.current ? 'current' : problems.password ? 'password' : problems.repeat ? 'repeat' : 'current';
    setFailures(count => count + 1);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (submitting.current) return;
    const problems: Fields = {};
    if (!current) problems.current = 'Enter your current password.';
    if (!passwordAcceptable(password)) problems.password = PASSWORD_RULE_MESSAGE;
    else if (password === current) problems.password = 'Choose a password that is different from your current one.';
    if (repeat !== password) problems.repeat = 'Passwords must match.';
    if (problems.current || problems.password || problems.repeat) { fail('Please check the highlighted fields.', problems); return; }
    submitting.current = true;
    setPending(true); setError(null); setFields({}); setExpired(false);
    try {
      const response = await fetch('/api/change-password', { method: 'POST', cache: 'no-store',
        headers: { 'Content-Type': 'application/json' }, signal: AbortSignal.timeout(20_000),
        body: JSON.stringify({ current_password: current, new_password: password }) });
      const result = await response.json().catch(() => null);
      if (response.ok && result?.changed === true) {
        setCurrent(''); setPassword(''); setRepeat('');
        setChanged(true);
        // Existing tokens were revoked server-side; end this browser session and sign in anew.
        try { await signOut({ callbackUrl: new URL('/login?passwordChanged=1', window.location.href).href }); }
        catch { /* The success notice below links to sign in. */ }
        return;
      }
      if (response.status === 401) { setExpired(true); fail(MESSAGES.sessionEnded); }
      else if (response.status === 422 && result?.fields) {
        fail('Please check the highlighted fields.', {
          ...(typeof result.fields.current_password === 'string' ? { current: MESSAGES.currentPasswordWrong } : {}),
          ...(typeof result.fields.new_password === 'string' ? { password: MESSAGES.newPasswordRejected } : {}),
        });
      } else fail(response.status === 429 ? MESSAGES.tooMany : MESSAGES.changeUnavailable);
    } catch { fail(MESSAGES.changeUnavailable); }
    setCurrent(''); setPassword(''); setRepeat('');
    setPending(false); submitting.current = false;
  }

  return <AuthShell>
    <PageNavigation back={{ href: consoleUrl(), label: 'your workspace' }} breadcrumbs={[{ label: 'Workspace', href: consoleUrl() }, { label: 'Change password' }]} />
    <div className="auth__form-head"><h1 className="auth__title">Change password</h1><p className="auth__subtitle">Keep your account secure with a unique password.</p></div>
    {changed ? <div className="janso-flow">
      <Notice tone="success">Your password was changed. Signing you out so you can sign in with the new password…</Notice>
      <p className="auth__foot"><a className="janso-link" href="/login?passwordChanged=1">Continue to sign in</a></p>
    </div> : <>
      {error ? <div className="auth__alert"><Notice tone="danger">{error}{expired ? <> <a className="janso-link" href="/login">Sign in again</a></> : null}</Notice></div> : null}
      <form onSubmit={submit} ref={form} noValidate aria-label="Change password" aria-busy={pending}>
        <PasswordField label="Current password" name="current" purpose="current" maxLength={256} required readOnly={pending}
          value={current} error={fields.current}
          onChange={event => { setCurrent(event.target.value); setFields(value => ({ ...value, current: undefined })); }} />
        <PasswordField label="New password" name="password" purpose="new" minLength={MIN_PASSWORD_LENGTH} maxLength={MAX_PASSWORD_LENGTH * 2}
          required readOnly={pending} value={password} error={fields.password} avoid={[current]}
          hint={`${MIN_PASSWORD_LENGTH}–${MAX_PASSWORD_LENGTH} characters. Choose a unique passphrase.`}
          onChange={event => { setPassword(event.target.value); setFields(value => ({ ...value, password: undefined })); }} />
        <PasswordField label="Confirm new password" name="repeat" purpose="new" showStrength={false} minLength={MIN_PASSWORD_LENGTH}
          maxLength={MAX_PASSWORD_LENGTH * 2} required readOnly={pending} value={repeat} error={fields.repeat}
          onChange={event => { setRepeat(event.target.value); setFields(value => ({ ...value, repeat: undefined })); }} />
        <div className="auth__actions"><Button type="submit" block loading={pending} loadingLabel="Changing password…">Change password</Button></div>
      </form>
      <p className="janso-fine">After you change it, every device is signed out and you sign in again with the new password.</p>
      <p className="auth__foot"><a className="janso-link" href={consoleUrl()}>Cancel</a><span aria-hidden="true"> · </span><a className="janso-link" href="/logout">Sign out</a></p>
    </>}
  </AuthShell>;
}
