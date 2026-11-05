'use client';
import { ProductInventoryActions } from './ProductInventoryActions';
import { catalogRelatedLinks } from '../lib/master-navigation';
import { useEffect, useState } from 'react';
import { Badge, Card, CardBody, CardHeader, DataTable, Disclosure, FilterBar, Notice, PageHeader, Pager, Select, TableSearch, asErrorStatus, type Column } from '@janso/ui';
import type { MasterConfig, MasterRow } from '../lib/catalog-masters';
import { masterRequest } from '../lib/catalog-master-api';
import { useServiceList } from '../lib/service-resource';
import { classificationDefinitions, type ClassificationResource, type ClassificationAccess } from '../lib/product-classification-resources';
import { catalogBase, catalogBack, catalogId, catalogLink, catalogVisible, useCatalogFields } from '../lib/product-classification';
import { allowedClassificationRequest } from '../lib/product-classification-policy';
import { ProductCatalogFailure, ProductCatalogNavigation, ProductCatalogReference } from './ProductCatalogCommon';
import { ProductCreationCard } from './ProductCreationCard';

export function ProductCatalogDirectory({
  company,
  config,
  canManage,
  access,
  initialQuery = '',
  canImport = false,
}: {
  company: string;
  config: MasterConfig;
  canManage: boolean;
  access: ClassificationAccess;
  initialQuery?: string;
  canImport?: boolean;
}) {
  const resource = config.resource as ClassificationResource,
    definition = classificationDefinitions[resource],
    root = '/masters/' + resource,
    product = resource === 'items' || resource === 'product-families';
  const [query, setQuery] = useState(
      () =>
        new URLSearchParams(
          new URL(
            catalogBack(root + '?' + initialQuery, root),
            'https://console.invalid',
          ).search,
        ),
    ),
    [adjusted, setAdjusted] = useState(false);
  const metadata = useCatalogFields(company, config.entity),
    fields = metadata.data?.fields ?? [],
    visible = (key: string) => catalogVisible(fields, key),
    identity = resource === 'items' ? 'sku' : 'code';
  const filters = new URLSearchParams();
  for (const [key, value] of query) {
    const field = key;
    if (
      key === 'q'
        ? visible(identity) && visible('name')
        : key === 'sort'
          ? visible(value.replace(/^-/, '')) || ['id', '-id'].includes(value)
          : visible(field)
    ) {
      if (
        allowedClassificationRequest(
          'GET',
          catalogBase(company, resource) +
            '?' +
            new URLSearchParams({ [key]: value }),
        ) === true
      )
        filters.set(key, value);
    }
  }
  if (!filters.has('sort')) filters.set('sort', '-id');
  const filterText = filters.toString(),
    queryText = query.toString(),
    here = root + (query.size ? '?' + query : '');
  useEffect(() => {
    if (!metadata.data) return;
    const next = new URLSearchParams(queryText),
      allowed = new URLSearchParams(filterText);
    for (const key of [...next.keys()])
      if (key !== 'returnTo' && !allowed.has(key)) next.delete(key);
    if (next.toString() !== queryText) {
      setQuery(next);
      setAdjusted(true);
    }
  }, [metadata.data, queryText, filterText]);
  useEffect(() => {
    window.history.replaceState(null, '', here);
  }, [here]);
  const list = useServiceList<MasterRow>(
    catalogBase(company, resource),
    filterText,
    masterRequest,
    (row) => {
      if (
        !catalogId.test(row.id) ||
        (row.company_id != null && row.company_id !== company)
      )
        throw {
          status: 502,
          message: 'The directory record could not be verified.',
        };
    },
    !!metadata.data && !metadata.failure,
  );
  function change(key: string, value: string) {
    setQuery((current) => {
      const next = new URLSearchParams(current);
      value ? next.set(key, value) : next.delete(key);
      return next;
    });
  }
  const failure = metadata.failure ?? list.failure,
    loading = metadata.loading || list.loading || (!list.data && !list.failure);
  const rowActions = (row: MasterRow) => [
    ...(!product ? [
    {
      id: 'view',
      label: 'View details',
      href: catalogLink(root + '/' + row.id, here),
    },
    ...(canManage &&
    (!product || ['DRAFT', 'ACTIVE'].includes(String(row.status)))
      ? [
          {
            id: 'edit',
            label: 'Edit details',
            href: catalogLink(root + '/' + row.id + '/edit', here),
          },
        ]
      : []),
    ] : []),
    ...catalogRelatedLinks(resource, row, visible, access, here),
  ];
  const columns: Column<MasterRow>[] = [
    identity,
    'name',
    ...(product
      ? [
          'status',
          ...(resource === 'product-families'
            ? ['kind', 'structure_mode']
            : ['sellable', 'purchasable']),
        ]
      : ['is_active']),
  ]
    .filter(visible)
    .map((key) => ({
      key,
      header:
        key === 'is_active' || key === 'status'
          ? 'Status'
          : key === 'sku'
            ? 'SKU'
            : key
                .replaceAll('_', ' ')
                .replace(/^./, (letter) => letter.toUpperCase()),
      type: 'custom',
      render: (row) =>
        !(key in row) ? (
          'Protected'
        ) : [identity, 'name'].includes(key) ? (product ? String(row[key]) : (
          <a
            className="janso-link"
            href={catalogLink(root + '/' + row.id, here)}
          >
            {String(row[key])}
          </a>
        )) : key === 'is_active' || key === 'status' ? (
          <Badge
            tone={
              row[key] === true || row[key] === 'ACTIVE'
                ? 'success'
                : row[key] === 'DRAFT'
                  ? 'info'
                  : 'neutral'
            }
          >
            {key === 'is_active'
              ? row[key]
                ? 'Active'
                : 'Inactive'
              : String(row[key]).slice(0, 1) +
                String(row[key]).slice(1).toLowerCase()}
          </Badge>
        ) : typeof row[key] === 'boolean' ? (
          row[key] ? (
            'Yes'
          ) : (
            'No'
          )
        ) : (
          String(row[key]).replaceAll('_', ' ').toLowerCase()
        ),
    }));
  if (!columns.length)
    columns.push({
      key: 'record',
      header: 'Record',
      type: 'custom',
      render: (row) => product ? 'Protected product' : (
        <a className="janso-link" href={catalogLink(root + '/' + row.id, here)}>
          View record
        </a>
      ),
    });
  if (product)
    columns.push({
      key: 'actions',
      header: 'Actions',
      hideHeader: true,
      align: 'end',
      type: 'custom',
      render: (row) => (
        <ProductInventoryActions
          company={company}
          row={row}
          family={resource === 'product-families'}
          access={access}
          items={rowActions(row)}
          returnTo={here}
        />
      ),
    });
  const create = !product && canManage;
  const newHref = catalogLink(root + '/new', here);
  const references: Record<string, [string, string]> = {
    family_id: ['Product family', 'product-families'],
    base_unit_id: ['Base unit', 'units'],
    brand_id: ['Brand', 'brands'],
    scheme_id: ['Category scheme', 'category-schemes'],
    manufacturer_id: ['Manufacturer', 'manufacturers'],
    parent_brand_id: ['Parent brand', 'brands'],
    product_type_revision_id: [
      'Published product type',
      'product-type-revisions',
    ],
  };
  const referenceKeys = Object.keys(references).filter(
    (key) =>
      (definition.filters as readonly string[]).includes(key) && visible(key),
  );
  const clearFilters = () =>
    setQuery(
      new URLSearchParams(
        query.get('returnTo') ? { returnTo: query.get('returnTo')! } : {},
      ),
    );
  const filtered = [...filters.keys()].some((key) => key !== 'sort');
  return (
    <div className="janso-page">
      <ProductCatalogNavigation
        resource={resource}
        title={definition.title}
        back={query.get('returnTo') ?? '/inventory/products'}
        access={access}
      />
      <PageHeader
        title={definition.title}
        lede={definition.description}
        actions={
          create || (product && canImport) ? (
            <div className="janso-form-actions">
              {create && (
                <a className="janso-btn janso-btn--primary" href={newHref}>
                  {`New ${definition.singular}`}
                </a>
              )}
              {product &&
                (canImport ? (
                  <a
                    className="janso-link"
                    href={catalogLink('/masters/items/import', here)}
                  >
                    Import products
                  </a>
                ) : (
                  <span
                    className="janso-link"
                    role="link"
                    aria-disabled="true"
                    title="Product import access is required for this company."
                  >
                    Import products
                  </span>
                ))}
            </div>
          ) : undefined
        }
      />
      {product && <ProductCreationCard company={company} href={catalogLink('/masters/items/new', here)} canCreate={access.createProduct} />}
      {!canManage && <Notice>Read-only access.</Notice>}
      {adjusted && (
        <Notice tone="warning">
          Unavailable search, filter or sort settings were removed.
        </Notice>
      )}
      <ProductCatalogFailure
        failure={metadata.failure}
        retry={() => {
          metadata.refresh();
          list.first();
        }}
      />
      {!metadata.failure && (
        <Card>
          <CardHeader title={definition.title + ' directory'} />
          <FilterBar
            applied={[...filters]
              .filter(([key]) => key !== 'sort')
              .map(([id, value]) => ({
                id,
                label: id === 'q' ? 'Search' : id.replaceAll('_', ' '),
                value: value.length === 36 ? 'Selected record' : value,
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
          >
            {visible(identity) && visible('name') && (
              <TableSearch
                label={'Search ' + definition.title.toLowerCase()}
                placeholder={
                  resource === 'items'
                    ? 'Search by product name or SKU'
                    : 'Search by name or code'
                }
                value={query.get('q') ?? ''}
                onChange={(value) => change('q', value)}
              />
            )}
            {visible(product ? 'status' : 'is_active') && (
              <Select
                label="Status"
                value={query.get(product ? 'status' : 'is_active') ?? ''}
                placeholder="All statuses"
                options={
                  product
                    ? ['DRAFT', 'ACTIVE', 'DISCONTINUED'].map((value) => ({
                        value,
                        label: value[0] + value.slice(1).toLowerCase(),
                      }))
                    : [
                        { value: 'true', label: 'Active' },
                        { value: 'false', label: 'Inactive' },
                      ]
                }
                onChange={(value) =>
                  change(product ? 'status' : 'is_active', value)
                }
              />
            )}
            {visible('kind') &&
              (definition.filters as readonly string[]).includes('kind') && (
                <Select
                  label="Kind"
                  value={query.get('kind') ?? ''}
                  placeholder="All kinds"
                  options={[
                    'GOODS',
                    'SERVICE',
                    ...(resource === 'product-types' ? ['BOTH'] : []),
                  ].map((value) => ({ value, label: value.toLowerCase() }))}
                  onChange={(value) => change('kind', value)}
                />
              )}
            <Select
              label="Sort by"
              value={filters.get('sort')!}
              options={[
                { value: '-id', label: 'Newest first' },
                { value: 'id', label: 'Oldest first' },
                ...(visible(identity)
                  ? [
                      { value: identity, label: 'Code A–Z' },
                      { value: '-' + identity, label: 'Code Z–A' },
                    ]
                  : []),
                ...(visible('name')
                  ? [
                      { value: 'name', label: 'Name A–Z' },
                      { value: '-name', label: 'Name Z–A' },
                    ]
                  : []),
              ]}
              onChange={(value) => change('sort', value)}
            />
          </FilterBar>
          {referenceKeys.length > 0 && (
            <CardBody>
              <Disclosure
                summary="More filters"
                defaultOpen={referenceKeys.some((key) => filters.has(key))}
              >
                <div className="janso-form-grid">
                  {referenceKeys.map((key) => (
                    <ProductCatalogReference
                      key={key}
                      company={company}
                      source={references[key]![1]}
                      label={references[key]![0]}
                      value={query.get(key)}
                      access={access}
                      onChange={(value) => change(key, value ?? '')}
                    />
                  ))}
                </div>
              </Disclosure>
            </CardBody>
          )}
          <DataTable
            caption={definition.title}
            rows={failure ? [] : (list.data?.items ?? [])}
            rowId={(row) => row.id}
            rowLabel={(row) => row.name ?? row.code ?? 'Record'}
            columns={columns}
            loading={loading}
            error={list.failure ? asErrorStatus(list.failure.status) : null}
            errorDetail={list.failure?.message}
            onRetry={list.first}
            filtered={filtered}
            onClearFilters={clearFilters}
            emptyTitle={
              filtered
                ? 'No matching ' + definition.title.toLowerCase()
                : 'No ' + definition.title.toLowerCase()
            }
            emptyBody={
              filtered
                ? 'Try another search or clear the filters to see more records.'
                : create
                  ? 'Create your first record to get started.'
                  : 'No records are available in this company.'
            }
            emptyAction={
              create && !filtered && !failure ? (
                <a className="janso-btn janso-btn--primary" href={newHref}>
                  Create first record
                </a>
              ) : undefined
            }
            rowActions={product ? undefined : rowActions}
          />
          {!loading && !failure && (
            <Pager
              count={loading || failure ? 0 : (list.data?.items.length ?? 0)}
              from={list.hasPrevious ? null : 1}
              limit={list.limit}
              hasPrevious={list.hasPrevious}
              hasNext={!!list.data?.page.has_more}
              onPrevious={list.previous}
              onNext={list.next}
              onLimitChange={list.setLimit}
              busy={loading || !!failure}
              noun="record"
            />
          )}
        </Card>
      )}
    </div>
  );
}
