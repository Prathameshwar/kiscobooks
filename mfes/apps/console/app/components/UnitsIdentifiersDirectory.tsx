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
import { masterRequest } from '../lib/catalog-master-api';
import type { MasterConfig, MasterRow } from '../lib/catalog-masters';
import { useServiceList } from '../lib/service-resource';
import {
  identifierBase,
  identifierCodeSearch,
  identifierId,
  identifierLink,
  identifierReturn,
  identifierTitle,
  identifierVisible,
  identifierWritable,
  useIdentifierFields,
} from '../lib/units-identifiers';
import {
  IdentifierFailure,
  IdentifierNavigation,
  IdentifierUnitLabel,
  IdentifierUnitReference,
  type IdentifierAccess,
} from './UnitsIdentifiersCommon';

export function UnitsIdentifiersDirectory({
  company,
  config,
  canManage,
  access,
  initialQuery = '',
}: {
  company: string;
  config: MasterConfig;
  canManage: boolean;
  access: IdentifierAccess;
  initialQuery?: string;
}) {
  const root = '/masters/' + config.resource,
    initial = new URL(
      identifierReturn(root + '?' + initialQuery, root),
      'https://console.invalid',
    ),
    conversion = config.resource === 'unit-conversions',
    codes = identifierCodeSearch(config.resource);
  const [query, setQuery] = useState(new URLSearchParams(initial.search)),
    [adjusted, setAdjusted] = useState(false),
    metadata = useIdentifierFields(company, config.entity),
    fields = metadata.data?.fields ?? [],
    available = (key: string) => identifierVisible(fields, key);
  const filters = new URLSearchParams(),
    canSearch =
      !conversion && available('code') && (codes || available('name'));
  if (canSearch && query.get('q')) filters.set('q', query.get('q')!);
  for (const key of conversion
    ? ['from_unit_id', 'canonical_unit_id']
    : [
        'is_active',
        ...(config.resource === 'identifier-types' ? ['is_barcode'] : []),
      ])
    if (available(key) && query.get(key)) filters.set(key, query.get(key)!);
  const requestedSort = query.get('sort') ?? '-id',
    sortKey = requestedSort.replace(/^-/, '');
  const sort =
    sortKey === 'id' ||
    (available(sortKey) && !conversion && (!codes || sortKey === 'code'))
      ? requestedSort
      : '-id';
  filters.set('sort', sort);
  const filterText = filters.toString(),
    queryText = query.toString();
  useEffect(() => {
    if (!metadata.data) return;
    const next = new URLSearchParams(queryText),
      allowed = new URLSearchParams(filterText);
    for (const key of [
      'q',
      'is_active',
      'is_barcode',
      'from_unit_id',
      'canonical_unit_id',
    ]) {
      if (next.has(key) && !allowed.has(key)) next.delete(key);
    }
    if (next.has('sort') && next.get('sort') !== allowed.get('sort'))
      next.delete('sort');
    if (next.toString() !== queryText) {
      setQuery(next);
      setAdjusted(true);
    }
  }, [metadata.data, filterText, queryText]);
  const list = useServiceList<MasterRow>(
    identifierBase(company, config.resource),
    filters.toString(),
    masterRequest,
    (row) => {
      if (!identifierId.test(row.id))
        throw {
          status: 502,
          message: 'The directory response could not be verified.',
        };
    },
  );
  useEffect(() => {
    const limit = initial.searchParams.get('limit');
    if (limit) list.setLimit(Number(limit));
  }, [company, config.resource]);
  const here = root + (query.size ? '?' + query : '');
  useEffect(() => {
    window.history.replaceState(null, '', here);
  }, [here]);
  function change(key: string, value: string) {
    setQuery((current) => {
      const next = new URLSearchParams(current);
      if (value) next.set(key, value);
      else next.delete(key);
      return next;
    });
  }
  function clear() {
    setQuery(
      new URLSearchParams(
        query.has('returnTo') ? { returnTo: query.get('returnTo')! } : {},
      ),
    );
  }
  const link = (row: MasterRow) => identifierLink(root + '/' + row.id, here),
    columns: Column<MasterRow>[] = [];
  for (const key of conversion
    ? ['from_unit_id', 'canonical_unit_id', 'numerator', 'denominator']
    : ['code', 'name', 'is_barcode', 'is_active']) {
    if (!available(key)) continue;
    const field = fields.find((field) => field.key === key)!;
    columns.push({
      key,
      header:
        field.label !== field.key ? field.label : (field.control?.label ?? key),
      type: 'custom',
      render: (row) => {
        if (!(key in row)) return 'Protected';
        if (key.endsWith('_unit_id'))
          return access.units && typeof row[key] === 'string' ? (
            <IdentifierUnitLabel
              company={company}
              id={row[key] as string}
              here={here}
            />
          ) : (
            'Protected'
          );
        if (key === 'code' || key === 'name')
          return (
            <a className="janso-link" href={link(row)}>
              {String(row[key])}
            </a>
          );
        if (key === 'is_active') return row[key] ? 'Active' : 'Inactive';
        if (key === 'is_barcode')
          return row[key] ? 'Barcode' : 'Other identifier';
        return String(row[key]);
      },
    });
  }
  if (conversion || !columns.length)
    columns.unshift({
      key: 'record',
      header: 'Record',
      type: 'custom',
      render: (row) => (
        <a className="janso-link" href={link(row)}>
          View {config.singular}
        </a>
      ),
    });
  return (
    <div className="janso-page">
      <IdentifierNavigation
        title={config.title}
        access={access}
        back={query.get('returnTo') ?? '/inventory/units-identifiers'}
      />
      <PageHeader
        title={config.title}
        lede={
          conversion
            ? 'Declare exact conversions directly to a canonical unit. Existing ratios remain immutable.'
            : 'Maintain reusable definitions in the company currently open.'
        }
        actions={
          canManage && (
            <a
              className="janso-btn janso-btn--primary"
              href={identifierLink(root + '/new', here)}
            >
              New {config.singular}
            </a>
          )
        }
      />
      {!canManage && <Notice>Read-only access.</Notice>}
      {adjusted && (
        <Notice tone="warning">
          Unavailable search, filter or sort settings were removed. The
          remaining records are shown.
        </Notice>
      )}
      <IdentifierFailure
        failure={metadata.failure ?? list.failure}
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
                id === 'q'
                  ? 'Search'
                  : id.endsWith('_unit_id')
                    ? 'Unit'
                    : id === 'is_barcode'
                      ? 'Classification'
                      : 'Status',
              value: id.endsWith('_unit_id')
                ? 'Selected unit'
                : id === 'is_barcode'
                  ? value === 'true'
                    ? 'Barcode'
                    : 'Other identifier'
                  : value === 'true'
                    ? 'Active'
                    : value === 'false'
                      ? 'Inactive'
                      : value,
            }))}
          onRemove={(key) => change(key, '')}
          onClearAll={clear}
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
          {canSearch && (
            <TableSearch
              label={'Search ' + config.title.toLowerCase()}
              value={query.get('q') ?? ''}
              onChange={(value) =>
                change('q', value.trim().length >= 2 ? value : '')
              }
              hint={
                codes
                  ? 'At least two characters; search by code.'
                  : 'At least two characters; search by code or name.'
              }
            />
          )}
          {available('is_active') && (
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
          {config.resource === 'identifier-types' &&
            available('is_barcode') && (
              <Select
                label="Identifier classification"
                placeholder="All classifications"
                value={query.get('is_barcode') ?? ''}
                options={[
                  { value: 'true', label: 'Barcode' },
                  { value: 'false', label: 'Other identifier' },
                ]}
                onChange={(value) => change('is_barcode', value)}
              />
            )}
          {conversion &&
            access.units &&
            ['from_unit_id', 'canonical_unit_id']
              .filter(available)
              .map((key) => (
                <IdentifierUnitReference
                  key={key}
                  company={company}
                  label={
                    key === 'from_unit_id'
                      ? 'Filter by source unit'
                      : 'Filter by canonical unit'
                  }
                  value={query.get(key)}
                  onChange={(value) => change(key, value ?? '')}
                  activeOnly={false}
                />
              ))}
          <Select
            label="Sort"
            value={sort}
            options={[
              { value: '-id', label: 'Newest first' },
              { value: 'id', label: 'Oldest first' },
              ...(!conversion && available('code')
                ? [
                    { value: 'code', label: 'Code A to Z' },
                    { value: '-code', label: 'Code Z to A' },
                  ]
                : []),
              ...(!conversion && !codes && available('name')
                ? [
                    { value: 'name', label: 'Name A to Z' },
                    { value: '-name', label: 'Name Z to A' },
                  ]
                : []),
            ]}
            onChange={(value) => change('sort', value)}
          />
        </FilterBar>
        <DataTable
          caption={config.title + ' directory'}
          columns={columns}
          rows={list.data?.items ?? []}
          rowId={(row) => row.id}
          rowLabel={identifierTitle}
          loading={metadata.loading || list.loading}
          filtered={filters.size > 1}
          emptyTitle={'No ' + config.title.toLowerCase() + ' found'}
          emptyBody="Create a record or clear the filters."
          onClearFilters={clear}
          rowActions={(row) => [
            {
              id: 'view',
              label: 'View details',
              href: identifierLink(root + '/' + row.id, here),
            },
            ...(canManage &&
            !conversion &&
            identifierVisible(fields, 'row_version') &&
            (codes ? ['name'] : ['code', 'name']).some((key) =>
              identifierWritable(fields, [key]),
            )
              ? [
                  {
                    id: 'edit',
                    label: 'Edit details',
                    href: identifierLink(root + '/' + row.id + '/edit', here),
                  },
                ]
              : []),
          ]}
        />
        <Pager
          count={list.data?.items.length ?? 0}
          limit={list.limit}
          busy={list.loading}
          hasPrevious={list.hasPrevious}
          hasNext={!!list.data?.page.has_more}
          onPrevious={list.previous}
          onNext={list.next}
          onLimitChange={(value) => {
            list.setLimit(value);
            change('limit', String(value));
          }}
          noun={config.singular}
        />
      </Card>
    </div>
  );
}
