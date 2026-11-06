'use client';

import { useEffect, useState } from 'react';
import { signIn } from 'next-auth/react';
import { Button, Notice } from '@janso/ui';
import { AuthShell } from '../components/AuthShell';
import { consoleUrl } from '../lib/navigate';
import { authProviderId, useAuthProvider } from '../lib/provider-client';

export default function LoginPage() {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [returnTo, setReturnTo] = useState(consoleUrl());
  const [setupAvailable, setSetupAvailable] = useState(false);
  const [recovered, setRecovered] = useState(false);
  const [passwordChanged, setPasswordChanged] = useState(false);
  const provider = useAuthProvider();
  useEffect(() => {
    let active = true;
    fetch('/api/setup?action=status', { cache: 'no-store' }).then(response => response.ok ? response.json() : null)
      .then(value => { if (active) setSetupAvailable(value?.available === true); }).catch(() => undefined);
    return () => { active = false; };
  }, []);
  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    const code = query.get('error');
    setRecovered(query.get('recovery') === 'complete' && !code);
    setPasswordChanged(query.get('passwordChanged') === '1' && !code);
    if (code) {
      const messages: Record<string, string> = {
        OAuthSignin: 'The sign-in service is currently unavailable. Please try again shortly. If the problem continues, contact your administrator.',
        AccessDenied: 'Sign in was not completed. Please try again.',
        Configuration: 'Sign in is unavailable because the sign-in service is not configured correctly. Please contact your administrator.',
        SessionUnavailable: 'Your session could not be refreshed. Please try again.',
        SessionExpired: 'Your session has ended. Please sign in again.',
      };
      setError(messages[code] ?? 'Unable to complete sign in. Please try again.');
    }
    try {
      const base = new URL(consoleUrl(), window.location.href);
      const target = new URL(query.get('returnTo') ?? query.get('callbackUrl') ?? base.href, base);
      if (target.origin === base.origin && !target.username && !target.password) setReturnTo(target.href);
      if (target.origin === window.location.origin && target.pathname === '/setup' && !target.username && !target.password) {
        setReturnTo(target.href);
      }
    } catch { /* Use the configured Console destination. */ }
  }, []);
  async function login() {
    setPending(true);
    setError(null);
    try {
      const destination = new URL(returnTo);
      const callbackUrl = destination.origin === window.location.origin && destination.pathname === '/setup' ? returnTo
        : window.location.origin + '/onboarding?returnTo=' + encodeURIComponent(returnTo);
      await signIn(provider ?? await authProviderId(), { callbackUrl },
        // Authentik 2026.8 treats max_age=0 as unset. A positive bound also resets
        // its remembered reauthentication state before issuing another access token.
        // The local provider has no SSO cookie and always asks for the password, so it
        // ignores both parameters.
        { prompt: 'login', max_age: new URL(returnTo).pathname === '/setup' ? '300' : '1' });
    } catch {
      setError('Unable to start sign in. Please try again.');
      setPending(false);
    }
  }
  return (
    <AuthShell>
      <div className="auth__form-head">
        <h1 className="auth__title">Welcome back</h1>
        <p className="auth__subtitle">Sign in to your books.</p>
      </div>
      {error ? (
        <div className="auth__alert">
          <Notice tone="danger">{error}</Notice>
        </div>
      ) : null}
      {recovered && provider ? <div className="auth__alert"><Notice tone="info">{provider === 'local'
        ? 'After resetting your password, continue to sign in with your new password.'
        : 'After completing recovery in Authentik, continue to sign in with your new password.'}</Notice></div> : null}
      {passwordChanged && provider === 'local' ? <div className="auth__alert"><Notice tone="info">If you just changed your password, sign in again with your new password.</Notice></div> : null}
      <Button block onClick={login} loading={pending} loadingLabel="Connecting…">
        Continue to sign in
      </Button>
      <div className="auth__foot auth__foot--band">
        <p className="auth__foot--links">
          <span className="auth__account-question">New to KiscoBooks?</span>
          <a className="janso-link" href="/signup">Create account</a>
          <a className="janso-link auth__forgot-password" href={'/recover?returnTo=' + encodeURIComponent(returnTo)}>Forgot password?</a>
        </p>
        {setupAvailable ? <p><a className="janso-link" href="/setup">Set up this platform</a></p> : null}
      </div>
    </AuthShell>
  );
}
