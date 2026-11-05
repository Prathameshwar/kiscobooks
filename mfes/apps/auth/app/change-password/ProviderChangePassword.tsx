'use client';

import { useRef, useState } from 'react';
import { Button, Notice, PageNavigation } from '@janso/ui';
import { AuthShell } from '../components/AuthShell';
import { consoleUrl, goTo } from '../lib/navigate';

/** Authentik mode: hand the person to the provider's own password-change flow. */
export function ProviderChangePassword() {
  const [pending, setPending] = useState(false), [error, setError] = useState(''), [expired, setExpired] = useState(false);
  const busy = useRef(false);
  async function start() {
    if (busy.current) return; busy.current = true; setPending(true); setError(''); setExpired(false);
    try {
      const response = await fetch('/api/change-password', { method: 'POST', cache: 'no-store' });
      if (response.status === 401) { setExpired(true); setError('Your session has ended. Sign in again before changing your password.'); return; }
      const value = await response.json();
      if (!response.ok || typeof value.destination !== 'string') throw new Error();
      const target = new URL(value.destination);
      if (target.protocol !== 'https:' || target.username || target.password || target.pathname !== '/if/flow/bill-password-change/' || target.search || target.hash) throw new Error();
      goTo(target.href);
    } catch { setError('Password change is temporarily unavailable. Please try again.'); }
    finally { busy.current = false; setPending(false); }
  }
  return <AuthShell>
    <PageNavigation back={{ href: consoleUrl(), label: 'your workspace' }} breadcrumbs={[{ label: 'Workspace', href: consoleUrl() }, { label: 'Change password' }]} />
    <div className="auth__form-head"><h1 className="auth__title">Change password</h1><p className="auth__subtitle">Keep your account secure with a unique password.</p></div>
    <div className="janso-flow">
      {error ? <Notice tone="danger">{error}{expired ? <> <a className="janso-link" href="/login">Sign in again</a></> : null}</Notice> : null}
      <p className="janso-fine">Continue to Authentik to verify your current password and enter your new password twice. Use 6–128 characters. Your configured authentication factors may also be requested.</p>
      <Button block onClick={start} loading={pending} loadingLabel="Connecting…">Continue to change password</Button>
      <p className="janso-fine">Authentik confirms when the password has changed. Then return to KiscoBooks and sign out and back in with your new password.</p>
      <p className="janso-fine">If you sign in through another provider or a passkey, manage your credentials with that provider or contact your administrator.</p>
      <p className="auth__foot"><a className="janso-link" href={consoleUrl()}>Cancel</a><span aria-hidden="true"> · </span><a className="janso-link" href="/logout">Sign out</a></p>
    </div>
  </AuthShell>;
}
