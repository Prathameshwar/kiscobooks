'use client';
import { useEffect, useRef, useState } from 'react';
import type { components } from '@janso/api-client/identity';
import { Badge, Button, Card, CardBody, CardHeader, ConfirmDialog, DataTable, ErrorState, FilterBar, Notice, PageHeader, PageNavigation, ReviewList, Skeleton, TableSearch, TextField, Toolbar, asErrorStatus, useFormatters, type Column } from '@janso/ui';
import type { Session } from '../session';
import { companyCall, companyFailure, type CompanyFailure } from '../lib/company-api';
import { companyPermission } from '../lib/company-permissions';
import { accountingBack, accountingBackLabel, accountingLink, accountingPermission, accountingResources } from '../lib/accounting-configuration-resources';
import { configLink, configRoot } from '../lib/product-configuration';
import { administrationBackLabel, administrationDirectoryReturn, administrationLink, administrationReturn } from '../lib/administration-navigation';
import { signInUrl, stepUpUrl } from '../lib/navigate';
import { useAccessDraft } from './AccessCommon';
import { CompanyTaxContext } from './CompanyTaxContext';
import { taxSystemLabel } from '../lib/company-labels';

type Profile = components['schemas']['CompanyDetail'];
type Catalogue = components['schemas']['FeatureCatalogue'];
type Feature = components['schemas']['SetupFeature'];
type Snapshot = { profile: Profile; catalogue: Catalogue; setup: components['schemas']['CompanySetupReadiness'] };
type Review = { feature: Feature; enabling: boolean; stamp: string };

