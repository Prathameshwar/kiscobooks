'use client';
import { useEffect, useState } from 'react';
import type { components } from '@janso/api-client/identity';
import { Badge, Button, ErrorState, Notice, PageHeader, PageNavigation, Skeleton, asErrorStatus } from '@janso/ui';
import type { Session } from '../session';
import { companyCall, companyFailure, type CompanyFailure } from '../lib/company-api';
import { companyPermission } from '../lib/company-permissions';
import { administrationDirectoryReturn, administrationLink, administrationReturn } from '../lib/administration-navigation';
import { accountingBack, accountingLink } from '../lib/accounting-configuration-resources';
import { signInUrl, stepUpUrl } from '../lib/navigate';
import { useAccessDraft } from './AccessCommon';
import { CompanyGstRegistration, type TaxFormActivity } from './CompanyGstRegistration';

type Profile = components['schemas']['CompanyDetail'];
function configurationBack(companyId: string, returnTo?: string) {
  const path = '/companies/' + companyId + '/configuration';
  let parent: string | undefined;
  try {
    const candidate = new URL(returnTo ?? path, 'https://console.invalid');
    if (candidate.origin === 'https://console.invalid' && candidate.pathname === path && candidate.searchParams.getAll('returnTo').length === 1) parent = candidate.searchParams.get('returnTo') ?? undefined;
  } catch { /* A direct visit returns to this company's configuration. */ }
  const accounting = parent?.startsWith('/accounting') ? accountingBack(parent, '') : '';
  return accounting ? accountingLink(path, accounting) : administrationLink(path, administrationReturn('companies', parent));
}

export function CompanyGstSettings({ session, companyId, returnTo }: { session: Session; companyId: string; returnTo?: string }) {
  const canRead = companyPermission(session, 'company.read', companyId);
  const base = '/companies/' + companyId, back = configurationBack(companyId, returnTo);
  const here = base + '/gst-settings?' + new URLSearchParams({ returnTo: back });
  const login = signInUrl(), signIn = login + (login.includes('?') ? '&' : '?') + new URLSearchParams({ returnTo: here });
  const [profile, setProfile] = useState<Profile | null>(null), [failure, setFailure] = useState<CompanyFailure | null>(null);
  const [loading, setLoading] = useState(canRead), [revision, setRevision] = useState(0);
  const [activity, setActivity] = useState<TaxFormActivity>({ dirty: false, pending: false });
  const guard = useAccessDraft(activity.dirty, activity.pending);
  useEffect(() => {
    const abort = new AbortController(); setProfile(null); setFailure(null); setLoading(canRead);
    if (canRead) void companyCall<Profile>('identity', '/v1/companies/' + companyId, { signal: abort.signal }).then(value => {
      if (abort.signal.aborted) return;
      if (value.id !== companyId) throw { status: 502, message: 'The company response could not be verified. Reload GST settings.' };
      setProfile(value); setLoading(false);
    }).catch(value => { if (!abort.signal.aborted) { setFailure(companyFailure(value)); setLoading(false); } });
    return () => abort.abort();
  }, [companyId, canRead, revision]);
  function refresh() { if (!activity.dirty && !activity.pending) setRevision(value => value + 1); }
  const applicable = profile?.country_code === 'IN' && profile.default_tax_system === 'gst_in';
  return <div className="janso-page">
    <PageNavigation back={{ href: back, label: 'company configuration' }} breadcrumbs={[
      { label: 'Administration', href: '/organisation' },
      { label: 'Companies', href: administrationDirectoryReturn('companies', back) },
      { label: profile?.display_name ?? 'Company details', href: administrationLink(base, back) },
      { label: 'Configuration', href: back }, { label: 'GST settings' },
    ]} onNavigate={guard.leave} />
    <PageHeader title="GST settings" lede="Manage GST registrations and dated outward reporting profiles for this company." meta={profile && <><span>{profile.display_name ?? 'Company'}</span><Badge tone={profile.status === 'active' ? 'success' : 'warn'}>{profile.status}</Badge></>} actions={applicable && <Button variant="ghost" disabled={loading || activity.dirty || activity.pending} onClick={refresh}>Refresh GST settings</Button>} />
    {!canRead ? <ErrorState status={403} detail="Company read access is required for this company." />
      : loading ? <div role="status" aria-label="Loading GST settings"><Skeleton /></div>
      : failure ? <ErrorState status={asErrorStatus(failure.status)} detail={failure.message} action={failure.status === 401 ? <a className="janso-link" href={signIn}>Sign in again</a> : failure.code === 'step_up_required' ? <a className="janso-link" href={stepUpUrl(companyId)}>Verify sign-in</a> : failure.status !== 403 ? <Button onClick={refresh}>Reload GST settings</Button> : undefined} />
      : profile && (applicable ? <>
        {profile.status !== 'active' && <Notice tone="warning">This company is {profile.status}. Review its history; changes require an active company.</Notice>}
        <CompanyGstRegistration key={companyId + ':' + revision} company={companyId} onActivity={setActivity} onNavigate={guard.leave} canOpenReports={session.company.id === companyId && companyPermission(session, 'report.read', companyId)} />
      </> : <Notice>GST settings are available for companies using GST (India). Review this company's tax framework in company configuration.</Notice>)}
    {guard.confirmation}
  </div>;
}
