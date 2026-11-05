'use client';

import { useEffect, useState } from 'react';
import { signIn, signOut } from 'next-auth/react';
import { Button, Notice } from '@janso/ui';
import { AuthShell } from '../components/AuthShell';
import { consoleUrl, goTo } from '../lib/navigate';
import { authProviderId } from '../lib/provider-client';

const RESUME_KEY = 'janso-invitation-resume';

function resumeUrl(): string {
  const nonce = crypto.randomUUID();
  sessionStorage.setItem(RESUME_KEY, nonce);
  const url = new URL(window.location.href);
  url.searchParams.set('resume', nonce);
  return url.href;
}

export default function AcceptInvitationPage() {
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [switchAccount, setSwitchAccount] = useState(false);
  const [signupHref, setSignupHref] = useState<string | null>(null);
  useEffect(() => {
    const url = new URL(window.location.href);
    const nonce = url.searchParams.get('resume');
    url.searchParams.delete('resume');
    if (url.searchParams.has('tenant') && url.searchParams.has('invitation')) {
      setSignupHref('/signup?returnTo=' + encodeURIComponent(url.pathname + url.search));
    }
    if (!nonce || nonce !== sessionStorage.getItem(RESUME_KEY)) return;
    sessionStorage.removeItem(RESUME_KEY);
    window.history.replaceState(null, '', url);
    void accept(true);
  // The return marker is consumed once, on mount after the provider redirect.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  async function accept(automatic = false) {
    setPending(true); setMessage(null); setSwitchAccount(false);
    try {
      const query = new URLSearchParams(window.location.search);
      const response = await fetch('/api/invitations/accept', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tenant: query.get('tenant'), invitation: query.get('invitation') }),
      });
      if (response.status === 401) {
        if (automatic) { setMessage('Sign in did not complete. Please try again.'); return; }
        await signIn(await authProviderId(), { callbackUrl: resumeUrl() }, { prompt: 'login', max_age: '1' });
        return;
      }
      if (response.status === 403) {
        setMessage('The signed-in account cannot accept this invitation. Use the invited email after it is verified by the sign-in provider.');
        setSwitchAccount(true);
        return;
      }
      if (!response.ok) { setMessage('This invitation is unavailable, or your verified email does not match.'); return; }
      goTo(consoleUrl());
    } catch { setMessage('Unable to reach the service. Please try again.'); }
    finally { setPending(false); }
  }
  async function useInvitedAccount() {
    setPending(true); setMessage(null);
    try { await signOut({ callbackUrl: window.location.href }); }
    catch { setMessage('Unable to sign out. Please try again.'); }
    finally { setPending(false); }
  }
  return <AuthShell><div className="auth__invitation">
    <div className="auth__form-head">
      <h1 className="auth__title">Accept your invitation</h1>
      <p className="auth__subtitle">Join your workspace using the invited email address.</p>
    </div>
    {message ? <div className="auth__alert"><Notice tone="danger">{message}</Notice></div> : null}
    <div className="auth__invite-guide" aria-label="Ways to join">
      <section className="auth__invite-option">
        <h2>Already have an account?</h2>
        <p>Sign in with the invited email. We will add your workspace after verification.</p>
      </section>
      <section className="auth__invite-option">
        <h2>New to KiscoBooks?</h2>
        <p>Create an account with the invited email. Your platform administrator must complete approval and email verification before you can join.</p>
      </section>
    </div>
    <Button block onClick={() => void accept()} disabled={pending}>{pending ? 'Connecting…' : 'Accept invitation'}</Button>
    {switchAccount ? <div className="auth__invite-secondary"><Button block variant="ghost" onClick={useInvitedAccount} disabled={pending}>Sign in with invited account</Button></div> : null}
    <nav className="auth__invite-links" aria-label="Invitation links">
      {signupHref ? <span>Need an account? <a className="janso-link" href={signupHref}>Create an account</a></span> : null}
      <a className="janso-link" href={consoleUrl()}>Go to Home</a>
    </nav>
  </div>
  </AuthShell>;
}
