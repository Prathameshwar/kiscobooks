'use client';
import { useEffect, useState } from 'react';
import { Badge, Button, Card, CardBody, CardHeader, ConfirmDialog, Notice, PageHeader, ReviewList, useFormatters } from '@janso/ui';
import { masterRequest } from '../lib/catalog-master-api';
import { companyToday, configBack, configLabel, configLink, configMetadata, configRecord, configRoot, useConfigCommand, useConfigDestination, useConfigRead, type ConfigDraft, type ConfigEffective, type ConfigMetadata, type ConfigPreview, type ConfigRevision, type ConfigScope, type ConfigValues } from '../lib/product-configuration';
import { requestFailure, type RequestFailure } from '../lib/service-call';
import { useAccessDraft } from './AccessCommon';
import { ConfigurationEffectiveValues, ConfigurationFailure, ConfigurationGroupedValues, ConfigurationLoading, ConfigurationNavigation, ConfigurationSectionNavigation, ConfigurationValues } from './ProductConfigurationCommon';

function ComparisonChanges({ comparison, metadata }: { comparison: NonNullable<ConfigPreview['comparisons']>[number]; metadata: ConfigMetadata | null }) {
  function display(value: unknown, path: string) {
    if (value === undefined) return 'Unavailable'; if (value === null) return 'Inherit / not set'; if (typeof value === 'boolean') return value ? 'Yes' : 'No';
    const [section, key] = path.split('.'), field = metadata?.[section as keyof ConfigMetadata]?.find(row => row.key === key);
    return field?.control?.choices.find(choice => choice.value === value)?.label ?? (typeof value === 'object' ? JSON.stringify(value) : String(value));
  }
  function lookup(value: ConfigEffective | null, path: string): unknown { return path.split('.').reduce<unknown>((current, key) => current && typeof current === 'object' ? (current as ConfigValues)[key] : undefined, value); }
  return <ReviewList items={comparison.changed_fields.map(path => { const [section, key] = path.split('.'), field = metadata?.[section as keyof ConfigMetadata]?.find(row => row.key === key); return { label: field ? configLabel(field) : path.replaceAll('_', ' '), value: <div><p><strong>Before:</strong> {display(lookup(comparison.before as ConfigEffective | null, path), path)}</p><p><strong>After:</strong> {display(lookup(comparison.after as ConfigEffective, path), path)}</p></div> }; })} />;
}

