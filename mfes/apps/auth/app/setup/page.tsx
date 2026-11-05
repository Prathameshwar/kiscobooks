'use client';

import { useEffect, useRef, useState, type FormEvent } from 'react';
import { signIn } from 'next-auth/react';
import { Badge, Button, Card, CardBody, Checkbox, EmailField, Notice, PasswordField, Select, Skeleton,
  Stepper, TextField, ThemeSwitcher, Wordmark } from '@janso/ui';
import type { components } from '@janso/api-client/identity';
import { authProviderId } from '../lib/provider-client';
import { MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH, PASSWORD_RULE_MESSAGE, passwordAcceptable } from '../lib/registration-input';

type Draft = components['schemas']['SetupRequest'];
type Checks = components['schemas']['SetupChecks'];
const UNLOCK = 'Unlock setup', CONNECTIONS = 'Connections', DETAILS = 'Platform details',
  WORKSPACE = 'Administration workspace', CREATE = 'Create administrator account', ADMIN = 'First administrator',
  EMAIL_STEP = 'Email delivery', REVIEW = 'Review and complete';
const baseSteps = [UNLOCK, CONNECTIONS, DETAILS, WORKSPACE, ADMIN, EMAIL_STEP, REVIEW];
// Local provider only, until an administrator account exists: it has to be created before anyone
// can sign in as one. Inserted before 'First administrator'; every other step keeps its meaning.
const stepsWith = (create: boolean) => create ? [...baseSteps.slice(0, 4), CREATE, ...baseSteps.slice(4)] : baseSteps;
const defaults: Draft = { platform_name: 'KiscoBooks', public_url: 'http://localhost:4320',
  workspace_name: 'Platform Administration', workspace_slug: 'platform-admin',
  administrator_name: '', country_code: 'IN', currency_code: 'INR', timezone: 'Asia/Kolkata', locale: 'en' };

async function request(action: string, body?: unknown) {
  const response = await fetch(`/api/setup${body === undefined ? `?action=${action}` : ''}`, {
    ...(body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action, ...(body as object) }) }), cache: 'no-store',
  });
  const value = await response.json().catch(() => null);
  if (!response.ok) throw new Error(value?.error ?? 'Setup is unavailable. Please try again.');
  return value;
}

