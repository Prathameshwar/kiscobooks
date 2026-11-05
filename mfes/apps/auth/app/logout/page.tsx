'use client';

import { useState } from 'react';
import { signOut } from 'next-auth/react';
import { Button, Notice } from '@janso/ui';
import { AuthShell } from '../components/AuthShell';

// Public confirmation screen: visiting a GET URL never changes authentication state.
export default function LogoutPage() {
  const [pending, setPending] = useState(false);
  const [failed, setFailed] = useState(false);
  async function logout() {
    setPending(true);
    setFailed(false);
    try {
      // NextAuth obtains a CSRF token and submits its protected signout POST.
      await signOut({ callbackUrl: new URL('/login?reauth=1', window.location.href).href });
    } catch { setFailed(true); setPending(false); }
  }
  return <AuthShell>
    <div className="auth__form-head">
      <h1 className="auth__title">Sign out</h1>
      <p className="auth__subtitle">Confirm to end your session.</p>
    </div>
    {failed ? <Notice tone="danger">Unable to sign out. Please try again.</Notice> : null}
    <Button block onClick={logout} loading={pending} loadingLabel="Signing out…">Sign out</Button>
  </AuthShell>;
}
