'use client';
import { inventoryBreadcrumbs } from '../lib/inventory-navigation';
import { useCallback, useEffect, useState } from 'react';
import {
  Button,
  Notice,
  PageNavigation,
  SearchSelect,
  type SearchSelectLoader,
  type SearchSelectOption,
} from '@janso/ui';
import { masterRequest, assertMaster } from '../lib/catalog-master-api';
import { companyCall } from '../lib/company-api';
import { requestFailure, type RequestFailure } from '../lib/service-call';
import { useServiceRead, type ServicePage } from '../lib/service-resource';
import type { MasterRow } from '../lib/catalog-masters';
import { pricingBase, pricingId, pricingReturn } from '../lib/pricing-masters';
import { pricingResources, type PricingAccess } from '../lib/pricing-resources';
import { IdentifierFailure } from './UnitsIdentifiersCommon';
export { IdentifierField as PricingField } from './UnitsIdentifiersCommon';
export function PricingFailure({
  failure,
  retry,
  uncertain = false,
}: {
  failure: RequestFailure | null;
  retry?: () => void;
  uncertain?: boolean;
}) {
  return uncertain ? (
    <Notice tone="danger">
      The save result could not be confirmed. Your values are retained. Retry
      the same action to recover its receipt.
    </Notice>
  ) : (
    <IdentifierFailure failure={failure} retry={retry} />
  );
}
const titles = {
  'sales-channels': 'Sales channels',
  'price-levels': 'Price levels',
  'price-plans': 'Price plans',
};
export function PricingNavigation({
  title,
  back,
  access,
  onLeave,
}: {
  title: string;
  back?: string;
  access: PricingAccess;
  onLeave?: React.MouseEventHandler<HTMLAnchorElement>;
}) {
  return (
    <>
      <PageNavigation
        back={{ href: pricingReturn(back, '/inventory/pricing'), label: 'previous page' }}
        breadcrumbs={inventoryBreadcrumbs('pricing', title)}
        onNavigate={onLeave}
      />
      <nav className="janso-page-navigation" aria-label="Pricing masters">
        {pricingResources
          .filter((resource) => access[resource])
          .map((resource) => (
            <a
              key={resource}
              className="janso-link"
              href={'/masters/' + resource}
              onClick={onLeave}
            >
              {titles[resource]}
            </a>
          ))}
      </nav>
    </>
  );
}
export function PricingLevelReference({
  company,
  label = 'Sales price level',
  value,
  onChange,
  disabled,
  error,
  activeOnly = true,
  required = false,
}: {
  company: string;
  label?: string;
  value: string | null;
  onChange: (value: string | null) => void;
  disabled?: boolean;
  error?: string;
  activeOnly?: boolean;
  required?: boolean;
}) {
  const [selected, setSelected] = useState<SearchSelectOption | null>(null),
    [problem, setProblem] = useState('');
  const load = useCallback<SearchSelectLoader>(
    async ({ q, cursor, signal }) => {
      const params = new URLSearchParams({ limit: '50' });
      if (q.trim().length >= 2) params.set('q', q.trim());
      if (cursor) params.set('cursor', cursor);
      const result = await masterRequest<ServicePage<MasterRow>>({
        path: pricingBase(company, 'price-levels') + '?' + params,
        signal,
      });
      if (
        !Array.isArray(result.items) ||
        !result.page ||
        result.items.some((row) => !pricingId.test(row.id))
      )
        throw {
          status: 502,
          message: 'Price level choices could not be verified.',
        };
      return {
        items: result.items
          .filter((row) => !activeOnly || row.is_active === true)
          .map((row) => ({
            id: row.id,
            label: row.name ?? row.code ?? 'Protected price level',
            meta: row.code,
            disabled:
              (!row.name && !row.code) ||
              (activeOnly && row.is_active !== true),
          })),
        nextCursor: result.page.has_more ? result.page.next_cursor : null,
      };
    },
    [company, activeOnly],
  );
  useEffect(() => {
    const controller = new AbortController();
    setSelected(null);
    setProblem('');
    if (value)
      masterRequest<MasterRow>({
        path: pricingBase(company, 'price-levels/' + value),
        signal: controller.signal,
      })
        .then((row) => {
          if (controller.signal.aborted) return;
          assertMaster(row, company, value);
          setSelected({
            id: row.id,
            label: row.name ?? row.code ?? 'Protected price level',
            meta: row.code,
          });
        })
        .catch((error) => {
          if (!controller.signal.aborted)
            setProblem(requestFailure(error, 'price level service').message);
        });
    return () => controller.abort();
  }, [company, value]);
  return (
    <SearchSelect
      label={label}
      name="price_level_id"
      value={value}
      selected={
        selected ??
        (value
          ? {
              id: value,
              label: problem
                ? 'Price level unavailable'
                : 'Loading price level…',
              disabled: true,
            }
          : null)
      }
      loadOptions={load}
      minQueryLength={0}
      scopeKey={company + ':pricing-levels:' + activeOnly}
      disabled={disabled}
      clearable={!required}
      required={required}
      error={error ?? (problem || undefined)}
      hint="Search by code or name in the current company."
      onChange={(id, option) => {
        setSelected(option);
        setProblem('');
        onChange(id);
      }}
    />
  );
}
export function PricingLevelLabel({
  company,
  id,
}: {
  company: string;
  id: string;
}) {
  const read = useServiceRead<MasterRow>(
    pricingId.test(id) ? pricingBase(company, 'price-levels/' + id) : undefined,
    masterRequest,
    (row) => assertMaster(row, company, id),
  );
  return (
    <>
      {read.data?.name ??
        read.data?.code ??
        (read.loading
          ? 'Loading price level…'
          : 'Price level label unavailable')}
    </>
  );
}
export function PricingCurrency({
  company,
  value,
  onChange,
  disabled,
  required = false,
  error,
}: {
  company: string;
  value: string | null;
  onChange: (value: string | null) => void;
  disabled?: boolean;
  required?: boolean;
  error?: string;
}) {
  const [options, setOptions] = useState<SearchSelectOption[]>([]),
    [failure, setFailure] = useState(''),
    [loading, setLoading] = useState(true),
    [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setOptions([]);
    setFailure('');
    setLoading(true);
    companyCall<{ code: string; name: string }[]>(
      'identity',
      '/v1/reference/currencies',
      { signal: controller.signal },
    )
      .then((rows) => {
        if (controller.signal.aborted) return;
        if (
          !Array.isArray(rows) ||
          rows.some(
            (row) =>
              !/^[A-Z]{3}$/.test(row.code) || typeof row.name !== 'string',
          )
        )
          throw {
            status: 502,
            message: 'Currency choices could not be verified.',
          };
        setOptions(
          rows.map((row) => ({
            id: row.code,
            label: row.name,
            meta: row.code,
          })),
        );
        setLoading(false);
      })
      .catch((error) => {
        if (!controller.signal.aborted) {
          setFailure(requestFailure(error, 'currency service').message);
          setLoading(false);
        }
      });
    return () => controller.abort();
  }, [company, revision]);
  return (
    <div className="janso-flow">
      <SearchSelect
        label="Currency"
        name="currency"
        value={value}
        selected={
          options.find((option) => option.id === value) ??
          (value ? { id: value, label: value } : null)
        }
        options={options}
        scopeKey={company + ':pricing-currency'}
        required={required}
        disabled={disabled || loading || !!failure}
        clearable={!required}
        error={error ?? (failure || undefined)}
        hint={
          loading
            ? 'Loading currencies…'
            : 'Foreign currencies require the company’s multi-currency feature and currency allowance.'
        }
        onChange={(value) => onChange(value)}
      />
      {failure && (
        <Button
          type="button"
          variant="ghost"
          onClick={() => setRevision((value) => value + 1)}
        >
          Retry currency choices
        </Button>
      )}
    </div>
  );
}
export function PricingMasterExplanation({ resource }: { resource: string }) {
  return (
    <Notice>
      {resource === 'price-plans'
        ? 'A price plan is a book for sale, purchase or reference retail prices. Purpose, sales level, currency and tax basis are fixed after creation. Item rates are maintained separately.'
        : resource === 'price-levels'
          ? 'Baseline levels are created through setup. Rename them as needed. Additional levels use numbers 4–64 and require multiple price levels to be enabled. The baseline and referenced levels cannot be retired.'
          : 'Channels classify sales, such as retail or wholesale. A channel referenced by a price series cannot be renamed or deactivated.'}
    </Notice>
  );
}
