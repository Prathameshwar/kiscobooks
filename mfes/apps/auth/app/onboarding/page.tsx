'use client';

import { useEffect, useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import { signIn } from 'next-auth/react';
import { Button, CheckIcon, Notice, Select, StoreIcon, TextField } from '@janso/ui';
import type { components } from '@janso/api-client/identity';
import { AuthShell } from '../components/AuthShell';
import { consoleUrl, goTo } from '../lib/navigate';
import { authProviderId } from '../lib/provider-client';
import { parseChoices, parseRegion, regionErrors } from '../lib/registration-regions';

export default function OnboardingPage() {
  const [state, setState] = useState<'loading' | 'opening' | 'signin' | 'verify' | 'ready' | 'error'>('loading');
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [target, setTarget] = useState(consoleUrl());
  const [options, setOptions] = useState<components['schemas']['TenantChoices'] | null>(null);
  const [draft, setDraft] = useState({ name: '', administrator_name: '', country_code: 'IN', state_code: '' });
  const submitting = useRef(false);
  async function check() {
    setState('loading'); setError(null);
    let destination = consoleUrl();
    try { const base = new URL(consoleUrl(), window.location.href), url = new URL(new URLSearchParams(window.location.search).get('returnTo') ?? base.href, base);
      if (url.origin === base.origin && !url.username && !url.password) destination = url.href;
    } catch { /* Configured Console destination. */ }
    setTarget(destination);
    try { const response = await fetch('/api/onboarding', { cache: 'no-store' });
      if (response.status === 401) { setState('signin'); return; }
      const value = await response.json();
      if (!response.ok) throw new Error('Workspace setup is unavailable. Please try again.');
      if (value.linked === true) { flushSync(() => setState('opening')); goTo(destination); return; }
      if (value.email_verified === true && ![value.options?.countries, value.options?.currencies, value.options?.timezones, value.options?.languages].every(items => Array.isArray(items) && items.length)) throw new Error('Regional choices unavailable');
      if (value.email_verified === true && !Array.isArray(value.options?.states)) throw new Error('State choices unavailable');
      setOptions(value.options ?? null);
      const choices = parseChoices(value.options), region = parseRegion(value.registration_region);
      if (choices) setDraft(current => ({ ...current,
        ...(region && !Object.keys(regionErrors(region, choices)).length ? region : {
          country_code: choices.countries.some(item => item.code === current.country_code) ? current.country_code : '',
          state_code: choices.states.some(item => item.code === current.state_code && item.country_code === current.country_code) ? current.state_code : '',
        }) }));
      setState(value.email_verified === true ? 'ready' : 'verify');
    } catch { setState('error'); setError('Workspace setup is unavailable. Please try again.'); }
  }
  useEffect(() => { void check(); }, []);
  async function login() {
    setPending(true); setError(null);
    try { await signIn(await authProviderId(), { callbackUrl: window.location.href }, { prompt: 'login', max_age: '1' }); }
    catch { setError('Unable to start sign in. Try again.'); setPending(false); }
  }
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (submitting.current || !event.currentTarget.reportValidity()) return;
    submitting.current = true; setPending(true); setError(null);
    try { const response = await fetch('/api/onboarding', { method: 'POST', cache: 'no-store', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...draft, state_code: draft.state_code || null }) });
      const value = await response.json();
      if (response.status === 401) { setState('signin'); return; }
      if (!response.ok) { setError(value?.error?.message ?? 'Unable to create your workspace. Try again.'); return; }
      flushSync(() => setState('opening')); goTo(target);
    } catch { setError('Unable to create your workspace. Please try again.'); }
    finally { setPending(false); submitting.current = false; }
  }
  const change = (field: keyof typeof draft, value: string) => setDraft(current => ({ ...current, [field]: value, ...(field === 'country_code' ? { state_code: '' } : {}) }));
  const states = options?.states.filter(item => item.country_code === draft.country_code) ?? [];
  const transitioning = state === 'loading' || state === 'opening';
  return <AuthShell registration>
    {transitioning ? <div className="janso-workspace-transition">
      <div className="janso-workspace-transition__symbol" aria-hidden="true"><StoreIcon /></div>
      <div><h1 className="auth__title">{state === 'opening' ? 'Opening your workspace' : 'Getting things ready'}</h1>
        <p className="auth__subtitle">{state === 'opening' ? 'Taking you to your books, reports and business tools.' : 'Finding your workspace and checking your access.'}</p></div>
      <div className="janso-workspace-transition__progress">
        <p role="status" aria-atomic="true">{state === 'opening' ? 'Workspace access confirmed. Opening your workspace…' : 'Checking your workspace access…'}</p>
        <ol aria-label="Workspace progress">
          <li aria-current={state === 'loading' ? 'step' : undefined}><span aria-hidden="true">{state === 'opening' ? <CheckIcon /> : <span className="janso-spinner" />}</span>Check workspace access</li>
          <li aria-current={state === 'opening' ? 'step' : undefined}><span aria-hidden="true">{state === 'opening' ? <span className="janso-spinner" /> : <StoreIcon />}</span>Open your workspace</li>
        </ol>
      </div>
      <p className="janso-fine">You’ll continue automatically. Keep this page open.</p>
    </div> : <div className="auth__form-head"><h1 className="auth__title">{state === 'ready' ? 'Set up your workspace' : 'Continue to your workspace'}</h1><p className="auth__subtitle">{state === 'ready' ? 'Give your business a secure home for its books.' : 'Access your business securely with KiscoBooks.'}</p></div>}
    {error ? <Notice tone="danger">{error}</Notice> : null}
    {state === 'error' ? <Button onClick={check}>Try again</Button> : null}
    {state === 'signin' || state === 'verify' ? <>
      <p>{state === 'verify' ? 'Your email address must be verified before you can create a workspace. Contact your platform administrator for manual verification, then sign in again.' : 'Sign in with your approved account to create a workspace or open an existing one.'}</p>
      <Button onClick={login} loading={pending}>Sign in to continue</Button>
    </> : null}
    {state === 'ready' ? <form className="janso-registration__form" onSubmit={submit}>
      <fieldset className="janso-registration__section" disabled={pending}><legend>Your business</legend><div className="janso-registration__fields">
        <TextField label="Workspace name" value={draft.name} required maxLength={200} onChange={event => change('name', event.target.value)} />
        <TextField label="Your full name" value={draft.administrator_name} required maxLength={100} autoComplete="name" onChange={event => change('administrator_name', event.target.value)} />
        <div className="janso-form-grid janso-form-grid--pair"><Select label="Country" value={draft.country_code} required placeholder="Choose a country" options={(options?.countries ?? []).map(item => ({ value: item.code, label: item.name + ' (' + item.code + ')' }))} onChange={value => change('country_code', value)} />
          <Select label="State" value={draft.state_code} required={states.length > 0} disabled={!states.length} placeholder="Choose a state" hint={!states.length ? 'No states are available for this country.' : undefined} options={states.map(item => ({ value: item.code, label: item.name }))} onChange={value => change('state_code', value)} /></div>
      </div></fieldset>
      <p className="janso-fine">You become this workspace’s administrator. These defaults apply when you create companies.</p>
      <Button type="submit" loading={pending} loadingLabel="Creating workspace…">Create workspace</Button>
    </form> : null}
    {!transitioning ? <p className="auth__foot">Have a workspace invitation? Use its acceptance link to join that workspace.</p> : null}
  </AuthShell>;
}
