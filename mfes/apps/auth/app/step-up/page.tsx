"use client";
import { useState } from 'react';
import { signIn } from 'next-auth/react';
import { Button } from '@janso/ui';
import { AuthShell } from '../components/AuthShell';
import { consoleUrl, goTo } from '../lib/navigate';
import { authProviderId } from '../lib/provider-client';
export default function StepUpPage() {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function verify() {
    setPending(true); setError(null);
    try {
      const params = new URLSearchParams(window.location.search);
      const company = params.get('company');
      const challenge = params.get('challenge');
      const complete = params.get('complete') === '1' && challenge;
      let returnTo = consoleUrl();
      try {
        const base = new URL(consoleUrl(), window.location.href);
        const target = new URL(params.get('returnTo') ?? base.href, base);
        if (target.origin === base.origin && !target.username && !target.password) returnTo = target.href;
      } catch { /* Keep the configured Console destination. */ }
      const response = await fetch('/api/step-up', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ company, challenge, action: complete ? 'complete' : 'challenge' }) });
      if (response.status === 401) { await signIn(await authProviderId(), { callbackUrl: window.location.href }); return; }
      if (!response.ok) { setError('Verification is unavailable or expired. Start again from your company.'); return; }
      if (complete) { goTo(returnTo); return; }
      const value = await response.json();
      const callback = new URL('/step-up', window.location.origin);
      callback.search = new URLSearchParams({ company: company ?? '', challenge: value.challenge, complete: '1' }).toString();
      callback.searchParams.set('returnTo', returnTo);
      await signIn(await authProviderId(), { callbackUrl: callback.href }, { prompt: 'login', max_age: '1' });
    } catch { setError('Unable to verify your identity. Please try again.'); }
    finally { setPending(false); }
  }
  return <AuthShell><h1 className="auth__title">Verify company access</h1>
    <p className="auth__subtitle">This company requires a fresh sign-in. Access lasts five minutes.</p>
    {error && <p role="alert">{error}</p>}
    <Button onClick={verify} disabled={pending}>{pending ? 'Verifying...' : 'Continue verification'}</Button>
  </AuthShell>;
}