export function ProductConfigurationDetail({ company, id, revision = false, canManage, canPublish, timezone, returnTo }: { company: string; id: string; revision?: boolean; canManage: boolean; canPublish: boolean; timezone: string; returnTo?: string }) {
  const format = useFormatters();
  const api = `/v1/companies/${company}`, back = configBack(returnTo), detailPath = configRoot + (revision ? '/revisions/' : '/drafts/') + id, here = configLink(detailPath, back);
  const read = useConfigRead<ConfigDraft | ConfigRevision>(api + (revision ? '/product-configuration-revisions/' : '/product-configurations/') + id, value => { configRecord(value, company, id); });
  const [metadata, setMetadata] = useState<ConfigMetadata | null>(null), [metadataError, setMetadataError] = useState<RequestFailure | null>(null), [preview, setPreview] = useState<ConfigPreview | null>(null), [previewError, setPreviewError] = useState<RequestFailure | null>(null), [reviewing, setReviewing] = useState(false), [previewBusy, setPreviewBusy] = useState(false);
  const command = useConfigCommand(), navigation = useConfigDestination(command.pending), guard = useAccessDraft(!navigation.destination && (reviewing || command.uncertain), command.pending || previewBusy);
  const owner = useConfigRead<ConfigScope>(read.data?.scope_id ? api + '/product-configuration-scopes/' + read.data.scope_id : undefined, value => { configRecord(value, company, read.data?.scope_id ?? undefined); });
  const retired = !!owner.data?.scope_kind && owner.data.scope_kind !== 'COMPANY';
  const draft = !revision ? read.data as ConfigDraft | null : null, writable = draft?.status === 'DRAFT' && owner.data?.scope_kind === 'COMPANY' && owner.data.owner_id === company;
  const published = revision || draft?.status === 'PUBLISHED', statusLabel = published ? 'Published' : draft?.status === 'DRAFT' ? 'Draft' : 'Not readable';
  useEffect(() => { const controller = new AbortController(); setMetadata(null); setMetadataError(null); configMetadata(company, 'update', controller.signal).then(value => { if (!controller.signal.aborted) setMetadata(value); }).catch(error => { if (!controller.signal.aborted) setMetadataError(requestFailure(error)); }); return () => controller.abort(); }, [company]);
  async function review() {
    if (!draft || !writable || !canPublish || previewBusy || command.pending) return;
    if (command.uncertain) { setReviewing(true); return; }
    setPreviewBusy(true); setPreviewError(null); setPreview(null); command.clear();
    try {
      const result = await masterRequest<ConfigPreview>({ path: api + '/product-configurations/' + id + '/preview' });
      if (result.draft_id !== id || result.draft_version !== draft.row_version || result.effective_from !== draft.effective_from || result.purpose !== 'FUTURE_PRODUCT_DEFAULTS' || result.existing_product_adoption !== 'unchanged' || !result.validated || !Array.isArray(result.comparisons) || !result.comparisons.length || result.comparisons.some(row => row.after.company_id !== company)) throw { status: 409, message: 'The draft review could not be verified. Reload the draft and review again.' };
      setPreview(result); setReviewing(true);
    } catch (error) { setPreviewError(requestFailure(error)); } finally { setPreviewBusy(false); }
  }
  async function publish() {
    if (!preview || !draft || !canPublish || !writable || command.pending || command.blocked && !command.uncertain) return;
    const result = await command.execute<ConfigRevision>({ path: api + '/product-configurations/' + id + '/publish', method: 'POST', body: { expected_version: preview.draft_version, expected_generation: preview.policy_generation, expected_source_version: preview.source_version } }, value => { configRecord(value, company); if (value.source_draft_id !== id || value.scope_id !== draft.scope_id || value.effective_from !== preview.effective_from || !Number.isSafeInteger(value.revision)) throw { status: 502, message: 'The publication result could not be verified.' }; });
    if (result) { setReviewing(false); navigation.setDestination(configLink(configRoot + '/revisions/' + result.id, back)); }
  }
  function reload() { if (command.pending) return; command.clear(); setReviewing(false); setPreview(null); setPreviewError(null); read.refresh(); }
  const today = companyToday(timezone), past = !!draft?.effective_from && draft.effective_from < today;
  return <div className="janso-page"><ConfigurationNavigation title={revision ? 'Published configuration' : 'Configuration draft'} back={back} onLeave={guard.leave} /><PageHeader title={revision ? 'Published configuration revision' : 'Configuration draft'} lede={revision ? 'Published settings are immutable and retain their effective date and change reason.' : 'Inspect saved settings and review the complete effect before publication.'} actions={writable && canManage ? <a className="janso-btn janso-btn--primary" href={configLink(detailPath + '/edit', here)} onClick={guard.leave}>Edit draft</a> : undefined} />
    <ConfigurationFailure failure={read.failure} retry={read.refresh} />{read.loading ? <ConfigurationLoading /> : read.data && <>
      <ConfigurationFailure failure={owner.failure} retry={owner.refresh} />
      {retired && <Notice>Retired configuration. These settings are available as read-only history.</Notice>}
      <Card><CardHeader title="Configuration details" /><CardBody><ReviewList items={[{ label: 'Status', value: <Badge tone={published ? 'success' : 'neutral'}>{statusLabel}</Badge> }, { label: 'Effective from', value: read.data.effective_from ? format.date(read.data.effective_from) : 'Not readable' }, { label: revision ? 'Revision' : 'Draft version', value: String(revision ? (read.data as ConfigRevision).revision ?? 'Not readable' : draft?.row_version ?? 'Not readable') }, { label: 'Reason for change', value: read.data.change_reason ?? 'Not readable' }]} />{read.data.scope_id && <a className="janso-link" href={configLink(configRoot + '/scopes/' + read.data.scope_id, here)} onClick={guard.leave}>Publication history</a>}</CardBody></Card>
      <ConfigurationFailure failure={metadataError} />{!metadata && !metadataError ? <ConfigurationLoading /> : metadata && <>
        <ConfigurationSectionNavigation details={false} conversion={metadata.options.some(field => field.visible && field.display_group === 'unit_conversion')} numeric={read.data.numeric_defaults.length > 0} />
        {(['options', 'profiles', 'pricing'] as const).map(section => <ConfigurationGroupedValues anchor={section} returnTo={here} onLeave={guard.leave} key={section} company={company} title={{ options: 'Entry options', profiles: 'Profile defaults', pricing: 'Pricing requirements' }[section]} fields={metadata[section]} values={read.data![section] as ConfigValues} />)}
        {!!read.data.numeric_defaults.length && <section id="configuration-numeric" tabIndex={-1} className="janso-flow janso-config-section">{read.data.numeric_defaults.map((row, index) => <ConfigurationValues returnTo={here} onLeave={guard.leave} key={row.id} company={company} title={'Numeric defaults ' + (index + 1)} fields={metadata.numeric_defaults} values={row as ConfigValues} />)}</section>}
      </>}
      <Notice>Publication affects future product defaults from its effective date. Existing product pins and price history remain unchanged. Company capabilities and native hard restrictions still apply.</Notice>
      {!revision && !canPublish && <Notice>Read-only publication access. A company-scoped product configuration publish grant is required.</Notice>}
      {past && <Notice tone="warning">The effective date is in the past in this company. Edit the draft to use today or a later permitted date before publication.</Notice>}
      <ConfigurationFailure failure={previewError} retry={reload} />
      {!reviewing && command.uncertain && <Notice tone="warning">Publication is unconfirmed. Reopen the retained review and retry the same request to recover its result.</Notice>}
      {writable && canPublish && <Button loading={previewBusy} disabled={past || command.pending} onClick={() => void review()}>{command.uncertain ? 'Recover publication' : 'Review publication'}</Button>}
    </>}
    <ConfirmDialog open={reviewing} size="lg" title="Publish these product defaults?" confirmLabel={command.uncertain ? 'Retry same publication' : command.blocked ? 'Reload and review' : 'Publish revision'} busy={command.pending} onCancel={() => { if (!command.pending) setReviewing(false); }} onConfirm={() => { if (command.blocked && !command.uncertain) reload(); else void publish(); }}>
      {preview && <><ReviewList items={[{ label: 'Effective from', value: format.date(preview.effective_from) }, { label: 'Reason', value: draft?.change_reason ?? 'Not readable' }, { label: 'Existing products', value: 'Unchanged' }]} />{preview.comparisons?.map(comparison => <div key={comparison.kind} className="janso-flow"><h3>{comparison.kind === 'GOODS' ? 'Goods' : 'Services'}</h3>{comparison.changed_fields.length ? <ComparisonChanges comparison={comparison} metadata={metadata} /> : <p>No effective changes.</p>}{comparison.before_conflicts?.map(reason => <Notice key={reason} tone="warning">Previous configuration: {reason}</Notice>)}<ConfigurationEffectiveValues value={{ ...comparison.after, settings: comparison.after.settings ?? [] }} metadata={metadata ?? undefined} returnTo={here} onLeave={guard.leave} /></div>)}</>}
      <ConfigurationFailure failure={command.failure} write />{command.uncertain && <Notice tone="warning">This exact publication request is retained. Retry it to recover its result before leaving this review.</Notice>}
    </ConfirmDialog>{guard.confirmation}</div>;
}
