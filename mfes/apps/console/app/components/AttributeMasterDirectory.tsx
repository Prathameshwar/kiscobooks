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
import {
  dimensions,
  type MasterConfig,
  type MasterRow,
} from '../lib/catalog-masters';
import { useServiceList } from '../lib/service-resource';
import {
  attributeBase,
  attributeEditKeys,
  attributeId,
  attributeLink,
  attributeReturn,
  attributeVisible,
  attributeWritable,
  useAttributeFields,
  valueTypes,
} from '../lib/attribute-masters';
import type { AttributeAccess } from '../lib/attribute-resources';
import {
  AttributeFailure,
  AttributeNavigation,
  AttributeReference,
} from './AttributeMasterCommon';
export function AttributeMasterDirectory({
  company,
  config,
  canManage,
  access,
  initialQuery = '',
}: {
  company: string;
  config: MasterConfig;
  canManage: boolean;
  access: AttributeAccess;
  initialQuery?: string;
}) {
  const root = '/masters/' + config.resource,
    initial = new URL(
      attributeReturn(root + '?' + initialQuery, root),
      'https://console.invalid',
    );
  const [query, setQuery] = useState(new URLSearchParams(initial.search)),
    [adjusted, setAdjusted] = useState(false);
  const metadata = useAttributeFields(company, config.entity),
    fields = metadata.data?.fields ?? [],
    visible = (key: string) => attributeVisible(fields, key);
  const allowedFilters = [
      'is_active',
      ...(config.resource === 'attribute-definitions'
        ? ['value_type', 'measurement_dimension', 'is_variant_capable']
        : config.resource === 'attribute-options'
          ? ['value_type', 'definition_id']
          : []),
    ],
    filters = new URLSearchParams();
  if (visible('code') && visible('name') && query.get('q'))
    filters.set('q', query.get('q')!);
  for (const key of allowedFilters)
    if (
      visible(key) &&
      query.get(key) &&
      (key !== 'definition_id' || access['attribute-definitions'])
    )
      filters.set(key, query.get(key)!);
  const requestedSort = query.get('sort') ?? '-id',
    sort =
      requestedSort.replace(/^-/, '') === 'id' ||
      (visible(requestedSort.replace(/^-/, '')) &&
        ['code', 'name'].includes(requestedSort.replace(/^-/, '')))
        ? requestedSort
        : '-id';
  filters.set('sort', sort);
  const filterText = filters.toString(),
    queryText = query.toString();
  useEffect(() => {
    if (!metadata.data) return;
    const next = new URLSearchParams(queryText),
      allowed = new URLSearchParams(filterText);
    for (const key of ['q', ...allowedFilters])
      if (next.has(key) && !allowed.has(key)) next.delete(key);
    if (next.has('sort') && next.get('sort') !== allowed.get('sort'))
      next.delete('sort');
    if (next.toString() !== queryText) {
      setQuery(next);
      setAdjusted(true);
    }
  }, [metadata.data, filterText, queryText]);
  const list = useServiceList<MasterRow>(
    attributeBase(company, config.resource),
    filterText,
    masterRequest,
    (row) => {
      if (!attributeId.test(row.id))
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
  const change = (key: string, value: string) =>
    setQuery((current) => {
      const next = new URLSearchParams(current);
      if (value) next.set(key, value);
      else next.delete(key);
      return next;
    });
  const columns: Column<MasterRow>[] = fields
    .filter(
      (field) =>
        visible(field.key) &&
        [
          'code',
          'name',
          'value_type',
          'measurement_dimension',
          'is_variant_capable',
          'is_active',
        ].includes(field.key),
    )
    .map((field) => ({
      key: field.key,
      header:
        field.label !== field.key
          ? field.label
          : (field.control?.label ?? field.key.replaceAll('_', ' ')),
      type: 'custom',
      render: (row) =>
        !(field.key in row) ? (
          'Protected'
        ) : ['code', 'name'].includes(field.key) ? (
          <a
            className="janso-link"
            href={attributeLink(root + '/' + row.id, here)}
          >
            {String(row[field.key])}
          </a>
        ) : field.key === 'is_active' ? (
          row[field.key] ? (
            'Active'
          ) : (
            'Inactive'
          )
        ) : typeof row[field.key] === 'boolean' ? (
          row[field.key] ? (
            'Yes'
          ) : (
            'No'
          )
        ) : (
          String(row[field.key] ?? 'Not set')
        ),
    }));
  if (!columns.length)
    columns.push({
      key: 'record',
      header: 'Record',
      type: 'custom',
      render: (row) => (
        <a
          className="janso-link"
          href={attributeLink(root + '/' + row.id, here)}
        >
          View {config.singular}
        </a>
      ),
    });
  return (
    <div className="janso-page">
      <AttributeNavigation
        title={config.title}
        back={query.get('returnTo') ?? '/inventory/attributes'}
        access={access}
      />
      <PageHeader
        title={config.title}
        lede="Maintain reusable attribute masters in the company currently open."
        actions={
          canManage && (
            <a
              className="janso-btn janso-btn--primary"
              href={attributeLink(
                root +
                  '/new' +
                  (query.get('definition_id')
                    ? '?definition_id=' + query.get('definition_id')
                    : ''),
                here,
              )}
            >
              New {config.singular}
            </a>
          )
        }
      />
      {!canManage && <Notice>Read-only access.</Notice>}
      {adjusted && (
        <Notice tone="warning">
          Unavailable search, filter or sort settings were removed.
        </Notice>
      )}
      <AttributeFailure
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
              label: id === 'q' ? 'Search' : id.replaceAll('_', ' '),
              value: id === 'definition_id' ? 'Selected definition' : value,
            }))}
          onRemove={(key) => change(key, '')}
          onClearAll={() =>
            setQuery(
              new URLSearchParams(
                query.has('returnTo')
                  ? { returnTo: query.get('returnTo')! }
                  : {},
              ),
            )
          }
          actions={
            <Button
              variant="ghost"
              disabled={list.loading}
              onClick={list.first}
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
          {allowedFilters.includes('value_type') && visible('value_type') && (
            <Select
              label="Value type"
              placeholder="All types"
              value={query.get('value_type') ?? ''}
              options={valueTypes.map((value) => ({ value, label: value }))}
              onChange={(value) => change('value_type', value)}
            />
          )}
          {allowedFilters.includes('measurement_dimension') &&
            visible('measurement_dimension') && (
              <Select
                label="Measurement dimension"
                placeholder="All dimensions"
                value={query.get('measurement_dimension') ?? ''}
                options={dimensions.map((value) => ({ value, label: value }))}
                onChange={(value) => change('measurement_dimension', value)}
              />
            )}
          {allowedFilters.includes('is_variant_capable') &&
            visible('is_variant_capable') && (
              <Select
                label="Variant eligibility"
                placeholder="All definitions"
                value={query.get('is_variant_capable') ?? ''}
                options={[
                  { value: 'true', label: 'May distinguish variants' },
                  { value: 'false', label: 'Specification only' },
                ]}
                onChange={(value) => change('is_variant_capable', value)}
              />
            )}
          {allowedFilters.includes('definition_id') &&
            visible('definition_id') &&
            access['attribute-definitions'] && (
              <AttributeReference
                company={company}
                label="Filter by definition"
                value={query.get('definition_id')}
                activeOnly={false}
                onChange={(value) => change('definition_id', value ?? '')}
              />
            )}
          <Select
            label="Sort"
            value={sort}
            options={[
              { value: '-id', label: 'Newest first' },
              { value: 'id', label: 'Oldest first' },
              ...['code', 'name'].filter(visible).flatMap((key) => [
                { value: key, label: key + ' A to Z' },
                { value: '-' + key, label: key + ' Z to A' },
              ]),
            ]}
            onChange={(value) => change('sort', value)}
          />
        </FilterBar>
        <DataTable<MasterRow>
          caption={config.title + ' directory'}
          columns={columns}
          rows={
            metadata.failure || list.failure ? [] : (list.data?.items ?? [])
          }
          rowId={(row) => row.id}
          rowLabel={(row) =>
            String(
              (visible('name') && row.name) ||
                (visible('code') && row.code) ||
                config.singular + ' ' + row.id,
            )
          }
          loading={metadata.loading || list.loading}
          emptyTitle={'No ' + config.title.toLowerCase()}
          emptyBody="Change the filters or create the first record if you have manage access."
          rowActions={(row) => [
            {
              id: 'view',
              label: 'View details',
              href: attributeLink(root + '/' + row.id, here),
            },
            ...(canManage &&
            attributeVisible(fields, 'row_version') &&
            attributeEditKeys(config.resource, row).some((key) =>
              attributeWritable(fields, [key]),
            )
              ? [
                  {
                    id: 'edit',
                    label: 'Edit details',
                    href: attributeLink(root + '/' + row.id + '/edit', here),
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
