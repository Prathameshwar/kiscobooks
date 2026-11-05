'use client';
import { useEffect, useRef, useState } from 'react';
import {
  Card,
  CardBody,
  CardHeader,
  DataTable,
  FilterBar,
  IconButton,
  Notice,
  PageHeader,
  Pager,
  RefreshIcon,
  SearchSelect,
  Select,
  TableSearch,
  asErrorStatus,
  parseListQuery,
  useListQuery,
  type Column,
  type SearchSelectLoader,
} from '@janso/ui';
import { platformCall, PlatformError } from '../../lib/platform-api';
import {
  administratorLink,
  administratorPath,
  administratorRoot,
  platformAccessReader,
  type AdministratorItem,
  type AdministratorPage,
  type AdministratorTenant,
  type TenantPage,
} from '../../lib/platform-access';
import { useServiceRead } from '../../lib/service-resource';
import { goTo } from '../../lib/navigate';
import { PlatformAccessNavigation } from './PlatformAccessOverview';

const columns: readonly Column<AdministratorItem>[] = [
  {
    key: 'display_name',
    header: 'Administrator',
    sortable: true,
    locked: true,
  },
  { key: 'email', header: 'Email', sortable: true },
  {
    key: 'status',
    header: 'Account status',
    type: 'status',
    tone: (value) =>
      value === 'active' ? 'success' : value === 'invited' ? 'warn' : 'neutral',
  },
  { key: 'updated_at', header: 'Updated', type: 'datetime', sortable: true },
];
const loadTenants: SearchSelectLoader = async ({ q, cursor, signal }) => {
  const query = new URLSearchParams({ limit: '50' });
  if (q.trim().length >= 2) query.set('q', q.trim());
  if (cursor) query.set('cursor', cursor);
  const value = await platformCall<TenantPage>(
    '/v1/platform/access/tenants?' + query,
    'GET',
    undefined,
    undefined,
    signal,
  );
  return {
    items: value.items.map((row) => ({
      id: row.id,
      label: row.name,
      meta: row.status,
    })),
    nextCursor: value.page.next_cursor,
  };
};
export function PlatformAdministratorDirectory({
  tenantId,
  canManage,
  canReadTenant = false,
}: {
  tenantId: string;
  canManage: boolean;
  canReadTenant?: boolean;
}) {
  const [selected, setSelected] = useState(tenantId);
  const tenant = useServiceRead<AdministratorTenant>(
    selected ? '/v1/platform/access/tenants/' + selected : undefined,
    platformAccessReader,
    (value) => {
      if (value.id !== selected)
        throw {
          status: 502,
          message: 'The selected tenant could not be verified.',
        };
    },
    'platform access service',
  );
  const selectedTenant = tenant.data?.id === selected ? tenant.data : null;
  const [pageMeta, setPageMeta] = useState<AdministratorPage['page'] | null>(
    null,
  );
  const query = useListQuery({
    initial: { sort: [{ key: 'display_name', direction: 'asc' }] },
    meta: pageMeta ? { ...pageMeta, limit: 50 } : null,
  });
  const adopted = useRef(false);
  useEffect(() => {
    if (!adopted.current) {
      adopted.current = true;
      const parsed = parseListQuery(
        new URLSearchParams(window.location.search),
        { filterKeys: ['status'] },
      );
      query.adopt({
        ...parsed,
        sort: parsed.sort.length
          ? parsed.sort
          : [{ key: 'display_name', direction: 'asc' }],
      });
    }
  }, [query.adopt]);
  const params = query.params.toString();
  const list = useServiceRead<AdministratorPage>(
    selectedTenant && !tenant.failure
      ? administratorPath(selected) + '?' + params
      : undefined,
    platformAccessReader,
    (value) => {
      if (!Array.isArray(value.items) || !value.page)
        throw {
          status: 502,
          message: 'The administrator directory could not be verified.',
        };
    },
    'platform access service',
  );
  useEffect(() => {
    setPageMeta(list.loading || !list.data ? null : list.data.page);
  }, [list.data, list.loading]);
  useEffect(() => {
    const url = new URLSearchParams(params);
    if (selected) url.set('tenant', selected);
    window.history.replaceState(
      null,
      '',
      administratorRoot + (url.size ? '?' + url : ''),
    );
  }, [selected, params]);
  const back =
    administratorRoot +
    '?' +
    new URLSearchParams({
      ...Object.fromEntries(query.params),
      tenant: selected,
    });
  const canWrite =
    canManage && !!selectedTenant && selectedTenant.status !== 'closed';
  const create = canWrite ? (
    <a
      className="janso-btn janso-btn--primary"
      href={administratorLink(administratorRoot + '/new', selected, back)}
    >
      Invite administrator
    </a>
  ) : undefined;
  return (
    <div className="janso-page">
      <PlatformAccessNavigation title="Tenant administrators" />
      <PageHeader
        title="Tenant administrators"
        lede="Choose a customer tenant, then manage its administrator accounts and tenant-wide access."
        actions={create}
      />
      <Card>
        <CardHeader
          title="Customer tenant"
          subtitle="Tenant selection is explicit. The platform operating workspace is excluded."
        />
        <CardBody>
          <div className="janso-flow">
            <SearchSelect
              label="Tenant"
              value={selected}
              selected={
                selectedTenant
                  ? {
                      id: selectedTenant.id,
                      label: selectedTenant.name,
                      meta: selectedTenant.status,
                    }
                  : null
              }
              loadOptions={loadTenants}
              minQueryLength={0}
              scopeKey="platform-administrator-tenants"
              onChange={(id) => {
                setSelected(id ?? '');
                query.restart();
              }}
              placeholder="Choose a tenant"
            />
            <PlatformError value={tenant.failure} returnTo={back} />
            {tenant.loading && <p role="status">Loading selected tenant…</p>}
            {selectedTenant && (
              <div className="janso-page-navigation">
                <span>
                  {selectedTenant.name} · {selectedTenant.status}
                </span>
                {canReadTenant && (
                  <a
                    className="janso-link"
                    href={'/platform/tenants/' + selected}
                  >
                    View tenant details
                  </a>
                )}
              </div>
            )}
            {selectedTenant?.status === 'closed' && (
              <Notice tone="info">
                This tenant is closed. Administrator details are available for
                review.
              </Notice>
            )}
          </div>
        </CardBody>
      </Card>
      {!selected && (
        <Notice tone="info">
          Select a tenant to see and manage its administrators.
        </Notice>
      )}
      {selectedTenant && !tenant.failure && (
        <Card>
          <CardHeader
            title={`${selectedTenant.name} administrators`}
            subtitle="Accounts with a direct tenant-administrator assignment. Revoked assignments are retained for review and restoration."
          />
          <FilterBar
            onClearAll={query.clearFilters}
            applied={[
              ...(query.q
                ? [{ id: 'q', label: 'Search', value: query.q }]
                : []),
              ...(query.filters.status
                ? [
                    {
                      id: 'status',
                      label: 'Status',
                      value: String(query.filters.status),
                    },
                  ]
                : []),
            ]}
            onRemove={(id) =>
              id === 'q' ? query.setSearch('') : query.setFilter('status', null)
            }
            actions={
              <IconButton
                label="Refresh administrators"
                icon={<RefreshIcon />}
                disabled={list.loading}
                onClick={list.refresh}
              />
            }
          >
            <TableSearch
              label="Search administrators"
              value={query.q}
              onChange={query.setSearch}
              maxLength={100}
              placeholder="Search administrator name"
              hint="Enter at least 2 characters. Matches the beginning of the name."
            />
            <Select
              label="Account status"
              value={String(query.filters.status ?? '')}
              onChange={(value) => query.setFilter('status', value || null)}
              options={[
                { value: '', label: 'All statuses' },
                ...['active', 'invited', 'suspended', 'deactivated'].map(
                  (value) => ({
                    value,
                    label: value[0].toUpperCase() + value.slice(1),
                  }),
                ),
              ]}
            />
          </FilterBar>
          <DataTable
            caption="Tenant administrators"
            columns={columns}
            rows={list.data?.items ?? []}
            rowId={(row) => row.id}
            rowLabel={(row) => row.display_name}
            loading={list.loading}
            error={list.failure ? asErrorStatus(list.failure.status) : null}
            errorDetail={<PlatformError value={list.failure} returnTo={back} />}
            onRetry={list.refresh}
            sort={query.sort}
            onSortChange={query.setSort}
            filtered={query.filtered}
            onClearFilters={query.clearFilters}
            emptyTitle="No administrators found"
            emptyBody="Invite an administrator for this tenant or clear the filters."
            emptyAction={create}
            rowActions={(row) => [
              { id: 'view', label: 'View details' },
              ...(canWrite &&
              ['active', 'invited', 'suspended'].includes(row.status)
                ? [{ id: 'edit', label: 'Edit administrator' }, { id: 'access', label: 'Manage administrator access' }, ...(row.status === 'active' ? [{ id: 'recovery', label: 'Reset password' }] : [])]
                : []),
            ]}
            onAction={(action, row) =>
              goTo(
                administratorLink(
                  administratorRoot +
                    '/' +
                    row.id +
                    (action === 'edit' ? '/edit' : ''),
                  selected,
                  back,
                ) + (action === 'access' ? '#administrator-actions' : action === 'recovery' ? '#password-recovery' : ''),
              )
            }
          />
          <Pager
            noun="administrator"
            count={list.data?.items.length ?? 0}
            from={query.page.from}
            limit={query.limit}
            hasPrevious={query.page.hasPrevious}
            hasNext={!list.loading && !list.failure && query.page.hasNext}
            onPrevious={query.previousPage}
            onNext={query.nextPage}
            onLimitChange={query.setLimit}
            busy={list.loading}
          />
        </Card>
      )}
    </div>
  );
}
