'use client';
import { useEffect, useState } from 'react';
import {
  Badge,
  Button,
  Disclosure,
  FilterBar,
  TableSearch,
  Card,
  CardBody,
  CardHeader,
  DataTable,
  Notice,
  PageHeader,
  Select,
  TextField,
  type CellType,
  type Column,
} from '@janso/ui';
import {
  useAccountingList,
  useAccountingRecord,
} from '../lib/accounting-configuration';
import {
  accountingBack,
  accountingLabel,
  accountingLink,
  accountingRoot,
  accountingUUID,
  type AccountingRecord,
  type AccountingResourceConfig,
} from '../lib/accounting-configuration-resources';
import {
  accountingDescription,
  accountingRelatedRowActions,
} from '../lib/accounting-masters';
import { validMasterDate } from '../lib/catalog-masters';
import {
  partyDirectoryActions,
  usePartyActionFeatures,
} from '../lib/party-directory-actions';
import {
  AccountingFailure,
  AccountingLoading,
  AccountingNavigation,
  AccountingPager,
  AccountingReference,
} from './AccountingConfigurationCommon';
const references: Record<string, { source: string; label: string }> = {
  party_id: { source: 'parties', label: 'Party' },
  account_id: { source: 'accounts', label: 'Account' },
  group_id: { source: 'account-groups', label: 'Account group' },
  head_id: { source: 'account-heads', label: 'Account head' },
  parent_id: { source: 'account-groups', label: 'Parent group' },
  payment_term_id: { source: 'payment-terms', label: 'Payment term' },
  section_id: { source: 'withholding-sections', label: 'Withholding section' },
};
export function AccountingConfigurationDirectory({
  company,
  config,
  canManage,
  canHistory = false,
  canSetup = false,
  availableResources = [],
  initialQuery = '',
  supplier = false,
  canImport = false,
  manageableResources = [],
  canReadCompanyConfiguration = false,
  canManagePartyPricing = false,
  canOpening = false,
}: {
  company: string;
  config: AccountingResourceConfig;
  canManage: boolean;
  canHistory?: boolean;
  canSetup?: boolean;
  availableResources?: readonly string[];
  initialQuery?: string;
  supplier?: boolean;
  canImport?: boolean;
  manageableResources?: readonly string[];
  canReadCompanyConfiguration?: boolean;
  canManagePartyPricing?: boolean;
  canOpening?: boolean;
}) {
  const partyActions = usePartyActionFeatures(
    company,
    config.resource === 'parties' &&
      canReadCompanyConfiguration &&
      (availableResources.includes('party-credit-policies') ||
        canManagePartyPricing),
  );
  const initial = new URLSearchParams(initialQuery),
    base = accountingRoot + '/' + (supplier ? 'suppliers' : config.resource),
    back = accountingBack(initial.get('returnTo') ?? undefined);
  const [search, setSearch] = useState(initial.get('q') ?? ''),
    [query, setQuery] = useState(search),
    [filters, setFilters] = useState<Record<string, string>>(() =>
      Object.fromEntries(
        [...initial].filter(([key]) => key !== 'returnTo' && key !== 'q'),
      ),
    );
  const metadata = useAccountingRecord(company, config, undefined, false);
  useEffect(() => {
    const timer = setTimeout(() => setQuery(search.trim()), 300);
    return () => clearTimeout(timer);
  }, [search]);
  const fields = metadata.metadata?.fields ?? [],
    has = (key: string) =>
      fields.some((field) => field.key === key && field.readable),
    keys = metadata.metadata?.filter_keys ?? [],
    searchable = !!metadata.metadata?.searchable,
    unavailableSupplier =
      supplier && !!metadata.metadata && !keys.includes('role'),
    unavailableRelationship =
      unavailableSupplier ||
      (!!metadata.metadata &&
        Object.entries(filters).some(
          ([key, value]) =>
            references[key] &&
            value &&
            (!keys.includes(key) || !accountingUUID.test(value)),
        ));
  const filter = new URLSearchParams();
  if (searchable && query.length >= 2) filter.set('q', query);
  for (const key of keys) {
    const value = supplier && key === 'role' ? 'SUPPLIER' : filters[key];
    if (
      value &&
      (!references[key] || accountingUUID.test(value)) &&
      (key !== 'as_of' || validMasterDate(value))
    )
      filter.set(key, value);
  }
  const primary = ['accounts', 'parties'].includes(config.resource);
  const sorts = [
    { value: '-id', label: 'Newest first' },
    { value: 'id', label: 'Oldest first' },
    ...(has('name')
      ? [
          { value: 'name', label: 'Name A-Z' },
          { value: '-name', label: 'Name Z-A' },
        ]
      : []),
    ...(config.resource === 'accounts' && has('code')
      ? [
          { value: 'code', label: 'Code A-Z' },
          { value: '-code', label: 'Code Z-A' },
        ]
      : []),
  ];
  if (primary)
    filter.set(
      'sort',
      sorts.some((sort) => sort.value === filters.sort) ? filters.sort : '-id',
    );
  const list = useAccountingList(
    company,
    config,
    filter.toString(),
    !!metadata.metadata && !unavailableRelationship,
  );
  const navigationFilter = new URLSearchParams(filter);
  if (!filters.sort) navigationFilter.delete('sort');
  if (unavailableRelationship)
    for (const [key, value] of Object.entries(filters)) {
      if (references[key] && accountingUUID.test(value))
        navigationFilter.set(key, value);
    }
  const here = accountingLink(
    base + (navigationFilter.size ? '?' + navigationFilter : ''),
    back,
  );
  useEffect(() => {
    if (metadata.metadata) window.history.replaceState(null, '', here);
  }, [here, !!metadata.metadata]);
  const columns: Column<AccountingRecord>[] = [
    ...(
      [
        'code',
        'name',
        'label',
        'alias',
        'role',
        'party_type',
        'kind',
        'purpose',
        'scheme',
        'deductee_type',
        'status',
        'currency',
        'method',
        'rate',
        'rate_percent',
        'no_pan_rate_percent',
        'limit_amount',
        'percentage',
        'days',
        'valid_from',
        'valid_to',
      ] as const
    )
      .filter(
        (key) => has(key) || (key === 'status' && keys.includes('status')),
      )
      .map((key) => ({
        key,
        header:
          key === 'status'
            ? 'Status'
            : (fields.find((field) => field.key === key)?.label ??
              key.replaceAll('_', ' ')),
        type: (key === 'status' || key === 'party_type'
          ? 'custom'
          : key.startsWith('valid_')
            ? 'date'
            : ['rate_percent', 'no_pan_rate_percent', 'percentage'].includes(
                  key,
                )
              ? 'percent'
              : key === 'limit_amount' && has('currency')
                ? 'money'
                : 'text') as CellType,
        ...(key === 'status'
          ? {
              render: (row: AccountingRecord) =>
                row.status == null ? (
                  'Protected'
                ) : (
                  <Badge
                    tone={
                      row.status === 'ACTIVE'
                        ? 'success'
                        : row.status === 'DRAFT'
                          ? 'info'
                          : 'neutral'
                    }
                  >
                    {row.status === 'INACTIVE'
                      ? 'Retired'
                      : String(row.status).slice(0, 1) +
                        String(row.status).slice(1).toLowerCase()}
                  </Badge>
                ),
            }
          : key === 'party_type'
            ? {
                render: (row: AccountingRecord) =>
                  row.party_type === 'ORGANISATION'
                    ? 'Organisation'
                    : row.party_type === 'PERSON'
                      ? 'Person'
                      : 'Not specified',
              }
            : {}),
        ...(['rate_percent', 'no_pan_rate_percent', 'percentage'].includes(key)
          ? { precision: 4 }
          : {}),
      })),
    ...(config.resource === 'parties' &&
    list.data?.items.some((row) => Array.isArray(row.roles))
      ? [
          {
            key: 'roles',
            header: 'Active roles',
            type: 'custom' as const,
            render: (row: AccountingRecord) =>
              Array.isArray(row.roles) ? (
                row.roles.length ? (
                  <div className="janso-inline">
                    {row.roles.map((role) => (
                      <Badge key={String(role)} tone="neutral">
                        {String(role).slice(0, 1) + String(role).slice(1).toLowerCase()}
                      </Badge>
                    ))}
                  </div>
                ) : (
                  'No active role'
                )
              ) : (
                'Protected'
              ),
          },
        ]
      : []),
    {
      key: 'id',
      header: 'Configuration',
      type: 'custom',
      render: (row) => (
        <a
          className="janso-link"
          href={accountingLink(base + '/' + row.id, here)}
        >
          Open {accountingLabel(row)}
        </a>
      ),
    },
  ];
  const newQuery = new URLSearchParams();
  for (const key of [config.owner, 'section_id'].filter(Boolean) as string[])
    if (filter.get(key)) newQuery.set(key, filter.get(key)!);
  if (config.resource === 'party-roles' && filter.get('role'))
    newQuery.set('role', filter.get('role')!);
  if (config.resource === 'accounts') {
    const kind = filter.get('kind');
    if (
      fields
        .find((field) => field.key === 'kind')
        ?.control.choices?.includes(kind!)
    )
      newQuery.set('kind', kind!);
    if (filter.get('group_id'))
      newQuery.set('group_id', filter.get('group_id')!);
  }
  if (config.resource === 'accounts' && filter.get('party_id')) {
    newQuery.set('party_id', filter.get('party_id')!);
    newQuery.set('kind', 'PARTY');
  }
  const newPath = accountingLink(
    base + '/new' + (newQuery.size ? '?' + newQuery : ''),
    here,
  );
  const update = (key: string, value: string | null) =>
    setFilters((current) => ({ ...current, [key]: value ?? '' }));
  const clear = () => {
      setSearch('');
      setQuery('');
      setFilters({});
    },
    filtered = [...filter.keys()].some(
      (key) => key !== 'sort' && (!supplier || key !== 'role'),
    );
  return (
    <div className="janso-page">
      <AccountingNavigation
        title={supplier ? 'Suppliers' : config.title}
        availableResources={availableResources}
        resource={supplier ? 'suppliers' : config.resource}
        back={back}
      />
      <PageHeader
        title={supplier ? 'Suppliers' : config.title}
        lede={
          supplier
            ? 'Parties with an active supplier role. Customers and suppliers share the same party identity.'
            : accountingDescription(config)
        }
        actions={
          (canOpening && primary) ||
          (canImport && config.resource === 'parties') ||
          (canManage &&
            metadata.metadata?.can_create &&
            !config.readonly &&
            !unavailableRelationship) ? (
            <div className="janso-form-actions">
              {canOpening && primary && <a className="janso-link" href="/accounting/opening">Opening balances</a>}
              {canManage &&
                metadata.metadata?.can_create &&
                !config.readonly &&
                !unavailableRelationship && (
                  <a className="janso-btn janso-btn--primary" href={newPath}>
                    New {supplier ? 'supplier' : config.singular.toLowerCase()}
                  </a>
                )}
              {config.resource === 'parties' &&
                (canImport ? (
                  <a
                    className="janso-link"
                    href={accountingLink(
                      '/accounting/' +
                        (supplier ? 'suppliers' : 'parties') +
                        '/import',
                      here,
                    )}
                  >
                    Import {supplier ? 'suppliers' : 'parties'}
                  </a>
                ) : (
                  <span
                    className="janso-link"
                    role="link"
                    aria-disabled="true"
                    title={
                      supplier
                        ? 'Accounting import access is required for this company.'
                        : 'Accounting import access is required for this company.'
                    }
                  >
                    Import {supplier ? 'suppliers' : 'parties'}
                  </span>
                ))}
            </div>
          ) : undefined
        }
      />
      {!canManage && <Notice>Read-only access for this company.</Notice>}
      {metadata.metadata?.unavailable_reason && (
        <Notice tone="warning">
          {metadata.metadata.unavailable_reason}{' '}
          <a
            className="janso-link"
            href={accountingLink(
              '/companies/' + company + '/configuration',
              here,
            )}
          >
            Open Company Config
          </a>
        </Notice>
      )}
      {config.readonly && (
        <Notice>
          These records are maintained by the installed chart. Review them here
          {canSetup && (
            <>
              {' '}
              or{' '}
              <a
                className="janso-link"
                href={accountingLink('/accounting/setup', here)}
              >
                Open company accounting setup
              </a>
            </>
          )}
          .
        </Notice>
      )}
      {supplier && (
        <Notice>
          Activate the party and its supplier role to complete setup. Unfinished
          parties remain available in{' '}
          <a
            className="janso-link"
            href={accountingLink('/accounting/parties', here)}
          >
            Parties
          </a>
          .
        </Notice>
      )}
      <Card>
        <CardHeader
          title={supplier ? 'Suppliers' : config.title}
          action={
            <Button
              variant="ghost"
              onClick={() => {
                metadata.refresh();
                list.first();
                partyActions.refresh();
              }}
              disabled={metadata.loading || list.loading}
            >
              Refresh
            </Button>
          }
        />
        <CardBody>
          <div className="janso-flow">
            <FilterBar
              applied={[...filter]
                .filter(
                  ([key]) => key !== 'sort' && (!supplier || key !== 'role'),
                )
                .map(([key, value]) => ({
                  id: key,
                  label:
                    references[key]?.label ??
                    (key === 'q' ? 'Search' : key.replaceAll('_', ' ')),
                  value: accountingUUID.test(value) ? 'Selected record' : value,
                }))}
              onRemove={(key) => {
                if (key === 'q') {
                  setSearch('');
                  setQuery('');
                } else update(key, '');
              }}
              onClearAll={clear}
            >
              {searchable && (
                <TableSearch
                  label="Search"
                  value={search}
                  delay={0}
                  placeholder="Search by name or code"
                  onChange={setSearch}
                  busy={list.loading}
                />
              )}
              {keys.includes('status') && (
                <Select
                  label="Status"
                  value={filters.status ?? ''}
                  options={[
                    { value: '', label: 'All statuses' },
                    { value: 'DRAFT', label: 'Draft' },
                    { value: 'ACTIVE', label: 'Active' },
                    { value: 'INACTIVE', label: 'Retired' },
                  ]}
                  onChange={(value) => update('status', value)}
                />
              )}
              {keys.includes('role') && !supplier && (
                <Select
                  label="Party role"
                  value={filters.role ?? ''}
                  options={[
                    { value: '', label: 'All parties' },
                    { value: 'CUSTOMER', label: 'Customers' },
                    { value: 'SUPPLIER', label: 'Suppliers' },
                    { value: 'OTHER', label: 'Other roles' },
                    { value: 'BROKER', label: 'Brokers' },
                  ]}
                  onChange={(value) => update('role', value)}
                />
              )}
              {keys.includes('kind') &&
              fields.find((field) => field.key === 'kind')?.control.choices
                ?.length ? (
                <Select
                  label="Kind"
                  value={filters.kind ?? ''}
                  options={[
                    { value: '', label: 'All kinds' },
                    ...(
                      fields.find((field) => field.key === 'kind')!.control
                        .choices ?? []
                    ).map((value) => ({
                      value,
                      label: value.replaceAll('_', ' '),
                    })),
                  ]}
                  onChange={(value) => update('kind', value)}
                />
              ) : null}
              {primary && (
                <Select
                  label="Sort by"
                  value={filter.get('sort')!}
                  options={sorts}
                  onChange={(value) => update('sort', value)}
                />
              )}
            </FilterBar>
            {(keys.some((key) => references[key]) ||
              keys.includes('as_of')) && (
              <Disclosure
                summary="More filters"
                defaultOpen={keys.some(
                  (key) =>
                    (references[key] || key === 'as_of') && !!filters[key],
                )}
              >
                <div className="janso-form-grid">
                  {keys
                    .filter((key) => references[key])
                    .map((key) => (
                      <AccountingReference
                        key={key}
                        company={company}
                        {...references[key]}
                        value={
                          accountingUUID.test(filters[key] ?? '')
                            ? filters[key]
                            : null
                        }
                        onChange={(value) => update(key, value)}
                        returnTo={here}
                      />
                    ))}
                  {keys.includes('as_of') && (
                    <TextField
                      label="Effective on"
                      type="date"
                      value={filters.as_of ?? ''}
                      onChange={(event) => update('as_of', event.target.value)}
                      error={
                        filters.as_of && !validMasterDate(filters.as_of)
                          ? 'Enter a valid date.'
                          : undefined
                      }
                    />
                  )}
                </div>
              </Disclosure>
            )}
            {unavailableSupplier ? (
              <Notice tone="warning">
                <p>
                  Supplier role filtering is unavailable with your field access.
                </p>
                <a
                  className="janso-link"
                  href={accountingLink('/accounting/parties', back)}
                >
                  Open Parties
                </a>
              </Notice>
            ) : (
              unavailableRelationship && (
                <Notice tone="warning">
                  The requested relationship filter is unavailable. Clear
                  filters to view records you can read, or ask an administrator
                  to check the link and your field access.{' '}
                  <Button variant="ghost" onClick={clear}>
                    Clear filters
                  </Button>
                </Notice>
              )
            )}
            {!unavailableRelationship &&
              (filtered || search) &&
              !!list.data?.items.length && (
                <Button variant="ghost" onClick={clear}>
                  Clear filters
                </Button>
              )}
            <AccountingFailure
              failure={metadata.failure}
              retry={metadata.refresh}
            />
            <AccountingFailure failure={list.failure} retry={list.first} />
            {!unavailableRelationship &&
              (metadata.loading ||
              list.loading ||
              (!!metadata.metadata && !list.data && !list.failure) ? (
                <AccountingLoading />
              ) : (
                !metadata.failure &&
                !list.failure && (
                  <DataTable
                    caption={supplier ? 'Suppliers' : config.title}
                    columns={columns}
                    rows={list.data?.items ?? []}
                    rowId={(row) => row.id}
                    rowLabel={accountingLabel}
                    filtered={filtered}
                    onClearFilters={clear}
                    emptyTitle={
                      filtered
                        ? 'No matching records'
                        : 'No ' + config.title.toLowerCase() + ' yet'
                    }
                    emptyBody={
                      filtered
                        ? 'Clear or change the filters to see more records.'
                        : canManage && !config.readonly
                          ? 'Create the first record to start configuring this area.'
                          : 'Records will appear here when your company setup is complete.'
                    }
                    emptyAction={
                      !filtered &&
                      canManage &&
                      metadata.metadata?.can_create &&
                      !config.readonly ? (
                        <a
                          className="janso-btn janso-btn--primary"
                          href={newPath}
                        >
                          Create first{' '}
                          {supplier
                            ? 'supplier'
                            : config.singular.toLowerCase()}
                        </a>
                      ) : undefined
                    }
                    rowActions={(row) => [
                      {
                        id: 'open',
                        label: 'View details',
                        href: accountingLink(base + '/' + row.id, here),
                      },
                      ...(canHistory && !config.workflow
                        ? [
                            {
                              id: 'history',
                              label: 'View history',
                              href: accountingLink(
                                base + '/' + row.id + '/history',
                                here,
                              ),
                            },
                          ]
                        : []),
                      ...(canManage &&
                      !config.readonly &&
                      !config.workflow &&
                      row.status !== 'INACTIVE'
                        ? [
                            {
                              id: 'edit',
                              label: 'Edit',
                              href: accountingLink(
                                base + '/' + row.id + '/edit',
                                here,
                              ),
                            },
                          ]
                        : []),
                      ...accountingRelatedRowActions(
                        config.resource,
                        row.id,
                        availableResources,
                        here,
                      ),
                      ...(config.resource === 'parties'
                        ? partyDirectoryActions(
                            row.id,
                            here,
                            availableResources,
                            manageableResources,
                            partyActions.features,
                            canManagePartyPricing,
                          )
                        : []),
                    ]}
                  />
                )
              ))}
            {!unavailableRelationship && (
              <AccountingPager
                list={list}
                noun={config.singular.toLowerCase()}
              />
            )}
          </div>
        </CardBody>
      </Card>
    </div>
  );
}
