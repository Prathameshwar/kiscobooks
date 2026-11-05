'use client';
import { inventoryBreadcrumbs } from '../lib/inventory-navigation';
import { useCallback, useEffect, useRef, useState } from 'react';
import { PageNavigation, SearchSelect, Select, TextField, type SearchSelectLoader, type SearchSelectOption } from '@janso/ui';
import { assertMaster, masterRequest } from '../lib/catalog-master-api';
import type { MasterField, MasterRow } from '../lib/catalog-masters';
import { requestFailure } from '../lib/service-call';
import { useServiceRead, type ServicePage } from '../lib/service-resource';
import { attributeBase, attributeId, attributeLabel, attributeReturn } from '../lib/attribute-masters';
import { attributeResources, type AttributeAccess } from '../lib/attribute-resources';
import { IdentifierField } from './UnitsIdentifiersCommon';
import { masterLink, masterReferencePath } from '../lib/master-navigation';
export { IdentifierFailure as AttributeFailure } from './UnitsIdentifiersCommon';
export function AttributeReferenceLabel({
  company,
  resource,
  id,
  returnTo,
  onLeave,
}: {
  company: string;
  resource: 'attribute-definitions' | 'units';
  id: string;
  returnTo?: string;
  onLeave?: React.MouseEventHandler<HTMLAnchorElement>;
}) {
  const record = useServiceRead<MasterRow>(
    attributeBase(company, resource + '/' + id),
    masterRequest,
    (row) => assertMaster(row, company, id),
  );
  const path =
    record.data && !record.failure ? masterReferencePath(resource, id) : null;
  if (path && returnTo)
    return (
      <a
        className="janso-link"
        href={masterLink(path, returnTo)}
        onClick={onLeave}
      >
        {attributeLabel(record.data!)}
      </a>
    );
  return (
    <span>
      {record.data
        ? attributeLabel(record.data)
        : record.loading
          ? 'Loading reference...'
          : id + ' (label unavailable)'}
    </span>
  );
}
export function AttributeField({
  company,
  field,
  value,
  onChange,
  disabled,
  error,
}: {
  company: string;
  field: MasterField;
  value: unknown;
  onChange: (value: unknown) => void;
  disabled?: boolean;
  error?: string;
}) {
  if (
    !field.visible ||
    field.conditional_access ||
    field.source !== 'native' ||
    !field.control
  )
    return null;
  const common = {
    label: field.label !== field.key ? field.label : field.control.label,
    name: field.key,
    disabled: disabled || !field.writable,
    required: field.required,
    error,
  };
  if (field.key === 'measurement_dimension')
    return (
      <Select
        {...common}
        placeholder="No measurement unit"
        value={String(value ?? '')}
        options={field.control.choices ?? []}
        onChange={onChange}
        hint="Choose a measurement dimension only for numeric values."
      />
    );
  if (field.control.kind === 'date')
    return (
      <TextField
        {...common}
        type="date"
        min="1000-01-01"
        max="9999-12-31"
        value={String(value ?? '')}
        onChange={(event) => onChange(event.target.value)}
      />
    );
  if (field.key === 'value_boolean')
    return (
      <Select
        {...common}
        required
        placeholder="Choose yes or no"
        value={typeof value === 'boolean' ? String(value) : ''}
        options={[
          { value: 'true', label: 'Yes' },
          { value: 'false', label: 'No' },
        ]}
        onChange={(value) => onChange(value === '' ? null : value === 'true')}
      />
    );
  if (['value_integer', 'value_decimal'].includes(field.key))
    return (
      <TextField
        {...common}
        required
        maxLength={field.control.max_length ?? undefined}
        inputMode={field.key === 'value_decimal' ? 'decimal' : 'text'}
        value={String(value ?? '')}
        hint="Enter the exact value; it will be saved without rounding."
        onChange={(event) => onChange(event.target.value)}
      />
    );
  return (
    <IdentifierField
      company={company}
      field={field}
      value={value}
      onChange={onChange}
      disabled={disabled}
      error={error}
    />
  );
}
export function AttributeNavigation({
  title,
  back,
  access,
  onLeave,
}: {
  title: string;
  back?: string;
  access: AttributeAccess;
  onLeave?: React.MouseEventHandler<HTMLAnchorElement>;
}) {
  return (
    <>
      <PageNavigation
        back={{ href: attributeReturn(back, '/inventory/attributes'), label: 'previous page' }}
        onNavigate={onLeave}
        breadcrumbs={inventoryBreadcrumbs('attributes', title)}
      />
      <nav className="janso-page-navigation" aria-label="Attribute masters">
        {attributeResources
          .filter((resource) => access[resource])
          .map((resource) => (
            <a
              key={resource}
              className="janso-link"
              href={'/masters/' + resource}
              onClick={onLeave}
            >
              {
                {
                  'attribute-definitions': 'Definitions',
                  'attribute-options': 'Options',
                  'attribute-sets': 'Sets / templates',
                }[resource]
              }
            </a>
          ))}
        {access.products && (
          <a
            className="janso-link"
            href="/masters/items"
            onClick={onLeave}
          >
            Products
          </a>
        )}
      </nav>
    </>
  );
}
export function AttributeReference({
  company,
  resource = 'attribute-definitions',
  label,
  name,
  value,
  onChange,
  onRecord,
  required = false,
  disabled = false,
  error,
  activeOnly = true,
  dimension,
}: {
  company: string;
  resource?: 'attribute-definitions' | 'units';
  label: string;
  name?: string;
  value: string | null;
  onChange: (id: string | null) => void;
  onRecord?: (row: MasterRow) => void;
  required?: boolean;
  disabled?: boolean;
  error?: string;
  activeOnly?: boolean;
  dimension?: string;
}) {
  const [selected, setSelected] = useState<SearchSelectOption | null>(null),
    [problem, setProblem] = useState(''),
    resolve = useRef(onRecord);
  resolve.current = onRecord;
  const load = useCallback<SearchSelectLoader>(
    async ({ q, cursor, signal }) => {
      const params = new URLSearchParams({ limit: '50' });
      if (activeOnly) params.set('is_active', 'true');
      if (dimension && resource === 'units') params.set('dimension', dimension);
      if (q.trim().length >= 2) params.set('q', q.trim());
      if (cursor) params.set('cursor', cursor);
      const page = await masterRequest<ServicePage<MasterRow>>({
        path: attributeBase(company, resource) + '?' + params,
        signal,
      });
      if (
        !Array.isArray(page.items) ||
        !page.page ||
        page.items.some((row) => !attributeId.test(row.id))
      )
        throw {
          status: 502,
          message: 'Reference options could not be verified.',
        };
      return {
        items: page.items.map((row) => ({
          id: row.id,
          label: attributeLabel(row),
          meta: [row.code, row.value_type ?? row.dimension]
            .filter(Boolean)
            .join(' · '),
          disabled: activeOnly && row.is_active !== true,
        })),
        nextCursor: page.page.has_more ? page.page.next_cursor : null,
      };
    },
    [company, resource, activeOnly, dimension],
  );
  useEffect(() => {
    const controller = new AbortController();
    setSelected(null);
    setProblem('');
    if (value)
      masterRequest<MasterRow>({
        path: attributeBase(company, resource) + '/' + value,
        signal: controller.signal,
      })
        .then((row) => {
          assertMaster(row, company, value);
          if (!controller.signal.aborted) {
            setSelected({
              id: row.id,
              label: attributeLabel(row),
              meta: row.code,
            });
            resolve.current?.(row);
          }
        })
        .catch((error) => {
          if (!controller.signal.aborted)
            setProblem(requestFailure(error, 'attribute references').message);
        });
    return () => controller.abort();
  }, [company, resource, value]);
  return (
    <SearchSelect
      label={label}
      name={name}
      value={value}
      selected={
        selected ??
        (value
          ? {
              id: value,
              label: problem ? 'Reference unavailable' : 'Loading reference...',
              disabled: true,
            }
          : null)
      }
      loadOptions={load}
      scopeKey={[company, resource, activeOnly, dimension].join(':')}
      minQueryLength={0}
      clearable={!required}
      required={required}
      disabled={disabled}
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
