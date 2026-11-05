'use client';

import { useEffect, useState } from 'react';
import { Badge, Button, Card, CardBody, CardHeader, Notice, PageHeader, PageNavigation, ReviewList, formatDateTime, useDisplayConfig } from '@janso/ui';
import type { components } from '@janso/api-client/identity';
import { PlatformError, platformCall, platformFailure, type PlatformFailure } from '../../lib/platform-api';
import { administrationBackLabel, administrationDirectoryReturn, administrationLink, administrationReturn } from '../../lib/administration-navigation';
import { PlatformHistory } from '../../components/PlatformHistory';
import { TenantLifecycleDialog } from './TenantLifecycleDialog';

type Detail = components['schemas']['PlatformTenantDetail'];
type Choices = components['schemas']['TenantChoices'];
export function TenantDetail({ tenantId, permissions, returnTo, ownTenantId }: { tenantId: string; permissions: readonly string[]; returnTo?: string; ownTenantId?: string }) {
  const back = administrationReturn('tenants', returnTo), directory = administrationDirectoryReturn('tenants', back), origin = administrationLink('/platform/tenants/' + tenantId, back);
  const display = useDisplayConfig();
  const [detail, setDetail] = useState<Detail | null>(null), [choices, setChoices] = useState<Choices | null>(null);
  const [error, setError] = useState<PlatformFailure | null>(null), [loading, setLoading] = useState(true), [reload, setReload] = useState(0);
  const [lifecycle, setLifecycle] = useState<Detail | null>(null), [message, setMessage] = useState('');
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError(null); setDetail(null);
    Promise.all([platformCall<Detail>(`/v1/platform/tenants/${tenantId}`, 'GET', undefined, undefined, controller.signal),
      platformCall<Choices>('/v1/platform/tenant-options', 'GET', undefined, undefined, controller.signal).catch(() => null)])
      .then(([record, options]) => { if (!controller.signal.aborted) { setDetail(record); setChoices(options); setLoading(false); } })
      .catch(value => { if (!controller.signal.aborted) { setError(platformFailure(value)); setLoading(false); } });
    return () => controller.abort();
  }, [tenantId, reload]);
  const label = (items: readonly { code: string; name: string }[] | undefined, code: string | null | undefined) => !code ? 'Not specified' : items?.find(item => item.code === code)?.name ?? code;
  const date = (value: string | undefined) => value && Number.isFinite(Date.parse(value)) ? formatDateTime(value, display) : 'Not available';
  return <div className="janso-page">
    <PageNavigation back={{ href: back, label: administrationBackLabel(back) }} breadcrumbs={[{ label: 'Platform administration', href: '/platform' }, { label: 'Tenants', href: directory }, { label: detail?.name ?? 'Tenant details' }]} />
    <PageHeader title={detail?.name ?? 'Tenant details'} lede="Workspace identity, regional defaults and access status."
      actions={detail && detail.status !== 'closed' ? <>
        {permissions.includes('platform.config.manage') && <a className="janso-btn janso-btn--primary" href={`/platform/tenants/${tenantId}/edit?returnTo=${encodeURIComponent(origin)}`}>Edit details</a>}
        {permissions.includes('platform.tenant.suspend') && <Button variant="ghost" disabled={tenantId === ownTenantId} title={tenantId === ownTenantId ? 'Your operating workspace cannot be deactivated.' : undefined} onClick={() => setLifecycle(detail)}>{detail.status === 'active' ? 'Deactivate tenant' : 'Activate tenant'}</Button>}
      </> : undefined} />
    {message && <Notice tone="success">{message}</Notice>}
    <PlatformError value={error} returnTo={`/platform/tenants/${tenantId}?returnTo=${encodeURIComponent(back)}`} />
    {loading ? <p role="status">Loading tenant details…</p> : null}
    {error && ![401,403,404].includes(error.status) ? <Button variant="ghost" onClick={() => setReload(value => value + 1)}>Try again</Button> : null}
    {detail ? <>
      {detail.status === 'suspended' ? <Notice tone="warning">Workspace access is suspended. {detail.suspended_reason}</Notice> : null}
      {detail.status === 'closed' ? <Notice>This workspace is closed. Its existing records are retained.</Notice> : null}
      <div className="janso-grid janso-grid--split janso-grid--start">
        <Card><CardHeader title="Workspace details" subtitle="Tenant identity and contact" /><CardBody><ReviewList items={[
          { label: 'Tenant', value: detail.name }, { label: 'Status', value: <Badge tone={detail.status === 'active' ? 'success' : detail.status === 'suspended' ? 'warn' : 'neutral'}>{detail.status}</Badge> },
          { label: 'Primary contact', value: detail.primary_contact_email || 'Not specified' },
          { label: 'Created', value: date(detail.created_at) }, { label: 'Last updated', value: date(detail.updated_at) },
        ]} /></CardBody></Card>
        <Card><CardHeader title="Regional defaults" subtitle="Defaults for new company setup" /><CardBody><ReviewList items={[
          { label: 'Country', value: label(choices?.countries, detail.default_country_code) },
          { label: 'State', value: label(choices?.states, detail.default_state_code) },
          { label: 'Currency', value: label(choices?.currencies, detail.default_currency_code) },
          { label: 'Timezone', value: label(choices?.timezones, detail.default_timezone) },
          { label: 'Language', value: label(choices?.languages, detail.default_locale) },
        ]} /></CardBody></Card>
      </div>
      {permissions.includes('platform.tenant_access.read') && tenantId !== ownTenantId && <Card><CardHeader title="Tenant administrators" subtitle="Manage invitations, activation, deactivation and password recovery." /><CardBody><a className="janso-btn janso-btn--primary" href={'/platform/access/administrators?tenant=' + tenantId}>Manage tenant administrators</a></CardBody></Card>}
      {permissions.includes('platform.tenant.read') ? <PlatformHistory entityType="tenant" entityId={tenantId} revision={detail.updated_at} /> : null}
    </> : null}
    {lifecycle && <TenantLifecycleDialog tenant={lifecycle} returnTo={origin} onClose={() => setLifecycle(null)} onChanged={value => { setMessage(value); setReload(v => v + 1); }} onReview={() => setReload(v => v + 1)} />}
  </div>;
}
