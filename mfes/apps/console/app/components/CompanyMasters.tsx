'use client';

import { useState } from 'react';
import { ActionCard, BookIcon, BoxIcon, Button, ErrorState, FilterBar, Notice, PageHeader, PageNavigation, SectionHeader, TableSearch, TaxIcon } from '@janso/ui';
import type { Session } from '../session';
import type { CompanyContext } from '../lib/company-context';
import { companyMastersFor } from '../lib/company-masters';
import { companyPermission } from '../lib/company-permissions';
import { NoCompany } from './NoCompany';
import { useServiceRead } from '../lib/service-resource';
import { masterRequest } from '../lib/catalog-master-api';
import { taxRequest } from '../lib/tax-api';
import type { TaxContext } from '../lib/tax-masters';
import { useCompanyActionFeatures } from '../lib/company-action-features';
import { useProductMode } from './ProductModeProvider';

const trackingFeatures = ['inventory', 'batch_tracking', 'serial_tracking'];

export function CompanyMasters({ session, context }: { session: Session; context: CompanyContext }) {
  const [search, setSearch] = useState('');
  const mode = useProductMode();
  const advanced =
    mode?.data &&
    mode.company === session.company.id &&
    mode.data.company_id === session.company.id
      ? mode.data.product_family_sku_enabled
      : null;
  const available = companyMastersFor(session, advanced);
  const hasTracking = available.some(group => group.key === 'stock-tracking');
  const tracking = useCompanyActionFeatures(session.company.id ?? '', hasTracking && companyPermission(session, 'company.read'), trackingFeatures);
  const trackingRestriction = !companyPermission(session, 'company.read') ? 'Company configuration read access is required' : tracking.features.restriction;
  const trackingVisible = (href: string) => !tracking.features.enabled || tracking.features.enabled.includes('inventory') && (href === '/inventory/stock' || tracking.features.enabled.includes(href.endsWith('/batches') ? 'batch_tracking' : 'serial_tracking'));
  const tax = useServiceRead<TaxContext>(available.some(group => group.key === 'tax') ? `/v1/companies/${session.company.id}/tax-administration` : undefined, taxRequest, value => {
    if (value.company_id !== session.company.id || !/^[A-Z]{2}$/.test(value.country_code) || typeof value.default_tax_system !== 'string' || !value.default_tax_system) throw { status: 502, message: 'Tax configuration could not be verified for this company.' };
  }, 'tax configuration');
  const bom = useServiceRead<{ company_id: string; enabled: boolean; operational_ready: false }>(available.some(group => group.items.some(item => item.href === '/masters/boms')) ? `/v1/companies/${session.company.id}/boms/authoring-context` : undefined, masterRequest, value => {
    if (value.company_id !== session.company.id || typeof value.enabled !== 'boolean' || value.operational_ready !== false) throw { status: 502, message: 'BOM configuration could not be verified for this company.' };
  }, 'BOM configuration');
  const stack = useServiceRead<{ company_id: string; enabled: boolean; operational_ready: false }>(available.some(group => group.items.some(item => item.href === '/masters/promotion-stack-policies')) ? `/v1/companies/${session.company.id}/promotion-stack-policies/authoring-context` : undefined, masterRequest, value => {
    if (value.company_id !== session.company.id || typeof value.enabled !== 'boolean' || value.operational_ready !== false) throw { status: 502, message: 'Promotion configuration could not be verified for this company.' };
  }, 'promotion configuration');
  const stackAvailable = !stack.loading && !stack.failure && stack.data?.company_id === session.company.id && stack.data?.enabled === true;
  const bomRestriction = bom.failure ? 'Configuration unavailable' : !bom.data ? 'Checking BOM configuration' : undefined;
  const taxRestriction = tax.failure ? 'Configuration unavailable' : !tax.data || tax.data.company_id !== session.company.id ? 'Checking configuration' : undefined;
  const query = search.trim().toLowerCase();
  const groups = available.filter(group => group.key !== 'tax' || !tax.data || tax.data.company_id !== session.company.id || tax.data.country_code === 'IN' && tax.data.default_tax_system === 'gst_in')
    .map(group => ({ ...group, items: group.items.filter(item => (group.key !== 'stock-tracking' || trackingVisible(item.href)) && (item.href !== '/masters/promotion-stack-policies' || stackAvailable) && (item.href !== '/masters/boms' || !bom.data || bom.data.enabled) && (item.label + ' ' + item.description + ' ' + group.label).toLowerCase().includes(query)) })).filter(group => group.items.length);
  return <div className="janso-page">
    <PageNavigation back={{ href: '/', label: 'business overview' }} breadcrumbs={[{ label: 'Business overview', href: '/' }, { label: 'Masters' }]} />
    <PageHeader title="Masters" lede="Product, warehouse, pricing, accounting and tax masters for the company currently open." />
    {!session.company.id ? <NoCompany action="manage masters for" context={context} canCreate={companyPermission(session, 'company.create')} />
      : !available.length ? <ErrorState status={403} detail="No master read permissions are available for this company." />
      : <>
        <Notice>Masters for {session.company.name}. Available actions depend on your access and the company’s configuration.</Notice>
        <FilterBar><TableSearch label="Search masters" placeholder="Find a master by name or purpose" value={search} onChange={setSearch} minLength={0} maxLength={100} /></FilterBar>
        {!groups.length ? <Notice>{query ? 'No masters match your search. Clear the search to see the available cards.' : 'No masters are applicable for this company.'}</Notice> : groups.map(group => <section key={group.key} className="janso-flow" aria-label={group.label}>
          <SectionHeader title={group.label} description={group.description} />
          {group.key === 'tax' && tax.failure ? <Notice tone="warning">Tax configuration is unavailable. Other masters remain available. <Button type="button" variant="ghost" onClick={tax.refresh}>Retry tax configuration</Button></Notice> : null}
          {group.key === 'manufacturing' && bom.failure ? <Notice tone="warning">BOM configuration is unavailable. Other manufacturing definitions remain available. <Button type="button" variant="ghost" onClick={bom.refresh}>Retry BOM configuration</Button></Notice> : null}
          <div className="janso-action-card-grid janso-action-card-grid--compact">{group.items.map(item => <ActionCard key={item.href} title={item.label} description={item.description}
            icon={group.kind === 'accounting' ? <BookIcon /> : group.kind === 'tax' ? <TaxIcon /> : <BoxIcon />}
            actionLabel={item.href === '/accounting/account-heads' ? 'View account heads' : 'Open ' + item.label.toLowerCase()}
            {...(group.key === 'stock-tracking' && trackingRestriction ? { disabledReason: trackingRestriction } : item.href === '/masters/boms' && bomRestriction ? { disabledReason: bomRestriction } : group.key === 'tax' && taxRestriction ? { disabledReason: taxRestriction } : { href: item.href + '?returnTo=%2Fmasters' })} />)}</div>
        </section>)}
      </>}
  </div>;
}
