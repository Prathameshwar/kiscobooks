'use client';
import { useState } from 'react';
import { Badge, Card, DataTable, FilterBar, Notice, PageHeader, PageNavigation, Pager, Select, TableSearch, SEARCH_MIN, SEARCH_MAX, type Column } from '@janso/ui';
import type { components } from '@janso/api-client/catalog';
import { masterRequest } from '../lib/catalog-master-api';
import { catalogBack, catalogId, catalogLink } from '../lib/product-classification';
import { useServiceList, useServiceRead } from '../lib/service-resource';
import { simpleRoot, verifySimpleFields, type SimpleFields } from '../lib/simple-products';
import type { ClassificationAccess } from '../lib/product-classification-resources';
import { ProductCatalogFailure } from './ProductCatalogCommon';
import { ProductInventoryActions } from './ProductInventoryActions';
import { ProductCreationCard } from './ProductCreationCard';

type Row = components['schemas']['SimpleProductListItem'];
export function SimpleProductDirectory({
  company,
  access,
  initialQuery = '',
  canImport = false,
  canManage = false,
}: {
  company: string;
  access: ClassificationAccess;
  initialQuery?: string;
  canImport?: boolean;
  canManage?: boolean;
}) {
  const [query, setQuery] = useState(new URLSearchParams(initialQuery));
  const metadata = useServiceRead<SimpleFields>(
    `/v1/companies/${company}/products/field-set`,
    masterRequest,
    (value) => verifySimpleFields(value, company),
  );
  const visible = (key: string) =>
    metadata.data?.fields.some((field) => field.key === key && field.visible);
  const filters = new URLSearchParams();
  const search = query.get('q')?.trim() ?? '';
  if (search.length >= SEARCH_MIN && search.length <= SEARCH_MAX && visible('code') && visible('name'))
    filters.set('q', search);
  if (visible('status') && ['DRAFT', 'ACTIVE', 'DISCONTINUED'].includes(query.get('status') ?? ''))
    filters.set('status', query.get('status')!);
  if (visible('code') && (query.get('code') || query.get('sku')))
    filters.set('code', (query.get('code') ?? query.get('sku'))!);
  if (
    visible('base_unit_id') &&
    catalogId.test(query.get('base_unit_id') ?? '')
  )
    filters.set('base_unit_id', query.get('base_unit_id')!);
  for (const key of ['sellable', 'purchasable'])
    if (visible(key) && ['true', 'false'].includes(query.get(key) ?? ''))
      filters.set(key, query.get(key)!);
  if (query.get('custom_filters'))
    filters.set('custom_filters', query.get('custom_filters')!);
  const sort = query.get('sort')?.replace(/sku/g, 'code') ?? 'code';
  filters.set(
    'sort',
    ['id', '-id', 'code', '-code', 'name', '-name'].includes(sort) &&
      (['id', '-id'].includes(sort) || visible(sort.replace(/^-/, '')))
      ? sort
      : 'id',
  );
  const list = useServiceList<Row>(
    `/v1/companies/${company}/products`,
    filters.toString(),
    masterRequest,
    (row) => {
      if (!catalogId.test(row.id))
        throw {
          status: 502,
          message: 'The product list could not be verified.',
        };
    },
    !!metadata.data,
  );
  const change = (key: string, value: string) => {
    const next = new URLSearchParams(query);
    if (value) next.set(key, value);
    else next.delete(key);
    next.delete('cursor');
    setQuery(next);
    window.history.replaceState(
      window.history.state,
      '',
      simpleRoot + (next.size ? '?' + next : ''),
    );
  };
  const here = simpleRoot + (query.size ? '?' + query : '');
  const failure = metadata.failure ?? list.failure;
  const loading = metadata.loading || list.loading;
  const filtered = [...filters.keys()].some((key) => key !== 'sort');
  const clearFilters = () => {
    const next = new URLSearchParams();
    for (const key of ['sort', 'returnTo']) {
      const value = query.get(key);
      if (value) next.set(key, value);
    }
    setQuery(next);
    window.history.replaceState(window.history.state, '', simpleRoot + (next.size ? '?' + next : ''));
  };
  const columns: Column<Row>[] = [
    ...(visible('code')
      ? [{ key: 'code', header: 'Product code', type: 'text' as const }]
      : []),
    ...(visible('name')
      ? [
          {
            key: 'name',
            header: 'Product name',
            type: 'custom' as const,
            render: (row: Row) => row.name ?? 'Protected product',
          },
        ]
      : []),
    ...(visible('status') ? [{
      key: 'status',
      header: 'Status',
      type: 'custom' as const,
      render: (row: Row) => (
        <Badge>
          {row.status === 'ACTIVE'
            ? 'Active'
            : row.status === 'DRAFT'
              ? 'Draft'
              : row.status === 'DISCONTINUED'
                ? 'Discontinued'
                : 'Protected'}
        </Badge>
      ),
    }] : []),
    {
      key: 'actions', header: 'Actions', hideHeader: true, align: 'end', type: 'custom',
      render: row => <ProductInventoryActions company={company} row={{ ...row, name: row.name ?? undefined, code: row.code ?? undefined }} family={false}
        access={access} items={[]} returnTo={here} />,
    },
  ];
  return (
    <section className="janso-page">
      <PageNavigation
        back={{
          href: catalogBack(
            query.get('returnTo') ?? undefined,
            '/inventory/products',
          ),
          label: 'products and classification',
        }}
      />
      <PageHeader
        title="Products"
        lede="Browse the products and services you buy or sell."
        actions={
          <div className="janso-form-actions">
            {canImport && (
              <a
                className="janso-btn janso-btn--secondary"
                href={catalogLink(simpleRoot + '/import', here)}
              >
                Import products
              </a>
            )}
          </div>
        }
      />
      <ProductCreationCard company={company} href={catalogLink('/masters/items/new', here)} canCreate={access.createProduct} />
      {(query.has('family_id') || query.has('cursor')) && (
        <Notice>Product filters have been adjusted for single products.</Notice>
      )}
      <ProductCatalogFailure
        failure={failure}
        retry={() => {
          metadata.refresh();
          list.first();
        }}
      />
      <Card>
        <FilterBar>
            {visible('code') && visible('name') && (
              <TableSearch
                value={query.get('q') ?? ''}
                onChange={(value) => change('q', value)}
                placeholder="Search products"
              />
            )}
            {visible('status') && <Select
              label="Status"
              value={query.get('status') ?? ''}
              options={[
                { value: '', label: 'All statuses' },
                { value: 'DRAFT', label: 'Draft' },
                { value: 'ACTIVE', label: 'Active' },
                { value: 'DISCONTINUED', label: 'Discontinued' },
              ]}
              onChange={(value) => change('status', value)}
            />}
            <Select
              label="Sort by"
              value={filters.get('sort') ?? 'id'}
              options={[
                ...(visible('code')
                  ? [
                      { value: 'code', label: 'Product code: A to Z' },
                      { value: '-code', label: 'Product code: Z to A' },
                    ]
                  : []),
                ...(visible('name')
                  ? [
                      { value: 'name', label: 'Product name: A to Z' },
                      { value: '-name', label: 'Product name: Z to A' },
                    ]
                  : []),
                { value: '-id', label: 'Newest first' },
                { value: 'id', label: 'Oldest first' },
              ]}
              onChange={(value) => change('sort', value)}
            />
        </FilterBar>
        {!failure && (loading ? (
          <p role="status">Loading products…</p>
        ) : (
          <DataTable
            caption="Products"
            rows={list.data?.items ?? []}
            columns={columns}
            rowId={(row) => row.id}
            rowLabel={(row) => row.name ?? row.code ?? 'Product'}
            filtered={filtered}
            onClearFilters={clearFilters}
            emptyTitle={filtered ? 'No matching products' : 'No products yet'}
            emptyBody={filtered
              ? 'Try another search or clear the filters to see more products.'
              : 'No products are available in this company.'}
          />
        ))}
        {!loading && !failure && <Pager
          count={list.data?.items.length ?? 0}
          limit={list.limit}
          hasPrevious={list.hasPrevious}
          hasNext={!!list.data?.page.has_more}
          onPrevious={list.previous}
          onNext={list.next}
          onLimitChange={list.setLimit}
          busy={list.loading}
          noun="product"
        />}
      </Card>
    </section>
  );
}
