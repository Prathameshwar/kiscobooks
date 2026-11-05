'use client';
import { ProductStructureSettings } from './ProductStructureSettings';
import { ProductPricingOptions } from './ProductPricingOptions';
import { ProductEntryOptions } from './ProductEntryOptions';
import type { components } from '@janso/api-client/catalog';
import { Badge, Card, CardBody, CardHeader, DataTable, Notice, PageHeader, Pager, type Column } from '@janso/ui';
import { configBack, configLink, configRoot, configListRecord, scopeLabels, useConfigList, useConfigRead, type ConfigPage, type ConfigScope } from '../lib/product-configuration';
import { ConfigurationFailure, ConfigurationLoading, ConfigurationNavigation } from './ProductConfigurationCommon';

type ScopeRow = components['schemas']['ScopeListItem'] & { owner_label?: string | null };
export const scopeTitle = (scope: ScopeRow) => scope.scope_kind === 'COMPANY' ? 'Company defaults' : scope.owner_label ?? (scope.scope_kind ? scopeLabels[scope.scope_kind] + ' configuration' : 'Protected scope');
export function ConfigurationOwner({ scope }: { company: string; scope: ScopeRow }) {
  return <span>{scope.scope_kind === 'COMPANY' ? 'Company defaults' : scope.owner_label ?? 'Owner unavailable or protected'}</span>;
}
export function ConfigurationPager<T>({ list, noun }: { list: ReturnType<typeof useConfigList<T>>; noun: string }) { return <Pager count={list.data?.items.length ?? 0} limit={list.limit} hasPrevious={list.hasPrevious} hasNext={!!list.data?.page.has_more} onPrevious={list.previous} onNext={list.next} onLimitChange={list.setLimit} busy={list.loading || !!list.failure} noun={noun} />; }
export function ProductConfigurationDirectory({ company, canManage, canPublish = false, canAdopt = false, initialQuery = '' }: { company: string; canManage: boolean; canPublish?: boolean; canAdopt?: boolean; initialQuery?: string }) {
  const initial = new URL(configBack(configRoot + (initialQuery ? '?' + initialQuery : '')), 'https://console.invalid');
  const back = configBack(initial.toString().replace(initial.origin, '')), api = `/v1/companies/${company}`;
  const scopes = useConfigRead<ConfigPage<ScopeRow>>(api + '/product-configuration-scopes?scope_kind=COMPANY&limit=2', value => {
    if (!Array.isArray(value.items) || value.items.length > 1 || value.page?.has_more) throw { status: 502, message: 'The company configuration could not be verified.' };
    for (const row of value.items) {
      configListRecord(row);
      if (row.scope_kind !== 'COMPANY' || row.owner_id !== company) throw { status: 502, message: 'The company configuration is unavailable or protected.' };
    }
  });
  const owner = scopes.data?.items[0], base = owner ? api + '/product-configuration-scopes/' + owner.id : undefined;
  const drafts = useConfigRead<ConfigPage<components['schemas']['DraftListItem']>>(base ? base + '/drafts?status=DRAFT&limit=1&sort=-id' : undefined, value => {
    if (!Array.isArray(value.items)) throw { status: 502, message: 'The saved company draft could not be verified.' };
    for (const row of value.items) {
      configListRecord(row);
      if (row.scope_id !== owner?.id || row.status !== 'DRAFT') throw { status: 502, message: 'The saved company draft is unavailable or protected.' };
    }
  });
  const published = useConfigRead<ConfigPage<components['schemas']['RevisionListItem']>>(base ? base + '/revisions?limit=1&sort=-id' : undefined, value => {
    if (!Array.isArray(value.items)) throw { status: 502, message: 'The published company configuration could not be verified.' };
    for (const row of value.items) {
      configListRecord(row);
      if (row.scope_id !== owner?.id) throw { status: 502, message: 'The published configuration does not belong to this company.' };
    }
  });
  const busy = scopes.loading || !!owner && (drafts.loading || published.loading);
  const failed = scopes.failure || drafts.failure || published.failure;
  const pending = drafts.data?.items[0], latest = published.data?.items[0];
  const ready = !busy && !failed && !!scopes.data && (!owner || !!drafts.data && !!published.data);
  const edit = pending ? configRoot + '/drafts/' + pending.id + '/edit' : configRoot + '/new';
  return <div className="janso-page">
    <ConfigurationNavigation title="Product configuration" back={initial.searchParams.get('returnTo') ?? '/settings'} />
    <PageHeader title="Product configuration" lede="Manage product information, pricing options and defaults for this company." />
    <nav className="janso-page-navigation" aria-label="Product configuration"><a className="janso-link" href={configLink(configRoot + '/effective', back)}>Inspect effective settings</a>{canAdopt && <a className="janso-link" href={configLink(configRoot + '/adopt', back)}>Review product adoption</a>}<a className="janso-link" href="/products/custom-fields">Product fields</a></nav>
    {!canManage && <Notice>Read-only access. Company-scoped product configuration manage permission is required to create or edit drafts.</Notice>}
    <ProductStructureSettings company={company} canManage={canManage} />
    <Notice>New companies receive a published starter configuration automatically: Simple products, one selling-price level, optional selling and purchase prices, and additional pricing options disabled. Enable more options when needed by editing and publishing a configuration draft.</Notice>
    <Card><CardHeader title="Company product defaults" /><CardBody>
      <ConfigurationFailure failure={scopes.failure} retry={scopes.refresh} />
      <ConfigurationFailure failure={drafts.failure} retry={drafts.refresh} />
      <ConfigurationFailure failure={published.failure} retry={published.refresh} />
      {busy ? <ConfigurationLoading /> : ready && <div className="janso-flow">
        <p>{pending ? 'A company configuration draft is ready to edit or review.' : latest ? 'The published company configuration is available. Create a draft to change its settings.' : 'No company configuration has been published. Create your first configuration to set product defaults.'}</p>
        {latest && <a className="janso-link" href={configLink(configRoot + '/revisions/' + latest.id, back)}>View published revision {latest.revision}</a>}
        <div className="janso-form-actions">
          {canManage && <a className="janso-btn janso-btn--primary" href={configLink(edit, back)}>{pending || latest ? 'Edit company configuration' : 'Create company configuration'}</a>}
          {pending && <a className="janso-btn janso-btn--secondary" href={configLink(configRoot + '/drafts/' + pending.id, back)}>{canPublish ? 'Review and publish' : 'Review draft'}</a>}
          {owner && <a className="janso-link" href={configLink(configRoot + '/scopes/' + owner.id, back)}>Publication history</a>}
        </div>
      </div>}
    </CardBody></Card>
    {ready && latest && <><ProductEntryOptions company={company} revisionId={latest.id} /><ProductPricingOptions company={company} revisionId={latest.id} /></>}
    <Notice>Publishing changes future defaults. Existing product settings and price history remain unchanged until a supported, explicit adoption.</Notice>
  </div>;
}
export function ProductConfigurationScope({ company, id, canManage, returnTo }: { company: string; id: string; canManage: boolean; returnTo?: string }) {
  const base = `/v1/companies/${company}/product-configuration-scopes/${id}`, back = configBack(returnTo), scopePath = configRoot + '/scopes/' + id, here = configLink(scopePath, back);
  const scope = useConfigRead<ConfigScope>(base, value => { if (value.id !== id || value.company_id !== company) throw { status: 502, message: 'This configuration scope could not be verified.' }; });
  const drafts = useConfigList<components['schemas']['DraftListItem']>(base + '/drafts'), revisions = useConfigList<components['schemas']['RevisionListItem']>(base + '/revisions');
  const draftColumns: Column<components['schemas']['DraftListItem']>[] = [{ key: 'effective_from', header: 'Effective from', type: 'date' }, { key: 'status', header: 'Status', type: 'custom', render: row => <Badge tone={row.status === 'PUBLISHED' ? 'success' : 'neutral'}>{row.status === 'PUBLISHED' ? 'Published' : row.status === 'DRAFT' ? 'Draft' : 'Not readable'}</Badge> }, { key: 'row_version', header: 'Version', type: 'text' }];
  const revisionColumns: Column<components['schemas']['RevisionListItem']>[] = [{ key: 'revision', header: 'Revision', type: 'text' }, { key: 'effective_from', header: 'Effective from', type: 'date' }, { key: 'published_at', header: 'Published', type: 'datetime' }];
  return <div className="janso-page"><ConfigurationNavigation title="Configuration scope" back={back} /><PageHeader title={scope.data ? scopeTitle(scope.data) : 'Configuration scope'} lede="Review company drafts and immutable publication history." actions={canManage && scope.data?.scope_kind === 'COMPANY' && scope.data.owner_id === company ? <a className="janso-btn janso-btn--primary" href={configLink(scopePath + '/drafts/new', here)}>New draft</a> : undefined} />
    <ConfigurationFailure failure={scope.failure} retry={scope.refresh} />{scope.loading ? <ConfigurationLoading /> : scope.data && <Notice><ConfigurationOwner company={company} scope={scope.data} /> · Latest published revision: {scope.data.latest_revision ?? 'Not readable'}</Notice>}
    {!scope.loading && scope.data && <>
      <Card><CardHeader title="Drafts" /><ConfigurationFailure failure={drafts.failure} retry={drafts.first} />{drafts.loading ? <ConfigurationLoading /> : !drafts.failure && <DataTable caption="Configuration drafts" columns={draftColumns} rows={drafts.data?.items ?? []} rowId={row => row.id} rowLabel={row => 'Draft effective ' + (row.effective_from ?? 'not readable')} emptyTitle="No drafts yet" rowActions={row => [{ id: 'view', label: 'View draft', href: configLink(configRoot + '/drafts/' + row.id, here) }, ...(canManage && scope.data?.scope_kind === 'COMPANY' && scope.data.owner_id === company && row.status === 'DRAFT' ? [{ id: 'edit', label: 'Edit draft', href: configLink(configRoot + '/drafts/' + row.id + '/edit', here) }] : [])]} />}<ConfigurationPager list={drafts} noun="draft" /></Card>
      <Card><CardHeader title="Published revisions" subtitle="Published settings are immutable. Create a draft for a later effective date." /><ConfigurationFailure failure={revisions.failure} retry={revisions.first} />{revisions.loading ? <ConfigurationLoading /> : !revisions.failure && <DataTable caption="Published configuration revisions" columns={revisionColumns} rows={revisions.data?.items ?? []} rowId={row => row.id} rowLabel={row => 'Revision ' + row.revision} emptyTitle="No published revisions" rowActions={row => [{ id: 'view', label: 'View revision', href: configLink(configRoot + '/revisions/' + row.id, here) }]} />}<ConfigurationPager list={revisions} noun="revision" /></Card>
    </>}
  </div>;
}
