'use client';
import { useEffect, useState } from 'react';
import {
  Button,
  Card,
  CardHeader,
  DataTable,
  FilterBar,
  Notice,
  PageHeader,
  Pager,
  Select,
  TableSearch,
  type Column,
} from '@janso/ui';
import type { MasterConfig, MasterRow } from '../lib/catalog-masters';
import { masterRequest } from '../lib/catalog-master-api';
import { useServiceList } from '../lib/service-resource';
import {
  profileBase,
  profileId,
  profileLink,
  profileReturn,
  profileVisible,
  profileWritable,
  useProfileFields,
} from '../lib/product-profiles';
import type {
  ProductProfileAccess,
  ProductProfileResource,
} from '../lib/product-profile-resources';
import {
  ProfileExplanation,
  ProfileFailure,
  ProfileNavigation,
} from './ProductProfileCommon';
export function ProductProfileDirectory({
  company,
  config,
  canManage,
  access,
  initialQuery = '',
}: {
  company: string;
  config: MasterConfig;
  canManage: boolean;
  access: ProductProfileAccess;
  initialQuery?: string;
}) {
  const operation = config.resource.startsWith('manufacturing-');
  const noun =
    config.resource === 'manufacturing-routes' ? 'route' : 'operation';
  const root = '/masters/' + config.resource,
    initial = new URL(
      profileReturn(root + '?' + initialQuery, root),
      'https://console.invalid',
    );
  const [query, setQuery] = useState(initial.searchParams),
    [adjusted, setAdjusted] = useState(false),
    metadata = useProfileFields(company, config.entity),
    fields = metadata.data?.fields ?? [],
    visible = (key: string) => profileVisible(fields, key);
  const filters = new URLSearchParams();
  if (visible('code') && visible('name') && query.get('q'))
    filters.set('q', query.get('q')!);
  if (visible('is_active') && query.get('is_active'))
    filters.set('is_active', query.get('is_active')!);
  if (visible('code') && query.get('code'))
    filters.set('code', query.get('code')!);
  const requested = query.get('sort') ?? '-id',
    sort =
      ['id', '-id'].includes(requested) || visible(requested.replace(/^-/, ''))
        ? requested
        : '-id';
  filters.set('sort', sort);
  const queryText = query.toString(),
    filterText = filters.toString();
  useEffect(() => {
    if (!metadata.data) return;
    const next = new URLSearchParams(queryText),
      allowed = new URLSearchParams(filterText);
    for (const key of ['q', 'code', 'is_active'])
      if (next.has(key) && !allowed.has(key)) next.delete(key);
    if (next.has('sort') && next.get('sort') !== allowed.get('sort'))
      next.delete('sort');
    if (next.toString() !== queryText) {
      setQuery(next);
      setAdjusted(true);
    }
  }, [metadata.data, queryText, filterText]);
  const list = useServiceList<MasterRow>(
    profileBase(company, config.resource),
    filters.toString(),
    masterRequest,
    (row) => {
      if (!profileId.test(row.id))
        throw {
          status: 502,
          message: 'The profile directory could not be verified.',
        };
    },
  );
  useEffect(() => {
    if (initial.searchParams.has('limit'))
      list.setLimit(Number(initial.searchParams.get('limit')));
  }, [company, config.resource]);
  const here = root + (query.size ? '?' + query : '');
  useEffect(() => {
    window.history.replaceState(null, '', here);
  }, [here]);
  const change = (key: string, value: string) =>
    setQuery((current) => {
      const next = new URLSearchParams(current);
      value ? next.set(key, value) : next.delete(key);
      return next;
    });
  const columns: Column<MasterRow>[] = ['code', 'name', 'is_active']
    .filter(visible)
    .map((key) => ({
      key,
      header: key === 'is_active' ? 'Status' : key === 'code' ? 'Code' : 'Name',
      type: 'custom',
      render: (row) =>
        !(key in row) ? (
          'Protected'
        ) : key === 'is_active' ? (
          row.is_active ? (
            'Active'
          ) : (
            'Inactive'
          )
        ) : (
          <a
            className="janso-link"
            href={profileLink(root + '/' + row.id, here)}
          >
            {String(row[key])}
          </a>
        ),
    }));
  if (!columns.length)
    columns.push({
      key: 'record',
      header: 'Profile',
      type: 'custom',
      render: (row) => (
        <a className="janso-link" href={profileLink(root + '/' + row.id, here)}>
          View {operation ? noun : 'profile'}
        </a>
      ),
    });
  const failure = metadata.failure ?? list.failure;
  return (
    <div className="janso-page">
      <ProfileNavigation
        resource={config.resource as ProductProfileResource}
        title={config.title}
        back={
          query.get('returnTo') ??
          (config.resource.startsWith('manufacturing-')
            ? '/masters'
            : '/inventory/product-profiles')
        }
        access={access}
      />
      <PageHeader
        title={config.title}
        lede="Maintain reusable definitions for the company currently open."
        actions={
          canManage && (
            <a
              className="janso-btn janso-btn--primary"
              href={profileLink(root + '/new', here)}
            >
              New {config.singular}
            </a>
          )
        }
      />
      <ProfileExplanation
        resource={config.resource as ProductProfileResource}
      />
      {!canManage && <Notice>Read-only access.</Notice>}
      {adjusted && (
        <Notice tone="warning">
          Unavailable search, filter or sort settings were removed.
        </Notice>
      )}
      <ProfileFailure
        failure={failure}
        retry={() => {
          metadata.refresh();
          list.first();
        }}
      />
      <Card>
        <CardHeader title={config.title + ' directory'} />
        <FilterBar
          applied={[...filters]
            .filter(([key]) => key !== 'sort')
            .map(([id, value]) => ({
              id,
              label:
                id === 'q' ? 'Search' : id === 'is_active' ? 'Status' : 'Code',
              value:
                id === 'is_active'
                  ? value === 'true'
                    ? 'Active'
                    : 'Inactive'
                  : value,
            }))}
          onRemove={(key) => change(key, '')}
          onClearAll={() =>
            setQuery(
              new URLSearchParams(
                query.get('returnTo')
                  ? { returnTo: query.get('returnTo')! }
                  : {},
              ),
            )
          }
          actions={
            <Button
              variant="ghost"
              onClick={list.first}
              disabled={list.loading}
            >
              Refresh
            </Button>
          }
        >
          {visible('code') && visible('name') && (
            <TableSearch
              label={'Search ' + config.title.toLowerCase()}
              value={query.get('q') ?? ''}
              hint="At least two characters; search by code or name."
              onChange={(value) =>
                change('q', value.trim().length >= 2 ? value : '')
              }
            />
          )}
          {visible('is_active') && (
            <Select
              label="Status"
              placeholder="All statuses"
              value={query.get('is_active') ?? ''}
              options={[
                { value: 'true', label: 'Active' },
                { value: 'false', label: 'Inactive' },
              ]}
              onChange={(value) => change('is_active', value)}
            />
          )}
          <Select
            label="Sort"
            value={sort}
            options={[
              'id',
              '-id',
              ...(visible('code') ? ['code', '-code'] : []),
              ...(visible('name') ? ['name', '-name'] : []),
            ].map((value) => ({
              value,
              label: {
                id: 'Oldest first',
                '-id': 'Newest first',
                code: 'Code A–Z',
                '-code': 'Code Z–A',
                name: 'Name A–Z',
                '-name': 'Name Z–A',
              }[value]!,
            }))}
            onChange={(value) => change('sort', value)}
          />
        </FilterBar>
        {!failure && (
          <>
            <DataTable
              caption={config.title}
              columns={columns}
              rows={list.data?.items ?? []}
              rowId={(row) => row.id}
              rowLabel={(row) => row.name ?? row.code ?? config.singular}
              loading={metadata.loading || list.loading}
              emptyTitle={
                operation ? 'No ' + noun + 's found' : 'No profiles found'
              }
              emptyBody={
                operation
                  ? 'Create a ' + noun + ' or adjust the filters.'
                  : 'Create a profile or adjust the filters.'
              }
              rowActions={(row) => [
                {
                  id: 'view',
                  label: operation
                    ? 'View ' + noun + ' and revisions'
                    : 'View profile and revisions',
                  href: profileLink(root + '/' + row.id, here),
                },
                ...(canManage &&
                profileVisible(fields, 'row_version') &&
                ['code', 'name'].some((key) => profileWritable(fields, [key]))
                  ? [
                      {
                        id: 'edit',
                        label: 'Edit details',
                        href: profileLink(root + '/' + row.id + '/edit', here),
                      },
                    ]
                  : []),
              ]}
            />
            <Pager
              noun={config.singular}
              count={list.data?.items.length ?? 0}
              limit={list.limit}
              hasPrevious={list.hasPrevious}
              hasNext={list.data?.page.has_more ?? false}
              onPrevious={list.previous}
              onNext={list.next}
              onLimitChange={(limit) => {
                list.setLimit(limit);
                change('limit', String(limit));
              }}
              busy={list.loading}
            />
          </>
        )}
      </Card>
    </div>
  );
}
