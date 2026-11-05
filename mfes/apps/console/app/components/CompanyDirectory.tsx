'use client';

import { useEffect, useState } from 'react';
import { Badge, Card, CardHeader, DataTable, FilterBar, PageHeader, PageNavigation,
  Pager, Select, TableSearch, asErrorStatus, parseListQuery, useListQuery, type Column, type PageMeta } from '@janso/ui';
import type { components } from '@janso/api-client/identity';
import { companyCall, companyFailure, type CompanyFailure } from '../lib/company-api';
import { companyPermission } from '../lib/company-permissions';
import type { Session } from '../session';
import { administrationLink, administrationReturn } from '../lib/administration-navigation';

type Row = components['schemas']['CompanyListItem'];
const columns = (back: string): readonly Column<Row>[] => [
  { key: 'code', header: 'Code', type: 'code' },
  { key: 'display_name', header: 'Company', type: 'custom', render: row =>
    <a className="janso-link" href={administrationLink('/companies/' + row.id, back)}>{row.display_name ?? row.code ?? 'Company'}</a> },
  { key: 'legal_name', header: 'Legal name' },
  { key: 'status', header: 'Status', type: 'custom', render: row => <Badge tone={row.status === 'active' ? 'success' : 'neutral'}>{row.status}</Badge> },
  { key: 'visibility', header: 'Visibility' },
  { key: 'base_currency', header: 'Currency' },
];

export function CompanyDirectory({ session, initialQuery = '' }: { session: Session; initialQuery?: string }) {
  const [rows, setRows] = useState<Row[]>([]), [meta, setMeta] = useState<PageMeta | null>(null);
  const [loading, setLoading] = useState(true), [failure, setFailure] = useState<CompanyFailure | null>(null);
  const [revision, setRevision] = useState(0);
  const initial = parseListQuery(new URL(administrationReturn('companies', '/companies/manage?' + initialQuery), 'https://console.invalid').searchParams, { filterKeys: ['status'] });
  const query = useListQuery({ initial, meta: loading || failure ? null : meta, onQueryChange: value => window.history.replaceState(null, '', '/companies/manage' + (value ? '?' + value : '')) });
  const back = '/companies/manage' + (query.queryString ? '?' + query.queryString : '');
  const status = String(query.filters.status ?? '');
  const canRead = companyPermission(session, 'company.read');
  const canCreate = companyPermission(session, 'company.create');
  useEffect(() => {
    if (!canRead) { setLoading(false); return; }
    const controller = new AbortController(); setLoading(true); setFailure(null); setRows([]);
    const params = new URLSearchParams({ limit: String(query.limit), include_unlisted: 'true' });
    if (query.q) params.set('q', query.q);
    if (query.cursor) params.set('cursor', query.cursor);
    if (status) params.set('status', status);
    companyCall<components['schemas']['CompanyPage']>('identity', '/v1/companies?' + params, { signal: controller.signal })
      .then(data => { if (!controller.signal.aborted) { setRows(data.items); setMeta({ ...data.page, limit: query.limit }); setLoading(false); } })
      .catch(error => { if (!controller.signal.aborted) { setFailure(companyFailure(error)); setMeta(null); setLoading(false); } });
    return () => controller.abort();
  }, [canRead, query.q, query.cursor, query.limit, status, revision]);
  return <div className="janso-page">
    <PageNavigation back={{ href: '/organisation', label: 'administration' }} breadcrumbs={[{ label: 'Business overview', href: '/' }, { label: 'Administration', href: '/organisation' }, { label: 'Companies' }]} />
    <PageHeader title="Manage companies" lede="View company details and manage the businesses your permissions cover."
      actions={canCreate && <a className="janso-btn janso-btn--primary" href={administrationLink('/companies/new', back)}>Create company</a>} />
    <Card><CardHeader title="Company directory" subtitle="Includes unlisted companies you are permitted to read. Opening a company and editing its details are separate actions." />
      {canRead && <FilterBar applied={[
        ...(query.q ? [{ id: 'q', label: 'Search', value: query.q }] : []),
        ...(status ? [{ id: 'status', label: 'Status', value: status }] : []),
      ]} onRemove={key => key === 'q' ? query.setSearch('') : query.setFilter(key, '')} onClearAll={query.clearFilters}>
        <TableSearch label="Search companies" value={query.q} onChange={query.setSearch} minLength={2} maxLength={100} placeholder="Code or company name" busy={loading} />
        <Select label="Status" value={status} onChange={value => query.setFilter('status', value)} options={[
          { value: '', label: 'All statuses' }, ...['active', 'suspended', 'closed'].map(value => ({ value, label: value })),
        ]} />
      </FilterBar>}
      <DataTable caption="Companies you can manage" columns={columns(back)} rows={rows} rowId={row => row.id} rowLabel={row => row.display_name ?? row.code ?? 'Company'}
        loading={loading} error={!canRead ? 403 : failure ? asErrorStatus(failure.status) : null}
        errorDetail={!canRead ? 'Company read access is needed to browse existing companies. You can create a company with your creation permission.' : failure?.message}
        onRetry={failure && failure.status !== 403 ? () => setRevision(value => value + 1) : undefined}
        filtered={query.filtered} emptyTitle="No companies found" emptyBody="Create a company or ask your administrator for company access."
        onClearFilters={query.clearFilters}
        rowActions={row => [{ id: 'view', label: 'View company', href: administrationLink('/companies/' + row.id, back) },
          { id: 'configure', label: 'Configure company', href: administrationLink('/companies/' + row.id + '/configuration', back) },
          ...(row.status === 'active' && companyPermission(session, 'company.update', row.id) ? [{ id: 'edit', label: 'Edit company', href: administrationLink('/companies/' + row.id + '/edit', back) }] : []),
          ...(companyPermission(session, 'period.read', row.id) ? [{ id: 'years', label: 'Manage years', href: administrationLink('/companies/' + row.id + '/years', back) }] : [])]} />
      {canRead && <Pager noun="company" nounPlural="companies" count={rows.length} from={query.page.from} limit={query.limit}
        hasPrevious={query.page.hasPrevious} hasNext={!failure && query.page.hasNext} onPrevious={query.previousPage} onNext={query.nextPage} onLimitChange={query.setLimit} busy={loading} />}
    </Card>
  </div>;
}
