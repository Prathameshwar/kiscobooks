'use client';
import { useState } from 'react';
import { ActionCard, FilterBar, Notice, PageHeader, PageNavigation, ReceiptIcon, TableSearch } from '@janso/ui';
import { familyHref, familyMatches, type OperateArea } from '../lib/operate-navigation';

export function OperateLanding({ area }: { area: OperateArea }) {
  const [search, setSearch] = useState('');
  const families = area.families.filter(family => familyMatches(family, search));
  return <div className="janso-page">
    <PageNavigation back={{ href: '/', label: 'business overview' }} breadcrumbs={[{ label: 'Business overview', href: '/' }, { label: area.title }]} />
    <PageHeader title={area.title} lede={area.description + ' Choose a workflow to find its vouchers and print settings.'} />
    <FilterBar><TableSearch label={'Search ' + area.title.toLowerCase() + ' workflows'} placeholder="Search workflows and vouchers" value={search} onChange={setSearch} minLength={0} maxLength={100} /></FilterBar>
    {!families.length && <Notice>No workflows match your search. Clear the search to see all workflows.</Notice>}
    <div className="janso-action-card-grid">
      {families.map(family => <ActionCard key={family.key} title={family.title} description={family.description} icon={<ReceiptIcon />} actionLabel="Open workflow" href={familyHref(area, family)} />)}
    </div>
    <a className="janso-link" href="/vouchers">Browse all voucher drafts</a>
  </div>;
}
