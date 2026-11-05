'use client';

import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Button, TextField, Notice, PasswordField } from '@janso/ui';
import { AuthShell } from '../components/AuthShell';
import { callbackTarget, lockedMessage, MESSAGES, normalizedLogin, validMinutes } from '../lib/local-auth-shared';
import { goTo } from '../lib/navigate';

type Phase = 'ready' | 'expired' | 'unavailable';
type Fields = { identifier?: string; password?: string };

/** One fixed message per outcome. Nothing the server sent is displayed. */
function messageFor(status: number, minutes: number | null, code?: unknown): string {
  switch (status) {
    case 401: return MESSAGES.badCredentials;
    case 403: return code === 'account_disabled' ? MESSAGES.disabled : MESSAGES.pending;
    case 423: return lockedMessage(minutes);
    case 429: return MESSAGES.tooMany;
    case 422: return MESSAGES.loginInput;
    default: return MESSAGES.unavailable;
  }
}

export function SignInForm({ requestId, available }: { requestId: string | null; available: boolean }) {
  const [phase, setPhase] = useState<Phase>(!available ? 'unavailable' : requestId ? 'ready' : 'expired');
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [fields, setFields] = useState<Fields>({});
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [failures, setFailures] = useState(0);
  const submitting = useRef(false);
  const form = useRef<HTMLFormElement>(null);
  const focusName = useRef<'identifier' | 'password'>('identifier');

  // Show "expired" before a password is typed. Only a definite 404 changes anything: if the
  // check itself fails, the form stays usable and the sign-in call gives the definitive answer.
  useEffect(() => {
    if (!available || !requestId) return;
    const controller = new AbortController();
    fetch('/api/local/login?request=' + encodeURIComponent(requestId), { cache: 'no-store', signal: controller.signal })
      .then(response => { if (response.status === 404) setPhase('expired'); })
      .catch(() => undefined);
    return () => controller.abort();
  }, [available, requestId]);
  // Only after a failed attempt, so typing never has focus taken away.
  useEffect(() => {
    if (failures) (form.current?.elements.namedItem(focusName.current) as HTMLInputElement | null)?.focus();
  }, [failures]);

  function fail(message: string, problems: Fields = {}) {
    setFields(problems); setError(message);
    focusName.current = problems.identifier ? 'identifier' : 'password';
    setFailures(count => count + 1);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (submitting.current || !requestId) return;
    const value = normalizedLogin(identifier);
    const problems: Fields = {};
    if (!value) problems.identifier = 'Enter your username or email address.';
    if (!password) problems.password = 'Enter your password.';
    if (problems.identifier || problems.password) { fail(MESSAGES.loginInput, problems); return; }
    submitting.current = true;
    setPending(true); setError(null); setFields({});
    try {
      const response = await fetch('/api/local/login', { method: 'POST', cache: 'no-store',
        headers: { 'Content-Type': 'application/json' }, signal: AbortSignal.timeout(20_000),
        body: JSON.stringify({ request_id: requestId, identifier: value, password }) });
      const result = await response.json().catch(() => null);
      if (response.ok) {
        // Follow only this app's own NextAuth callback, never a URL the server merely names.
        const target = callbackTarget(result?.redirect_to, window.location.origin);
        if (!target) throw new Error('Unexpected sign-in result');
        setPassword('');
        goTo(target);
        return; // Stay busy while the browser navigates; the form must not be submitted twice.
      }
      if (response.status === 404) setPhase('expired');
      else fail(messageFor(response.status, validMinutes(result?.retry_after_minutes), result?.code));
    } catch { fail(MESSAGES.unavailable); }
    // The password is never kept after an attempt that did not sign in.
    setPassword('');
    setPending(false); submitting.current = false;
  }

  return <AuthShell>
    {phase === 'ready' ? <>
      <div className="auth__form-head">
        <h1 className="auth__title">Sign in</h1>
        <p className="auth__subtitle">Enter your username or email address and password.</p>
      </div>
      {error ? <div className="auth__alert"><Notice tone="danger">{error}</Notice></div> : null}
      <form onSubmit={submit} ref={form} noValidate aria-label="Sign in" aria-busy={pending}>
        <TextField label="Username or email address" name="identifier" type="text" autoComplete="username" autoCapitalize="none" spellCheck={false}
          maxLength={254} required readOnly={pending} value={identifier} error={fields.identifier}
          onChange={event => { setIdentifier(event.target.value); setFields(current => ({ ...current, identifier: undefined })); }} />
        <PasswordField label="Password" name="password" purpose="current" maxLength={256} required readOnly={pending} value={password}
          error={fields.password} onChange={event => { setPassword(event.target.value); setFields(current => ({ ...current, password: undefined })); }}
          action={<a className="janso-link auth__field-action" href="/recover">Forgot password?</a>} />
        <div className="auth__actions"><Button type="submit" block loading={pending} loadingLabel="Signing in…">Sign in</Button></div>
      </form>
      <p className="auth__foot auth__foot--band">New to KiscoBooks? <a className="janso-link" href="/signup">Create account</a></p>
    </> : phase === 'expired' ? <>
      <div className="auth__form-head">
        <h1 className="auth__title">Sign-in request expired</h1>
        <p className="auth__subtitle">For your security, a sign-in must be completed within a few minutes.</p>
      </div>
      <Notice tone="warning">{MESSAGES.expiredRequest}</Notice>
      <p className="auth__foot"><a className="janso-link" href="/login">Start sign in again</a></p>
    </> : <>
      <div className="auth__form-head">
        <h1 className="auth__title">Sign in</h1>
      </div>
      <Notice tone="info">Sign in on this page is not enabled for this installation.</Notice>
      <p className="auth__foot"><a className="janso-link" href="/login">Back to sign in</a></p>
    </>}
  </AuthShell>;
}