export default function SetupPage() {
  const [step, setStep] = useState(0);
  const [draft, setDraft] = useState<Draft>(defaults);
  const [key, setKey] = useState('');
  const [checks, setChecks] = useState<Checks | null>(null);
  const [email, setEmail] = useState('');
  const [pending, setPending] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [closed, setClosed] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [local, setLocal] = useState(false);
  const [needsAdministrator, setNeedsAdministrator] = useState(false);
  const [created, setCreated] = useState(false);
  const [account, setAccount] = useState({ email: '', password: '', repeat: '' });
  const [result, setResult] = useState<{ verified: boolean; destination: string } | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const steps = stepsWith(needsAdministrator);
  const current = steps[step];

  useEffect(() => {
    let active = true;
    request('status').then(async state => {
      if (!active) return;
      if (state.completed || !state.available) { setClosed(true); return; }
      const isLocal = state.provider === 'local';
      const create = isLocal && state.administratorExists === false;
      setLocal(isLocal); setNeedsAdministrator(create);
      if (state.draft) setDraft({ ...defaults, ...state.draft });
      else if (state.applicationUrl) setDraft(previous => ({ ...previous, public_url: state.applicationUrl }));
      if (state.unlocked) {
        setStep(1);
        const data = await request('checks');
        if (!active) return;
        setChecks(data);
        if (new URLSearchParams(window.location.search).get('administrator') === '1') {
          setStep(stepsWith(create).indexOf(ADMIN));
          const profile = await request('administrator');
          if (active) setEmail(profile.email);
        }
      }
    }).catch(err => { if (active) setError(err.message); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);
  useEffect(() => { if (!loading) heading.current?.focus(); }, [step, loading]);

  function change(name: keyof Draft, value: string) {
    setConfirmed(false);
    setDraft(previous => ({ ...previous, [name]: value }));
  }
  async function run(action: () => Promise<void>) {
    setPending(true); setError('');
    try { await action(); } catch (err) { setError(err instanceof Error ? err.message : 'Setup failed. Please retry.'); }
    finally { setPending(false); }
  }
  async function testConnections() { setChecks(await request('checks')); }
  function next(event: FormEvent) {
    event.preventDefault();
    void run(async () => {
      if (current === UNLOCK) {
        const unlocked = await request('unlock', { key });
        if (unlocked.applicationUrl) change('public_url', unlocked.applicationUrl);
        // Whether an administrator account exists is revealed only to an unlocked caller.
        if (local) setNeedsAdministrator((await request('status')).administratorExists === false);
        setKey(''); setStep(1); await testConnections(); return;
      }
      if (current === CONNECTIONS && !checks?.ready) throw new Error('Resolve the failed connection checks before continuing.');
      if (current === CREATE && !created) {
        const name = draft.administrator_name.trim();
        if (!name || Array.from(name).length > 100) throw new Error('Enter the administrator’s full name (up to 100 characters).');
        if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(account.email.trim())) throw new Error('Enter a valid email address.');
        if (!passwordAcceptable(account.password)) throw new Error(PASSWORD_RULE_MESSAGE);
        if (account.repeat !== account.password) throw new Error('The passwords do not match.');
        try {
          await request('create-administrator', { name, email: account.email.trim(), password: account.password, password_repeat: account.repeat });
          setCreated(true);
        } finally { setAccount(previous => ({ ...previous, password: '', repeat: '' })); }
      }
      if (current === ADMIN && !email) throw new Error(local ? 'Sign in as the administrator before continuing.' : 'Sign in through Authentik before continuing.');
      if (current === REVIEW) {
        if (!confirmed) throw new Error('Confirm the administrator and settings before completing setup.');
        setResult(await request('complete', { draft })); return;
      }
      if (step >= 2) await request('save', { draft });
      setStep(value => value + 1);
    });
  }
  async function authenticate() {
    setConfirmed(false); setEmail('');
    await request('save', { draft });
    await signIn(await authProviderId(), { callbackUrl: `${window.location.origin}/setup?administrator=1` },
      { prompt: 'login', max_age: '300' });
  }
  const details = [ ['Platform', draft.platform_name], ['Application URL', draft.public_url],
    ['Country / currency', `${draft.country_code} / ${draft.currency_code}`], ['Time zone', draft.timezone],
    ['Language', draft.locale],
    ['Workspace', draft.workspace_name], ['Workspace code', draft.workspace_slug],
    ['Administrator', draft.administrator_name], ['Verified email', email] ];

  return <div className="janso-setup">
    <header className="janso-setup__header"><Wordmark /><ThemeSwitcher /></header>
    <div className="janso-setup__layout">
      <Stepper steps={steps} current={step} onStep={!pending && !closed && !result ? target => {
        if (target !== 0 || step === 0) { setError(''); setStep(target); }
      } : undefined} />
      <main className="janso-setup__content">
        <div><h1 ref={heading} tabIndex={-1} className="janso-setup__title">
          {result ? 'Platform setup completed' : closed ? 'Setup is closed' : current}</h1>
          <p className="janso-setup__subtitle">Set up your billing platform securely.</p></div>
        {error ? <Notice tone="danger">{error}</Notice> : null}
        {error && !loading && current === UNLOCK ? <Button type="button" variant="ghost" onClick={() => window.location.reload()}>Reload setup status</Button> : null}
        {loading ? <Skeleton /> : closed ? <Notice tone="info" title="First-run setup is unavailable">
          Setup has completed, existing tenants are present, or setup has not been enabled on the server.
          <p><a className="janso-link" href="/login">Continue to sign in</a></p></Notice> : result ? <Card><CardBody>
          <Notice tone={result.verified ? 'success' : 'warning'}>{result.verified
            ? 'Your administrator account is active and platform access was verified.'
            : 'Setup was saved. Platform access could not be verified yet; check Identity and sign in again.'}</Notice>
          <p><a className="janso-link" href={result.destination}>Open platform administration</a></p>
        </CardBody></Card> : <Card><CardBody><form onSubmit={next}>
          <div className="janso-setup__fields">
            {current === UNLOCK ? <>
              <Notice tone="info">Use the setup key saved on the host computer in start/win/platform-setup/setup-key.txt.</Notice>
              <TextField label="One-time setup key" type="password" autoComplete="off" required value={key}
                onChange={event => setKey(event.target.value)} maxLength={128} hint="This key is never saved in browser storage." />
            </> : null}
            {current === CONNECTIONS ? <>
              <p>Check the server connections before creating your platform administrator.</p>
              <div className="janso-setup__checks">{checks?.checks.map(check => <div key={check.name} className="janso-setup__check">
                <div><strong>{check.name}</strong><div>{check.message}</div></div>
                <Badge tone={check.status === 'ready' ? 'success' : check.status === 'failed' ? 'danger' : 'neutral'}>
                  {check.status === 'ready' ? 'Ready' : check.status === 'failed' ? 'Needs attention' : 'Optional'}</Badge>
              </div>)}</div>
              <Button variant="ghost" type="button" disabled={pending} onClick={() => void run(testConnections)}>Test connections again</Button>
            </> : null}
            {current === DETAILS ? <>
              <TextField label="Platform name" required maxLength={200} value={draft.platform_name} onChange={e => change('platform_name', e.target.value)} />
              <TextField label="Public application URL" type="url" required maxLength={2048} value={draft.public_url} onChange={e => change('public_url', e.target.value)} hint="Use the configured application origin. Changing this record does not reconfigure the server addresses. Use HTTPS when deployed." />
              <Select label="Country" required placeholder="Choose a country" value={draft.country_code} onChange={value => change('country_code', value)} options={checks?.countries.map(c => ({ value: c.code, label: c.name })) ?? []} />
              <Select label="Default currency" required placeholder="Choose a currency" value={draft.currency_code} onChange={value => change('currency_code', value)} options={checks?.currencies.map(c => ({ value: c.code, label: `${c.code} — ${c.name}` })) ?? []} />
              <Select label="Time zone" required placeholder="Choose a timezone" value={draft.timezone} onChange={value => change('timezone', value)} options={checks?.timezones.map(c => ({ value: c.code, label: c.name })) ?? []} />
              <Select label="Language" required placeholder="Choose a language" value={draft.locale ?? 'en'} onChange={value => change('locale', value)} options={checks?.languages.map(c => ({ value: c.code, label: c.name + ' (' + c.code + ')' })) ?? []} />
            </> : null}
            {current === WORKSPACE ? <>
              <TextField label="Administration workspace name" required maxLength={200} value={draft.workspace_name} onChange={e => change('workspace_name', e.target.value)} />
              <TextField label="Workspace code" required pattern="[a-z][a-z0-9-]{2,62}" maxLength={63} value={draft.workspace_slug} onChange={e => change('workspace_slug', e.target.value)} hint="3–63 lowercase letters, numbers or hyphens; begin with a letter." />
              <Notice tone="info">This internal tenant holds platform administrators. Customer tenants are created separately after setup.</Notice>
            </> : null}
            {current === CREATE ? (created ? <Notice tone="success">The administrator account was created. Continue to sign in as the administrator.</Notice> : <>
              <Notice tone="info">Create the sign-in for the first platform administrator. You use it to finish setup and then to manage the platform.</Notice>
              <TextField label="Administrator full name" required maxLength={100} autoComplete="name" value={draft.administrator_name} onChange={e => change('administrator_name', e.target.value)} />
              <EmailField label="Administrator email address" required value={account.email} onChange={value => setAccount(previous => ({ ...previous, email: value }))} />
              <PasswordField label="Password" purpose="new" required minLength={MIN_PASSWORD_LENGTH} maxLength={MAX_PASSWORD_LENGTH * 2}
                value={account.password} avoid={[account.email, draft.administrator_name]} hint={`${MIN_PASSWORD_LENGTH}–${MAX_PASSWORD_LENGTH} characters. Choose a unique passphrase.`}
                onChange={e => setAccount(previous => ({ ...previous, password: e.target.value }))} />
              <PasswordField label="Confirm password" purpose="new" required showStrength={false} minLength={MIN_PASSWORD_LENGTH} maxLength={MAX_PASSWORD_LENGTH * 2}
                value={account.repeat} onChange={e => setAccount(previous => ({ ...previous, repeat: e.target.value }))} />
            </>) : null}
            {current === ADMIN ? <>
              <TextField label="Administrator full name" required maxLength={100} value={draft.administrator_name} onChange={e => change('administrator_name', e.target.value)} />
              {email ? <EmailField label="Verified email" value={email} readOnly onChange={() => undefined} /> : <Notice tone="info">{local
                ? 'Sign in as the platform administrator account. Its email must be verified.'
                : 'Sign in through Authentik using the account that should become the first platform administrator. Its email must be verified.'}</Notice>}
              <Button type="button" variant="ghost" disabled={!draft.administrator_name.trim()} loading={pending} onClick={() => void run(authenticate)}>
                {email ? 'Sign in again' : local ? 'Sign in as the administrator' : 'Sign in through Authentik'}</Button>
            </> : null}
            {current === EMAIL_STEP ? <>
              <Notice tone="info" title="Optional email delivery">You can complete setup without email. Sender and transport credentials are configured on the Notification server.</Notice>
              <p>Ask the server administrator to configure and test the email transport before sending customer invitations. These settings can be completed after platform setup.</p>
              <p>Choose Next to continue without configuring email here.</p>
            </> : null}
            {current === REVIEW ? <>
              <dl className="janso-setup__review">{details.map(([label, value]) => <div key={label}>
                <dt>{label}</dt><dd>{value}</dd></div>)}</dl>
              <Notice tone="warning">{local ? 'The signed-in administrator account' : 'The signed-in Authentik account'} will become the first platform administrator. Successful completion permanently closes first-run setup.</Notice>
              <Checkbox checked={confirmed} onChange={e => setConfirmed(e.target.checked)}>I confirm this administrator and these platform settings.</Checkbox>
            </> : null}
          </div>
          <div className="janso-setup__actions">
            <Button type="button" variant="ghost" disabled={step === 0 || pending} onClick={() => { setError(''); setStep(value => value - 1); }}>Back</Button>
            <Button type="submit" loading={pending} disabled={(current === CONNECTIONS && !checks?.ready) || (current === ADMIN && !email) || (current === REVIEW && !confirmed)}
              loadingLabel={current === REVIEW ? 'Completing setup…' : 'Working…'}>{current === UNLOCK ? 'Unlock setup' : current === REVIEW ? 'Complete setup' : current === CREATE && !created ? 'Create administrator' : 'Next'}</Button>
          </div>
        </form></CardBody></Card>}
      </main>
    </div>
  </div>;
}
