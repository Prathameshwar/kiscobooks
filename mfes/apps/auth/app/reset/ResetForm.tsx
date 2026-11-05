'use client';

import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Button, Notice, PasswordField } from '@janso/ui';
import { AuthShell } from '../components/AuthShell';
import { MESSAGES } from '../lib/local-auth-shared';
import { goTo } from '../lib/navigate';
import { MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH, PASSWORD_RULE_MESSAGE, passwordAcceptable } from '../lib/registration-input';

type Phase = 'checking' | 'invalid' | 'ready' | 'unavailable' | 'disabled';
type Fields = { password?: string; repeat?: string };

async function recover(body: object): Promise<Response> {
  return fetch('/api/local/recover', { method: 'POST', cache: 'no-store',
    headers: { 'Content-Type': 'application/json' }, signal: AbortSignal.timeout(20_000), body: JSON.stringify(body) });
}

export function ResetForm({ token, available }: { token: string | null; available: boolean }) {
  const [phase, setPhase] = useState<Phase>(!available ? 'disabled' : token ? 'checking' : 'invalid');
  const [retry, setRetry] = useState(0);
  const [password, setPassword] = useState('');
  const [repeat, setRepeat] = useState('');
  const [fields, setFields] = useState<Fields>({});
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [failures, setFailures] = useState(0);
  const submitting = useRef(false);
  const form = useRef<HTMLFormElement>(null);
  const focusName = useRef<'password' | 'repeat'>('password');

  // Verify the link before asking for a password, so a spent or expired link says so at once.
  useEffect(() => {
    if (!available || !token) return;
    let active = true;
    setPhase('checking');
    recover({ action: 'inspect', token })
      .then(response => { if (active) setPhase(response.ok ? 'ready' : response.status === 404 ? 'invalid' : 'unavailable'); })
      .catch(() => { if (active) setPhase('unavailable'); });
    return () => { active = false; };
  }, [available, token, retry]);
  useEffect(() => {
    if (failures) (form.current?.elements.namedItem(focusName.current) as HTMLInputElement | null)?.focus();
  }, [failures]);

  function fail(message: string, problems: Fields = {}) {
    setFields(problems); setError(message);
    focusName.current = problems.repeat && !problems.password ? 'repeat' : 'password';
    setFailures(count => count + 1);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (submitting.current || !token) return;
    const problems: Fields = {};
    if (!passwordAcceptable(password)) problems.password = PASSWORD_RULE_MESSAGE;
    if (repeat !== password) problems.repeat = 'Passwords must match.';
    if (problems.password || problems.repeat) { fail('Please check the highlighted fields.', problems); return; }
    submitting.current = true;
    setPending(true); setError(null); setFields({});
    try {
      const response = await recover({ action: 'redeem', token, new_password: password });
      if (response.ok) { setPassword(''); setRepeat(''); goTo('/login?recovery=complete'); return; }
      if (response.status === 404) setPhase('invalid');
      else if (response.status === 422) fail(MESSAGES.recoveryRejected, { password: MESSAGES.recoveryRejected });
      else fail(response.status === 429 ? MESSAGES.tooMany : MESSAGES.recoveryUnavailable);
    } catch { fail(MESSAGES.recoveryUnavailable); }
    setPassword(''); setRepeat('');
    setPending(false); submitting.current = false;
  }

  return <AuthShell>
    <div className="auth__form-head">
      <h1 className="auth__title">Reset your password</h1>
      <p className="auth__subtitle">{phase === 'ready' ? 'Choose a new password for your KiscoBooks account.' : 'Use the one-time link your administrator gave you.'}</p>
    </div>
    {phase === 'checking' ? <p role="status">Checking your recovery link…</p> : null}
    {phase === 'disabled' ? <Notice tone="info">Password recovery on this page is not enabled for this installation.</Notice> : null}
    {phase === 'invalid' ? <Notice tone="danger">{MESSAGES.recoveryInvalid}</Notice> : null}
    {phase === 'unavailable' ? <>
      <Notice tone="warning">{MESSAGES.recoveryUnavailable}</Notice>
      <div className="auth__actions"><Button variant="ghost" onClick={() => setRetry(count => count + 1)}>Try again</Button></div>
    </> : null}
    {phase === 'ready' ? <>
      {error ? <div className="auth__alert"><Notice tone="danger">{error}</Notice></div> : null}
      <form onSubmit={submit} ref={form} noValidate aria-label="Reset password" aria-busy={pending}>
        <PasswordField label="New password" name="password" purpose="new" minLength={MIN_PASSWORD_LENGTH} maxLength={MAX_PASSWORD_LENGTH * 2}
          required readOnly={pending} value={password} error={fields.password}
          hint={`${MIN_PASSWORD_LENGTH}–${MAX_PASSWORD_LENGTH} characters. Choose a unique passphrase.`}
          onChange={event => { setPassword(event.target.value); setFields(current => ({ ...current, password: undefined })); }} />
        <PasswordField label="Confirm new password" name="repeat" purpose="new" showStrength={false} minLength={MIN_PASSWORD_LENGTH}
          maxLength={MAX_PASSWORD_LENGTH * 2} required readOnly={pending} value={repeat} error={fields.repeat}
          onChange={event => { setRepeat(event.target.value); setFields(current => ({ ...current, repeat: undefined })); }} />
        <div className="auth__actions"><Button type="submit" block loading={pending} loadingLabel="Saving…">Set new password</Button></div>
      </form>
    </> : null}
    <p className="auth__foot"><a className="janso-link" href="/login">Back to sign in</a></p>
  </AuthShell>;
}
