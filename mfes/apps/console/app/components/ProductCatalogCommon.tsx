'use client';
import { useProductMode } from './ProductModeProvider';
import { masterLink, masterReferencePath } from '../lib/master-navigation';
import { useCallback, useEffect, useId, useState } from 'react';
import {
  Button,
  Checkbox,
  PageNavigation,
  SearchSelect,
  Select,
  TextField,
  type SearchSelectLoader,
  type SearchSelectOption,
} from '@janso/ui';
import { masterRequest, assertMaster } from '../lib/catalog-master-api';
import type { MasterField, MasterRow } from '../lib/catalog-masters';
import type { ServicePage } from '../lib/service-resource';
import { requestFailure } from '../lib/service-call';
import {
  catalogBack,
  catalogBase,
  catalogId,
  catalogVisible,
} from '../lib/product-classification';
import {
  classificationResources,
  classificationDefinitions,
  typeSets,
  type ClassificationAccess,
  type ClassificationResource,
} from '../lib/product-classification-resources';
import { IdentifierFailure } from './UnitsIdentifiersCommon';
import { WarehouseRegionalField } from './WarehouseRegionalField';
import { ConfigurationReference } from './ProductConfigurationCommon';
import { ProductReferenceCreate } from './ProductReferenceCreate';
export const ProductCatalogFailure = IdentifierFailure;
export function ProductCatalogNavigation({
  title,
  back,
  access,
  resource: currentResource,
  onLeave,
  hideTabs = false,
}: {
  title: string;
  resource?: ClassificationResource;
  back?: string;
  access: ClassificationAccess;
  onLeave?: React.MouseEventHandler<HTMLAnchorElement>;
  hideTabs?: boolean;
}) {
  const mode = useProductMode();
  const simple = !!mode && mode.data?.product_family_sku_enabled !== true;
  return (
    <>
      <PageNavigation
        back={{
          href: catalogBack(back, '/inventory/products'),
          label: 'previous page',
        }}
        breadcrumbs={[
          { label: 'Business overview', href: '/' },
          { label: 'Masters', href: '/masters' },
          ...(currentResource &&
          title !== classificationDefinitions[currentResource].title
            ? [
                {
                  label: simple && currentResource === 'items' ? 'Products' : classificationDefinitions[currentResource].title,
                  href: '/masters/' + currentResource,
                },
              ]
            : []),
          { label: title },
        ]}
        onNavigate={onLeave}
      />
      {!hideTabs && (
        <nav className="janso-tabs" aria-label="Products and classification">
          {classificationResources
            .filter((resource) => access[resource] && (!simple || resource !== 'product-families'))
            .map((resource) => (
              <a
                key={resource}
                className="janso-tabs__tab"
                aria-current={resource === currentResource ? 'page' : undefined}
                href={'/masters/' + resource}
                onClick={onLeave}
              >
                {simple && resource === 'items' ? 'Products' : classificationDefinitions[resource].title}
              </a>
            ))}
        </nav>
      )}
    </>
  );
}
const configurationSources = [
  'product-type-revisions',
  'attribute-set-revisions',
  'inventory-template-revisions',
  'warranty-revisions',
  'return-policy-revisions',
  'handling-revisions',
];
export function readableSource(source: string, access: ClassificationAccess) {
  if (configurationSources.includes(source)) return access.configuration;
  if (source === 'units') return access.units;
  if (source === 'manufacturers') return access.manufacturers;
  if (source === 'item-groups') return access.groups;
  if (source === 'parties') return access.parties;
  if (source === 'pack-types') return access.packTypes;
  if (source === 'unit-bindings') return access.items;
  return !!access[source as keyof ClassificationAccess];
}
export function ProductCatalogReference({
  company,
  source,
  label,
  name,
  value,
  onChange,
  access,
  values = {},
  disabled = false,
  required = false,
  error,
  exclude,
  hint,
  returnTo,
  onLeave,
}: {
  company: string;
  source: string;
  label: string;
  name?: string;
  value: string | null;
  onChange: (value: string | null) => void;
  access: ClassificationAccess;
  values?: Record<string, unknown>;
  disabled?: boolean;
  required?: boolean;
  error?: string;
  exclude?: string;
  hint?: string;
  returnTo?: string;
  onLeave?: React.MouseEventHandler<HTMLAnchorElement>;
}) {
  const permitted = readableSource(source, access);
  const parentKey =
    source === 'brand-series'
      ? 'brand_id'
      : source === 'manufacturer-sites'
        ? 'manufacturer_id'
        : source === 'item-categories'
          ? 'scheme_id'
          : undefined;
  const parent =
    parentKey && typeof values[parentKey] === 'string'
      ? (values[parentKey] as string)
      : undefined;
  const resource =
    source === 'unit-bindings'
      ? 'items/' + values.item_id + '/unit-bindings'
      : source;
  const path = catalogBase(company, resource),
    scope =
      company +
      ':' +
      source +
      ':' +
      (parent ?? '') +
      ':' +
      (values.item_id ?? '');
  const [selected, setSelected] = useState<SearchSelectOption | null>(null),
    [problem, setProblem] = useState('');
  const load = useCallback<SearchSelectLoader>(
    async ({ q, cursor, signal }) => {
      const params = new URLSearchParams({ limit: '50' });
      if (!['unit-bindings', 'product-families', 'items'].includes(source))
        params.set(
          source === 'parties' ? 'status' : 'is_active',
          source === 'parties' ? 'ACTIVE' : 'true',
        );
      if (q.trim().length >= 2 && source !== 'unit-bindings')
        params.set('q', q.trim());
      if (cursor) params.set('cursor', cursor);
      if (parentKey && parent) params.set(parentKey, parent);
      const page = await masterRequest<ServicePage<MasterRow>>({
        service: source === 'parties' ? 'accounting' : 'catalog',
        path: path + '?' + params,
        signal,
      });
      if (
        !Array.isArray(page.items) ||
        !page.page ||
        page.items.some(
          (row) =>
            !catalogId.test(row.id) ||
            (row.company_id != null && row.company_id !== company) ||
            (parentKey && parent && row[parentKey] !== parent),
        )
      )
        throw {
          status: 502,
          message:
            'The reference choices did not match this company or parent.',
        };
      return {
        items: page.items.map((row) => ({
          id: row.id,
          label: row.name ?? row.code ?? 'Protected record',
          meta: row.code,
          disabled:
            row.id === exclude ||
            (!row.name && !row.code) ||
            (source !== 'unit-bindings' &&
              source !== 'parties' &&
              source !== 'product-families' &&
              source !== 'items' &&
              row.is_active !== true),
        })),
        nextCursor: page.page.has_more ? page.page.next_cursor : null,
      };
    },
    [path, source, parentKey, parent, exclude, company],
  );
  useEffect(() => {
    const controller = new AbortController();
    setSelected(null);
    setProblem('');
    if (value && permitted && !configurationSources.includes(source))
      masterRequest<MasterRow>({
        service: source === 'parties' ? 'accounting' : 'catalog',
        path: path + '/' + value,
        signal: controller.signal,
      })
        .then((row) => {
          assertMaster(row, company, value);
          if (parentKey && parent && row[parentKey] !== parent)
            throw {
              status: 502,
              message: 'This selection does not belong to the selected parent.',
            };
          if (!controller.signal.aborted)
            setSelected({
              id: row.id,
              label: row.name ?? row.code ?? 'Protected record',
              meta: row.code,
            });
        })
        .catch((error) => {
          if (!controller.signal.aborted)
            setProblem(requestFailure(error, 'reference choices').message);
        });
    return () => controller.abort();
  }, [path, source, value, permitted, company, parentKey, parent]);
  if (!permitted)
    return (
      <TextField
        label={label}
        value={value ? 'Existing reference retained' : 'Not set'}
        disabled
        hint="Read access to these references is required to change this field."
      />
    );
  if (configurationSources.includes(source))
    return (
      <ProductReferenceCreate company={company} source={source} kind={String(values.kind ?? 'GOODS')} access={access} disabled={disabled} onCreated={onChange}>
      <ConfigurationReference
        returnTo={returnTo}
        onLeave={onLeave}
        company={company}
        source={source}
        kind={
          source === 'product-type-revisions' &&
          ['GOODS', 'SERVICE'].includes(String(values.kind))
            ? (values.kind as 'GOODS' | 'SERVICE')
            : undefined
        }
        label={label}
        value={value}
        onChange={onChange}
        disabled={disabled}
        required={required}
        error={error}
        hint={hint ?? 'Choose a published revision from an active master.'}
      />
      </ProductReferenceCreate>
    );
  const referencePath = value ? masterReferencePath(source, value) : null;
  return (
    <ProductReferenceCreate company={company} source={source} kind={String(values.kind ?? 'GOODS')} access={access} disabled={disabled || (!!parentKey && !parent)} onCreated={onChange}>
    <div className="janso-flow">
      <SearchSelect
        label={label}
        name={name}
        scopeKey={scope}
        value={value}
        selected={
          selected?.id === value
            ? selected
            : value
              ? {
                  id: value,
                  label: problem
                    ? 'Reference unavailable'
                    : 'Loading reference...',
                  disabled: true,
                }
              : null
        }
        loadOptions={load}
        minQueryLength={0}
        clearable={!required}
        required={required}
        disabled={disabled || (!!parentKey && !parent)}
        error={error ?? (problem || undefined)}
        hint={
          parentKey && !parent
            ? 'Choose the parent first.'
            : (hint ??
              'Search by name or code. Only active records in this company are offered.')
        }
        onChange={(next, option) => {
          setSelected(option);
          setProblem('');
          onChange(next);
        }}
      />
      {disabled &&
        returnTo &&
        referencePath &&
        selected?.id === value &&
        !problem && (
          <a
            className="janso-link janso-fine"
            href={masterLink(referencePath, returnTo)}
            onClick={onLeave}
          >
            Open {label.toLowerCase()}
          </a>
        )}
    </div>
    </ProductReferenceCreate>
  );
}
export function ProductCatalogField({
  company,
  field,
  values,
  onChange,
  access,
  disabled = false,
  error,
  exclude,
  prefix = '',
  readView = false,
  returnTo,
  onLeave,
}: {
  company: string;
  field: MasterField;
  values: Record<string, unknown>;
  onChange: (value: unknown) => void;
  access: ClassificationAccess;
  disabled?: boolean;
  error?: string;
  exclude?: string;
  prefix?: string;
  readView?: boolean;
  returnTo?: string;
  onLeave?: React.MouseEventHandler<HTMLAnchorElement>;
}) {
  const id = useId(),
    control = field.control;
  if (!catalogVisible([field], field.key) || !control) return null;
  if (
    !readView &&
    control.depends_on &&
    control.show_when != null &&
    String(values[control.depends_on]) !== control.show_when
  )
    return null;
  const key = field.key,
    value = values[key],
    locked = disabled || !field.writable || !!control.disabled_reason,
    label = field.label !== field.key ? field.label : control.label;
  const retained = Array.isArray(value)
    ? value.filter(
        (entry) =>
          typeof entry === 'string' &&
          !(control.choices ?? []).some((choice) => choice.value === entry),
      )
    : [];
  const common = {
    label,
    name: prefix + key,
    disabled: locked,
    required: !locked && (field.required || !control.nullable),
    error,
    hint:
      control.disabled_reason ??
      (!disabled && !field.writable
        ? 'This field is read-only.'
        : (field.help_text ??
          (!locked && ['code', 'sku'].includes(key)
            ? 'Use up to 30 uppercase letters, numbers, dots, hyphens or underscores; start with a letter or number.'
            : !locked && key === 'base_unit_id'
              ? 'Choose how one unit is measured. The base unit is fixed after creation.'
              : !locked && key === 'product_type_revision_id'
                ? 'Choose a published type that matches goods or services and your inventory requirements.'
                : !locked && key === 'min_sale_quantity'
                  ? 'Optional. Enter a positive quantity with up to four decimal places, in the base unit.'
                  : !locked && !control.nullable && control.kind !== 'boolean'
                    ? 'Required.'
                    : undefined))),
  };
  if (typeSets.includes(key))
    return (
      <fieldset
        className="janso-setup__fields janso-field"
        disabled={locked}
        aria-describedby={error ? id + '-error' : undefined}
      >
        <legend className="janso-label">{label}</legend>
        {!!retained.length && (
          <p className="janso-hint">
            Retained selection: {retained.join(', ')}.
          </p>
        )}
        {common.hint && <p className="janso-hint">{common.hint}</p>}
        <div className="janso-form-actions">
          {(control.choices ?? []).map((choice) => (
            <Checkbox
              key={choice.value}
              name={prefix + key}
              checked={Array.isArray(value) && value.includes(choice.value)}
              aria-invalid={!!error}
              onChange={(event) =>
                onChange(
                  event.target.checked
                    ? [...(Array.isArray(value) ? value : []), choice.value]
                    : (Array.isArray(value) ? value : []).filter(
                        (entry) => entry !== choice.value,
                      ),
                )
              }
            >
              {choice.label}
            </Checkbox>
          ))}
        </div>
        {!!retained.length && !locked && (
          <Button
            variant="ghost"
            onClick={() =>
              onChange(
                (value as unknown[]).filter(
                  (entry) => !retained.includes(entry),
                ),
              )
            }
          >
            Clear unavailable selections
          </Button>
        )}
        {error && (
          <p id={id + '-error'} role="alert" className="janso-error">
            {error}
          </p>
        )}
      </fieldset>
    );
  if (control.kind === 'reference')
    return (
      <ProductCatalogReference
        returnTo={returnTo}
        onLeave={onLeave}
        {...common}
        company={company}
        source={control.reference_source ?? ''}
        access={access}
        value={typeof value === 'string' ? value : null}
        values={values}
        exclude={exclude}
        onChange={onChange}
      />
    );
  if (key === 'country_code' || key === 'state_code')
    return (
      <WarehouseRegionalField
        {...common}
        company={company}
        type={key === 'country_code' ? 'country' : 'state'}
        value={typeof value === 'string' ? value : null}
        country={
          typeof values.country_code === 'string' ? values.country_code : null
        }
        onChange={onChange}
      />
    );
  if (key === 'description')
    return (
      <div className="janso-field janso-form-grid__full">
        <label htmlFor={id} className="janso-label">
          {label}
          {common.required && (
            <span className="janso-required" aria-hidden="true">
              *
            </span>
          )}
        </label>
        <textarea
          id={id}
          className="janso-input"
          name={prefix + key}
          rows={4}
          maxLength={control.max_length ?? 2000}
          disabled={locked}
          required={common.required}
          value={String(value ?? '')}
          aria-invalid={!!error}
          aria-describedby={
            [common.hint ? id + '-hint' : '', error ? id + '-error' : '']
              .filter(Boolean)
              .join(' ') || undefined
          }
          onChange={(event) => onChange(event.target.value)}
        />
        {common.hint && (
          <p id={id + '-hint'} className="janso-hint">
            {common.hint}
          </p>
        )}
        {error && (
          <p id={id + '-error'} className="janso-error" role="alert">
            {error}
          </p>
        )}
      </div>
    );
  if (control.kind === 'boolean')
    return (
      <div className="janso-field">
        <Checkbox
          name={prefix + key}
          disabled={locked}
          checked={value === true}
          aria-invalid={!!error}
          aria-describedby={
            [common.hint ? id + '-hint' : '', error ? id + '-error' : '']
              .filter(Boolean)
              .join(' ') || undefined
          }
          onChange={(event) => onChange(event.target.checked)}
        >
          {label}
        </Checkbox>
        {common.hint && (
          <p id={id + '-hint'} className="janso-hint">
            {common.hint}
          </p>
        )}
        {error && (
          <p id={id + '-error'} className="janso-error" role="alert">
            {error}
          </p>
        )}
      </div>
    );
  if (control.kind === 'select')
    return (
      <Select
        {...common}
        value={String(value ?? '')}
        options={
          typeof value === 'string' &&
          value &&
          !(control.choices ?? []).some((choice) => choice.value === value)
            ? [
                ...(control.choices ?? []),
                {
                  value,
                  label:
                    'Retained: ' +
                    value.slice(0, 1).toUpperCase() +
                    value.slice(1).toLowerCase().replaceAll('_', ' '),
                  disabled: true,
                },
              ]
            : (control.choices ?? [])
        }
        placeholder="Choose an option"
        onChange={onChange}
      />
    );
  return (
    <TextField
      {...common}
      value={String(value ?? '')}
      maxLength={control.max_length ?? undefined}
      type={control.kind === 'date' ? 'date' : 'text'}
      min={control.kind === 'date' ? '1000-01-01' : undefined}
      inputMode={
        control.kind === 'decimal'
          ? 'decimal'
          : control.kind === 'integer' ||
              ['numerator', 'denominator'].includes(key)
            ? 'numeric'
            : undefined
      }
      hint={
        common.hint ??
        (['code', 'sku'].includes(key)
          ? 'Use a short uppercase code, for example BASIC-001.'
          : control.kind === 'decimal'
            ? 'Use an exact quantity with up to four decimal places.'
            : undefined)
      }
      onChange={(event) => onChange(event.target.value)}
    />
  );
}