export function CompanyConfiguration({ session, companyId, returnTo }: { session: Session; companyId: string; returnTo?: string }) {
  const canRead = companyPermission(session, 'company.read', companyId), canUpdate = companyPermission(session, 'company.update', companyId);
  const canConfigureAccounting = session.company.id === companyId && accountingResources.some(resource => companyPermission(session, accountingPermission(resource, 'read'), companyId));
  const base = '/companies/' + companyId, api = '/v1/companies/' + companyId;
  const accountingParent = returnTo?.startsWith('/accounting') ? accountingBack(returnTo, '') : '';
  const back = accountingParent || administrationReturn('companies', returnTo), here = accountingParent ? accountingLink(base + '/configuration', back) : administrationLink(base + '/configuration', back);
  const authUrl = signInUrl(), login = authUrl + (authUrl.includes('?') ? '&' : '?') + new URLSearchParams({ returnTo: here });
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null), [loading, setLoading] = useState(canRead), [loadError, setLoadError] = useState<CompanyFailure | null>(null), [revision, setRevision] = useState(0);
  const [review, setReview] = useState<Review | null>(null), [reason, setReason] = useState(''), [reasonError, setReasonError] = useState(''), [pending, setPending] = useState(false);
  const [failure, setFailure] = useState<CompanyFailure | null>(null), [frozen, setFrozen] = useState(false), [message, setMessage] = useState(''), [search, setSearch] = useState('');
  const busy = useRef(false), draftKey = useRef<string | null>(null), reasonInput = useRef<HTMLInputElement>(null);
  const guard = useAccessDraft(!!review, pending), format = useFormatters();
  useEffect(() => { if (reasonError && !pending && !frozen) reasonInput.current?.focus(); }, [reasonError, pending, frozen]);
  useEffect(() => {
    const controller = new AbortController(); setSnapshot(null); setLoadError(null); setLoading(canRead);
    if (canRead) Promise.all([
      companyCall<Profile>('identity', api, { signal: controller.signal }),
      companyCall<Catalogue>('identity', '/v1/company-features', { signal: controller.signal }),
      companyCall<Snapshot['setup']>('identity', api + '/setup-readiness', { signal: controller.signal }),
    ]).then(([profile, catalogue, setup]) => {
      if (controller.signal.aborted) return;
      if (profile.id !== companyId || setup.company_id !== companyId || !Array.isArray(catalogue.items) || !Array.isArray(setup.features) || !Number.isFinite(Date.parse(setup.company_updated_at))) throw { status: 502, message: 'The configuration response could not be verified. Reload configuration.' };
      if (profile.updated_at && profile.updated_at !== setup.company_updated_at) throw { status: 409, message: 'Configuration changed while loading. Reload and review the latest settings.' };
      const keys = new Set(catalogue.items.map(item => item.key));
      const configuredKeys = new Set(setup.features.map(row => row.feature_key));
      if (!keys.size || keys.size !== catalogue.items.length || configuredKeys.size !== setup.features.length || configuredKeys.size !== keys.size || catalogue.items.some(item => !/^[a-z][a-z0-9_]{0,39}$/.test(item.key)) || setup.features.some(row => !keys.has(row.feature_key) || !['ENABLED', 'DISABLED', 'INCONSISTENT'].includes(row.state))) throw { status: 502, message: 'The feature catalogue and configuration do not agree. Reload configuration.' };
      setSnapshot({ profile, catalogue, setup }); setLoading(false);
    }).catch(error => { if (!controller.signal.aborted) { setLoadError(companyFailure(error)); setLoading(false); } });
    return () => controller.abort();
  }, [api, companyId, canRead, revision]);
  function reload() { if (busy.current) return; setReview(null); setSnapshot(null); setFrozen(false); setFailure(null); setReasonError(''); setRevision(value => value + 1); }
  const label = (key: string) => snapshot?.catalogue.items.find(item => item.key === key)?.label ?? key;
  const enabled = snapshot?.setup.features.filter(row => row.state === 'ENABLED') ?? [];
  const dependents = (key: string) => enabled.filter(row => row.required_features.includes(key));
  const inconsistent = snapshot?.setup.features.some(row => row.state === 'INCONSISTENT');
  const writable = canUpdate && snapshot?.setup.company_status === 'active' && !inconsistent;
  const gstAvailable = snapshot?.profile.country_code === 'IN' && snapshot.profile.default_tax_system === 'gst_in';
  function restriction(row: Feature): string | undefined {
    if (pending || loading) return 'Wait for the current request to finish.';
    if (frozen) return 'Reload and review configuration before another change.';
    if (!writable) return 'Configuration is read-only.';
    if (row.locked_at) return row.lock_reason ? 'Permanently enabled: ' + row.lock_reason : 'Permanently enabled after first use.';
    if (row.state === 'DISABLED' && !row.tax_system_supported) return 'Unavailable for this company’s default tax system.';
    const requiredBy = row.state === 'ENABLED' ? dependents(row.feature_key) : [];
    if (requiredBy.length) return 'Required by ' + requiredBy.map(item => label(item.feature_key)).join(', ') + '. Disable those features first.';
  }
  function start(row: Feature) {
    if (!snapshot || restriction(row)) return;
    const key = row.feature_key + (row.state === 'DISABLED' ? ':enable' : ':disable');
    if (draftKey.current !== key) setReason('');
    draftKey.current = key; setFailure(null); setReasonError('');
    setReview({ feature: row, enabling: row.state === 'DISABLED', stamp: snapshot.setup.company_updated_at });
  }
  async function apply() {
    if (frozen) { reload(); return; }
    if (!review || !snapshot || busy.current || !writable) return;
    const clean = reason.trim();
    if (!clean || clean.length > 200 || /[\x00-\x1f\x7f]/.test(clean)) { setReasonError('Enter a reason using 1 to 200 printable characters.'); reasonInput.current?.focus(); return; }
    busy.current = true; setPending(true); setFailure(null); setReasonError('');
    try {
      const result = await companyCall<components['schemas']['FeatureView']>('identity', api + '/features/' + review.feature.feature_key + (review.enabling ? '/enable' : '/disable'), { method: 'POST', body: { reason: clean, expected_updated_at: review.stamp } });
      if (result.feature_key !== review.feature.feature_key || result.is_enabled !== review.enabling) throw { status: 502, message: 'The feature change response could not be verified.' };
      setMessage(label(review.feature.feature_key) + (review.enabling ? ' enabled.' : ' disabled.') + ' Configuration is refreshing. Check company readiness before using the feature.');
      setReview(null); setReason(''); draftKey.current = null; setSnapshot(null); setRevision(value => value + 1);
    } catch (error) {
      const problem = companyFailure(error); setFailure(problem);
      setFrozen(problem.status !== 422 || !problem.fields?.reason);
      if (problem.fields?.reason) { setReasonError(problem.fields.reason); reasonInput.current?.focus(); }
    } finally { busy.current = false; setPending(false); }
  }
  const columns: Column<Feature>[] = [
    { key: 'feature_key', header: 'Feature', type: 'custom', render: row => <div><strong>{label(row.feature_key)}</strong><p>{snapshot?.catalogue.items.find(item => item.key === row.feature_key)?.description}</p></div> },
    { key: 'state', header: 'Status', type: 'custom', render: row => <Badge tone={row.state === 'ENABLED' ? 'success' : row.state === 'INCONSISTENT' ? 'warn' : 'neutral'}>{row.state === 'ENABLED' ? 'Enabled' : row.state === 'DISABLED' ? 'Disabled' : 'Needs repair'}</Badge> },
    { key: 'required_features', header: 'Dependencies', type: 'custom', render: row => row.required_features.length ? row.required_features.map(label).join(', ') : 'None' },
    { key: 'locked_at', header: 'Protection', type: 'custom', render: row => row.locked_at ? <div>{row.lock_reason ?? 'Permanently enabled'}<p>Locked {format.dateTime(row.locked_at)}</p></div> : !row.tax_system_supported ? 'Unavailable for the default tax system' : row.state === 'ENABLED' && dependents(row.feature_key).length ? 'Required by ' + dependents(row.feature_key).map(item => label(item.feature_key)).join(', ') : snapshot?.catalogue.items.find(item => item.key === row.feature_key)?.locks ? 'Locks after first qualifying use' : 'Reversible' },
  ];
  const rows = snapshot?.setup.features.filter(row => (label(row.feature_key) + ' ' + row.feature_key).toLowerCase().includes(search.trim().toLowerCase())) ?? [];
  const uncertain = failure && failure.status >= 500;
  return <div className="janso-page">
    <PageNavigation back={{ href: back, label: accountingParent ? accountingBackLabel(back) : administrationBackLabel(back) }} breadcrumbs={[{ label: 'Administration', href: '/organisation' }, { label: 'Companies', href: administrationDirectoryReturn('companies', back) }, { label: snapshot?.profile.display_name ?? 'Company details', href: administrationLink(base, back) }, { label: 'Configuration' }]} onNavigate={guard.leave} />
    <PageHeader title="Company configuration" lede="Review company defaults and capabilities. Each change applies only to this company." actions={writable || gstAvailable ? <>
      {writable && <a className="janso-btn janso-btn--primary" href={administrationLink(base + '/edit', here)} onClick={guard.leave}>Edit company settings</a>}
      {gstAvailable && <a className="janso-btn janso-btn--ghost" href={base + '/gst-settings?' + new URLSearchParams({ returnTo: here })} onClick={guard.leave}>GST settings</a>}
    </> : undefined} />
    <nav className="janso-page-navigation" aria-label="Company configuration"><a className="janso-link" href={administrationLink(base, here)} onClick={guard.leave}>Company details</a>{companyPermission(session, 'period.read', companyId) && <a className="janso-link" href={administrationLink(base + '/years', here)} onClick={guard.leave}>Financial years</a>}{session.company.id === companyId && <a className="janso-link" href="/settings/readiness" onClick={guard.leave}>Company readiness</a>}{session.company.id === companyId && companyPermission(session, 'product_configuration.read', companyId) && <a className="janso-link" href={configLink(configRoot, here)} onClick={guard.leave}>Product configuration</a>}{canConfigureAccounting && <a className="janso-link" href={accountingLink("/accounting", here)} onClick={guard.leave}>Account, party and supplier configuration</a>}</nav>
    {!canRead ? <ErrorState status={403} detail="Company read access is required for this company." /> : loading ? <div role="status" aria-label="Loading company configuration"><Skeleton /></div> : loadError ? <ErrorState status={asErrorStatus(loadError.status)} detail={loadError.message} action={loadError.status === 401 ? <a className="janso-link" href={login}>Sign in again</a> : ![401, 403].includes(loadError.status) ? <Button onClick={reload}>Reload configuration</Button> : loadError.code === 'step_up_required' ? <a className="janso-link" href={stepUpUrl(companyId)}>Verify sign-in</a> : undefined} /> : snapshot && <>
      <Card className="janso-card--wrap-header"><CardHeader title={snapshot.profile.display_name ?? 'Company settings'} subtitle="Company details and defaults" badge={<Badge tone={snapshot.setup.company_status === 'active' ? 'success' : 'warn'}>{snapshot.setup.company_status}</Badge>} /><CardBody><div className="janso-flow">
        <div className="janso-grid janso-grid--even janso-grid--start">
          <section aria-label="Business identity"><h4 className="janso-meta">Business identity</h4><ReviewList items={[
            { label: 'Legal name', value: snapshot.profile.legal_name ?? 'Not readable' },
            { label: 'Trade name', value: snapshot.profile.trade_name === undefined ? 'Not readable' : snapshot.profile.trade_name || 'Not set' },
            { label: 'Company code', value: snapshot.profile.code ?? 'Not readable' },
            { label: 'Country / state', value: [snapshot.profile.country_code, snapshot.profile.state_code].filter(Boolean).join(' / ') || 'Not readable' },
          ]} /></section>
          <section aria-label="Regional and financial defaults"><h4 className="janso-meta">Regional and financial defaults</h4><ReviewList items={[
            { label: 'Base currency', value: snapshot.profile.base_currency ?? 'Not readable' },
            { label: 'Default tax system', value: snapshot.profile.default_tax_system ? taxSystemLabel(snapshot.profile.default_tax_system) : 'Not readable' },
            { label: 'Timezone', value: snapshot.profile.timezone ?? 'Not readable' },
            { label: 'Books begin', value: snapshot.profile.books_begin_date ? format.date(snapshot.profile.books_begin_date) : 'Not readable' },
          ]} /></section>
        </div>
        <p className="janso-meta">Use Edit company settings to update these defaults. Fields protected by posting history or your access policy remain read-only.</p>
        <Toolbar right={<Button variant="ghost" disabled={pending} onClick={reload}>Refresh configuration</Button>} />
      </div></CardBody></Card>
      {!canUpdate && <Notice>Read-only access. Company update permission in this company is required to change settings or features.</Notice>}
      {!gstAvailable && <CompanyTaxContext key={companyId + ':' + snapshot.profile.default_tax_system} company={companyId} taxSystem={snapshot.profile.default_tax_system} />}
      {snapshot.setup.company_status !== 'active' && <Notice tone="warning">This company is {snapshot.setup.company_status}. Configuration remains readable; changes require an active company.</Notice>}
      {inconsistent && <Notice tone="danger">Feature configuration needs repair. Ask an administrator to resolve the inconsistent state before making changes.</Notice>}
      <Notice>Enabling a feature does not confirm that books, registrations, product setup or transaction workflows are ready. Disabling preserves history. Features cannot be disabled while required by another feature, protected by prior use, or needed by pending work.</Notice>
      {message && <Notice tone="success">{message}</Notice>}
      {!review && failure && <Notice tone="danger">{uncertain ? 'The change result is unconfirmed. Reload and review the current configuration before another action. ' : ''}{failure.message} <Button variant="ghost" onClick={reload}>Reload and review</Button></Notice>}
      <Card><CardHeader title="Features" subtitle="Review availability, dependencies and protection before changing a feature." /><FilterBar><TableSearch label="Search features" value={search} onChange={setSearch} maxLength={100} minLength={0} placeholder="Feature name or key" /></FilterBar>
        <DataTable caption="Company features" columns={columns} rows={rows} rowId={row => row.feature_key} rowLabel={row => label(row.feature_key)} filtered={!!search} onClearFilters={() => setSearch('')} emptyTitle="No matching features" emptyBody="Clear the search to review all company capabilities." rowActions={row => writable ? [{ id: 'change', label: (row.state === 'DISABLED' ? 'Enable ' : 'Disable ') + label(row.feature_key), destructive: row.state === 'ENABLED', disabledReason: restriction(row) }] : []} onAction={(_action, row) => start(row)} />
      </Card>
    </>}
    <ConfirmDialog open={!!review} title={review ? (review.enabling ? 'Enable ' : 'Disable ') + label(review.feature.feature_key) + '?' : 'Review feature change'} confirmLabel={frozen ? 'Reload and review' : review?.enabling ? 'Enable feature' : 'Disable feature'} tone={review?.enabling ? 'default' : 'danger'} busy={pending} onCancel={() => { if (!busy.current) { setReview(null); if (!frozen) { setReason(''); draftKey.current = null; } } }} onConfirm={() => void apply()}>
      {review && <><ReviewList items={[{ label: 'Company', value: snapshot?.profile.display_name ?? companyId }, { label: 'Feature', value: label(review.feature.feature_key) }, { label: 'Action', value: review.enabling ? 'Enable' : 'Disable' }, ...(review.enabling ? [{ label: 'Also enables', value: review.feature.required_features.filter(key => !enabled.some(row => row.feature_key === key)).map(label).join(', ') || 'No additional dependencies' }] : [])]} /><p>{review.enabling ? 'Required features are enabled together. A feature may become permanent after its first qualifying use.' : 'Historical data is retained. Changes that conflict with dependent features, pending work or first-use protection are refused.'}</p></>}
      <TextField ref={reasonInput} label="Reason for change" required maxLength={200} value={reason} onChange={event => { setReason(event.target.value); setReasonError(''); }} error={reasonError} disabled={pending || frozen} />
      {failure && <Notice tone="danger">{uncertain ? 'The result is unconfirmed. Your review is retained; do not repeat this request before checking the latest configuration. ' : ''}{failure.message}{frozen && <p>Reload and review the current state before a new confirmation.</p>}</Notice>}
    </ConfirmDialog>{guard.confirmation}
  </div>;
}
