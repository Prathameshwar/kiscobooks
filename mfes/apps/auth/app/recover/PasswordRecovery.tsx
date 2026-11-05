'use client';

import { useRef, useState } from 'react';
import { Button, Notice, PageNavigation } from '@janso/ui';
import { AuthShell } from '../components/AuthShell';
import { goTo } from '../lib/navigate';

/** `local` selects the local provider's copy: recovery by a one-time link an administrator issues. */
export function PasswordRecovery({ destination, signInHref, local = false }: { destination: string | null; signInHref: string; local?: boolean }) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState(false);
  const busy = useRef(false);
  function start() {
    if (busy.current || !destination) return;
    busy.current = true; setPending(true); setError(false);
    try { goTo(destination); }
    catch { busy.current = false; setPending(false); setError(true); }
  }
  return <AuthShell>
    <PageNavigation back={{ href: signInHref, label: 'sign in' }}
      breadcrumbs={[{ label: 'Sign in', href: signInHref }, { label: 'Forgot password' }]} />
    <div className="auth__form-head">
      <h1 className="auth__title">Forgot password?</h1>
      <p className="auth__subtitle">Get back to your workspace securely.</p>
    </div>
    <div className="janso-flow">
      {error ? <Notice tone="danger">We could not open password recovery. Please try again or contact your administrator.</Notice> : null}
      {local ? <>
        <Notice tone="info">Password recovery is by a one-time link from your administrator.</Notice>
        <p>Contact your workspace or platform administrator and ask for a password recovery link. They must verify your identity before sharing it securely.</p>
        <p className="janso-fine">The link expires after 10 minutes and can be used once. Open it to choose a new password, then return here to sign in. No email has been sent from this page.</p>
        <p className="janso-fine">If your account is still awaiting approval, contact your administrator.</p>
      </> : destination ? <>
        <p>Authentik will help you reset the password for your KiscoBooks account.</p>
        <ol className="janso-flow">
          <li>Enter the email address registered to your account.</li>
          <li>If your account is eligible, open the recovery link in your inbox. It expires after 10 minutes and can be used once.</li>
          <li>Complete any configured authentication checks, then enter and confirm your new password.</li>
        </ol>
        <Button block onClick={start} loading={pending} loadingLabel="Opening recovery…">Continue to reset password</Button>
        <p className="janso-fine">Check your spam folder if the message does not arrive. Wait a few minutes before requesting another link, or contact your administrator.</p>
      </> : <>
        <Notice tone="warning">Email password recovery is not available yet.</Notice>
        <p>Contact your workspace or platform administrator and ask for a password recovery link. They must verify your identity before sharing it securely.</p>
        <p className="janso-fine">The link expires after 10 minutes. Open it to confirm your new password in Authentik, then return here to sign in. No email has been sent from this page.</p>
      </>}
      {local ? null : <p className="janso-fine">For another sign-in provider or an account awaiting approval, contact your administrator. Existing authentication factors remain required.</p>}
      <p className="auth__foot"><a className="janso-link" href={signInHref}>Back to sign in</a></p>
    </div>
  </AuthShell>;
}
