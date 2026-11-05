'use client';
import { useEffect, useState } from 'react';
import {
  Button,
  Card,
  CardHeader,
  ConfirmDialog,
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
import { useServiceCommand, useServiceList } from '../lib/service-resource';
import {
  canEditPricing,
  pricingBase,
  pricingCommand,
  pricingId,
  pricingLink,
  pricingPurposes,
  pricingReceipt,
  pricingReturn,
  pricingVisible,
  pricingWritable,
  usePricingFields,
} from '../lib/pricing-masters';
import type { PricingAccess } from '../lib/pricing-resources';
import { useAccessDraft } from './AccessCommon';
import {
  PricingCurrency,
  PricingFailure,
  PricingLevelReference,
  PricingMasterExplanation,
  PricingNavigation,
} from './PricingMasterCommon';
export function PricingMasterDirectory({
  company,
  config,
  canManage,
  access,
  initialQuery = '',
}: {
  company: string;
  config: MasterConfig;
  canManage: boolean;
  access: PricingAccess;
  initialQuery?: string;
}) {
  const root = '/masters/' + config.resource,
    initial = new URL(
      pricingReturn(root + '?' + initialQuery, root),
      'https://console.invalid',
    );
  const initialSort = initial.searchParams.get('sort');
  if (initialSort?.includes(','))
    initial.searchParams.set('sort', initialSort.split(',')[0]!);
  const [query, setQuery] = useState(initial.searchParams),
    [adjusted, setAdjusted] = useState(false),
    [confirm, setConfirm] = useState(false),
    [message, setMessage] = useState('');
  const metadata = usePricingFields(company, config.entity),
    fields = metadata.data?.fields ?? [],
    visible = (key: string) => pricingVisible(fields, key);
  const channels = config.resource === 'sales-channels',
    plans = config.resource === 'price-plans',
    filters = new URLSearchParams();
  if (visible('code') && visible('name') && query.get('q'))
    filters.set('q', query.get('q')!);
  for (const key of channels
    ? ['is_active']
    : plans
      ? ['purpose', 'currency', 'price_level_id']
      : [])
    if (
      visible(key) &&
      query.get(key) &&
      (key !== 'purpose' ||
        query.get(key) !== 'PURCHASE' ||
        access.purchaseRead)
    )
      filters.set(key, query.get(key)!);
  const requestedSort = query.get('sort') ?? '-id',
    sort =
      ['id', '-id'].includes(requestedSort) ||
      (requestedSort.includes('code') && visible('code')) ||
      (channels && requestedSort.includes('name') && visible('name'))
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
      'purpose',
      'currency',
      'price_level_id',
    ])
      if (next.has(key) && !allowed.has(key)) next.delete(key);
    if (next.has('sort') && next.get('sort') !== allowed.get('sort'))
      next.delete('sort');
    if (next.toString() !== queryText) {
      setQuery(next);
      setAdjusted(true);
    }
  }, [metadata.data, filterText, queryText]);
  const list = useServiceList<MasterRow>(
    pricingBase(company, config.resource),
    filterText,
    masterRequest,
    (row) => {
      if (!pricingId.test(row.id))
        throw {
          status: 502,
          message: 'The pricing directory could not be verified.',
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
      if (value) next.set(key, value);
      else next.delete(key);
      return next;
    });
  const command = useServiceCommand(pricingCommand, 'pricing setup'),
    guard = useAccessDraft(command.uncertain, command.pending);
  const canBootstrap =
    canManage &&
    config.resource === 'price-levels' &&
    pricingVisible(fields, 'row_version') &&
    pricingWritable(fields, ['code', 'name', 'ordinal', 'is_active']);
  async function bootstrap() {
    if (!canBootstrap || command.pending) return;
    const result = await command.execute<MasterRow>(
      {
        path: pricingBase(company, 'pricing/bootstrap'),
        method: 'POST',
        body: {},
      },
      (row) => pricingReceipt(row, company),
    );
    setConfirm(false);
    if (result) {
      setMessage(
        'Baseline price levels are ready. Existing names were preserved.',
      );
      list.first();
    }
  }
  const columns: Column<MasterRow>[] = fields
    .filter(
      (field) =>
        visible(field.key) &&
        [
          'code',
          'name',
          'ordinal',
          'is_active',
          'purpose',
          'currency',
          'tax_basis',
        ].includes(field.key),
    )
    .map((field) => ({
      key: field.key,
      header:
        field.label !== field.key
          ? field.label
          : (field.control?.label ?? field.key),
      type: 'custom',
      render: (row) =>
        !(field.key in row) ? (
          'Protected'
        ) : ['code', 'name'].includes(field.key) ? (
          <a
            className="janso-link"
            href={pricingLink(root + '/' + row.id, here)}
            onClick={guard.leave}
          >
            {String(row[field.key])}
          </a>
        ) : field.key === 'is_active' ? (
          row.is_active ? (
            'Active'
          ) : (
            'Inactive'
          )
        ) : field.key === 'purpose' ? (
          (pricingPurposes.find((purpose) => purpose.value === row.purpose)
            ?.label ?? String(row.purpose))
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
          href={pricingLink(root + '/' + row.id, here)}
          onClick={guard.leave}
        >
          View {config.singular}
        </a>
      ),
    });
  return (
    <div className="janso-page">
      <PricingNavigation
        title={config.title}
        back={query.get('returnTo') ?? '/inventory/pricing'}
        access={access}
        onLeave={guard.leave}
      />
      <PageHeader
        title={config.title}
        lede="Maintain pricing masters in the company currently open."
        actions={
          canManage && (
            <a
              className="janso-btn janso-btn--primary"
              href={pricingLink(root + '/new', here)}
              onClick={guard.leave}
            >
              New {config.singular}
            </a>
          )
        }
      />
      <PricingMasterExplanation resource={config.resource} />
      {!canManage && <Notice>Read-only access.</Notice>}
      {adjusted && (
        <Notice tone="warning">
          Unavailable search, filter or sort settings were removed.
        </Notice>
      )}
      {message && <Notice tone="success">{message}</Notice>}
      <PricingFailure
        failure={metadata.failure ?? list.failure}
        retry={() => {
          metadata.refresh();
          list.first();
        }}
      />
      <PricingFailure failure={command.failure} uncertain={command.uncertain} />
      {canBootstrap && (
        <div className="janso-page-navigation">
          <Button
            type="button"
            disabled={command.blocked}
            onClick={() => setConfirm(true)}
          >
            Set up baseline price levels
          </Button>
          {command.uncertain && (
            <Button
              type="button"
              disabled={command.pending}
              onClick={bootstrap}
            >
              Retry same setup
            </Button>
          )}
          {command.failure && !command.uncertain && (
            <Button
              type="button"
              onClick={() => {
                command.clear();
                list.first();
              }}
            >
              Reload and review
            </Button>
          )}
        </div>
      )}
      <Card>
        <CardHeader title={config.title + ' directory'} />
        <FilterBar
          applied={[...filters]
            .filter(([key]) => key !== 'sort')
            .map(([id, value]) => ({
              id,
              label: id === 'q' ? 'Search' : id.replaceAll('_', ' '),
              value: id === 'price_level_id' ? 'Selected level' : value,
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
              disabled={list.loading || command.pending}
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
          {channels && visible('is_active') && (
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
          {plans && visible('purpose') && (
            <Select
              label="Purpose"
              placeholder="All purposes"
              value={query.get('purpose') ?? ''}
              options={pricingPurposes.filter(
                (purpose) =>
                  purpose.value !== 'PURCHASE' || access.purchaseRead,
              )}
              onChange={(value) => change('purpose', value)}
            />
          )}
          {plans && visible('currency') && (
            <PricingCurrency
              company={company}
              value={query.get('currency')}
              onChange={(value) => change('currency', value ?? '')}
            />
          )}
          {plans && visible('price_level_id') && access['price-levels'] && (
            <PricingLevelReference
              company={company}
              label="Filter by sales level"
              activeOnly={false}
              value={query.get('price_level_id')}
              onChange={(value) => change('price_level_id', value ?? '')}
            />
          )}
          <Select
            label="Sort"
            value={sort}
            options={[
              { value: '-id', label: 'Newest first' },
              { value: 'id', label: 'Oldest first' },
              ...(visible('code')
                ? [
                    { value: 'code', label: 'Code A to Z' },
                    { value: '-code', label: 'Code Z to A' },
                  ]
                : []),
              ...(channels && visible('name')
                ? [
                    { value: 'name', label: 'Name A to Z' },
                    { value: '-name', label: 'Name Z to A' },
                  ]
                : []),
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
          emptyBody="Change the filters or create a record with manage access."
          rowActions={(row) => [
            {
              id: 'view',
              label: 'View details',
              href: pricingLink(root + '/' + row.id, here),
              disabledReason: command.blocked
                ? 'Finish or recover setup first.'
                : undefined,
            },
            ...(canManage && canEditPricing(config, fields, row, access)
              ? [
                  {
                    id: 'edit',
                    label: 'Edit details',
                    href: pricingLink(root + '/' + row.id + '/edit', here),
                    disabledReason: command.blocked
                      ? 'Finish or recover setup first.'
                      : undefined,
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
      <ConfirmDialog
        open={confirm}
        title="Set up baseline price levels?"
        confirmLabel="Set up levels"
        onCancel={() => setConfirm(false)}
        onConfirm={bootstrap}
      >
        Create PRICE1 and the additional baseline levels allowed by this
        company’s enabled features. Existing level names are preserved. No rates
        or amounts are created.
      </ConfirmDialog>
      {guard.confirmation}
    </div>
  );
}
