'use client';
import { inventoryBreadcrumbs } from '../lib/inventory-navigation';
import { useCallback, useEffect, useId, useState } from 'react';
import {
  Notice,
  PageNavigation,
  SearchSelect,
  Select,
  TextField,
  type SearchSelectLoader,
  type SearchSelectOption,
} from '@janso/ui';
import { assertMaster, masterRequest } from '../lib/catalog-master-api';
import type { MasterField, MasterRow } from '../lib/catalog-masters';
import { requestFailure } from '../lib/service-call';
import type { ServicePage } from '../lib/service-resource';
import { profileBase, profileId, profileReturn } from '../lib/product-profiles';
import {
  productProfileResources,
  profileDefinitions,
  type ProductProfileAccess,
  type ProductProfileResource,
} from '../lib/product-profile-resources';
import { IdentifierFailure, IdentifierField } from './UnitsIdentifiersCommon';
import { masterLink } from '../lib/master-navigation';
export { IdentifierFailure as ProfileFailure };
export function ProfileNavigation({
  title,
  back,
  access,
  onLeave,
  resource,
}: {
  title: string;
  back?: string;
  access: ProductProfileAccess;
  onLeave?: React.MouseEventHandler<HTMLAnchorElement>;
  resource?: ProductProfileResource;
}) {
  const operation =
    resource === 'manufacturing-operations' ||
    resource === 'manufacturing-routes';
  const manufacturingTitle =
    resource && operation
      ? profileDefinitions[resource].title
      : 'Manufacturing operations';
  return (
    <>
      <PageNavigation
        back={{
          href: profileReturn(
            back,
            operation ? '/masters' : '/inventory/product-profiles',
          ),
          label: 'previous page',
        }}
        breadcrumbs={
          operation
            ? [
                { label: 'Business overview', href: '/' },
                { label: 'Masters', href: '/masters' },
                ...(title === manufacturingTitle
                  ? []
                  : [
                      {
                        label: manufacturingTitle,
                        href: '/masters/' + resource,
                      },
                    ]),
                { label: title },
              ]
            : inventoryBreadcrumbs('product-profiles', title)
        }
        onNavigate={onLeave}
      />
      {!operation && (
        <nav
          className="janso-page-navigation"
          aria-label="Reusable product profiles"
        >
          {productProfileResources
            .filter((resource) => access[resource])
            .map((resource) => (
              <a
                key={resource}
                className="janso-link"
                href={'/masters/' + resource}
                onClick={onLeave}
              >
                {profileDefinitions[resource].title}
              </a>
            ))}
        </nav>
      )}
    </>
  );
}
export function ProfileExplanation({
  resource,
}: {
  resource: ProductProfileResource;
}) {
  return (
    <Notice>
      {resource === 'manufacturing-routes'
        ? 'Arrange sequential steps using specific operation revisions and exact setup, run and lead times. Publishing preserves the reviewed definition.'
        : resource === 'manufacturing-operations'
          ? 'Define reusable manufacturing operations and optional service references. Publishing a specification does not schedule work, consume stock or post costs.'
          : resource === 'inventory-templates'
            ? 'Define reusable batch, serial, expiry and valuation rules. Published revisions can be selected in product configuration.'
            : resource === 'warranty-policies'
              ? 'Warranty duration uses the selected calendar unit. Publishing preserves that unit and the start event.'
              : resource === 'return-policies'
                ? 'Set whether returns are allowed, the return window, and any required conditions. A zero-day window is valid.'
                : 'Set handling instructions and optional temperature bounds in Celsius. Temperatures are saved exactly, without rounding.'}{' '}
      Draft revisions can be edited; published revisions are immutable.
    </Notice>
  );
}
function ProfileIdentifierReference({
  company,
  value,
  disabled,
  error,
  onChange,
  returnTo,
  onLeave,
  source = 'identifier-profiles',
}: {
  company: string;
  value: string | null;
  disabled: boolean;
  error?: string;
  onChange: (value: string | null) => void;
  returnTo?: string;
  onLeave?: React.MouseEventHandler<HTMLAnchorElement>;
  source?: 'identifier-profiles' | 'items';
}) {
  const service = source === 'items';
  const label = service ? 'Service SKU' : 'Identifier profile';
  const [selected, setSelected] = useState<SearchSelectOption | null>(null),
    [problem, setProblem] = useState('');
  const load = useCallback<SearchSelectLoader>(
    async ({ q, cursor, signal }) => {
      const params = new URLSearchParams({
        limit: '50',
        ...(service ? {} : { is_active: 'true' }),
      });
      if (q.trim().length >= 2) params.set('q', q.trim());
      if (cursor) params.set('cursor', cursor);
      const page = await masterRequest<ServicePage<MasterRow>>({
        path:
          profileBase(
            company,
            service ? 'manufacturing-operations/service-options' : source,
          ) +
          '?' +
          params,
        signal,
      });
      if (
        !Array.isArray(page.items) ||
        !page.page ||
        page.items.some((row) => !profileId.test(row.id))
      )
        throw {
          status: 502,
          message: label + ' choices could not be verified.',
        };
      return {
        items: page.items.map((row) => ({
          id: row.id,
          label: row.name ?? row.code ?? 'Protected ' + label.toLowerCase(),
          meta: service ? String(row.sku ?? '') : row.code,
          disabled:
            (service ? row.status !== 'ACTIVE' : row.is_active !== true) ||
            (!row.name && !row.code && !row.sku),
        })),
        nextCursor: page.page.has_more ? page.page.next_cursor : null,
      };
    },
    [company, source, service, label],
  );
  useEffect(() => {
    const controller = new AbortController();
    setSelected(null);
    setProblem('');
    if (value)
      masterRequest<MasterRow>({
        path: profileBase(company, source + '/' + value),
        signal: controller.signal,
      })
        .then((row) => {
          assertMaster(row, company, value);
          if (!controller.signal.aborted)
            setSelected({
              id: row.id,
              label: row.name ?? row.code ?? 'Protected ' + label.toLowerCase(),
              meta: row.code,
            });
        })
        .catch((error) => {
          if (!controller.signal.aborted)
            setProblem(requestFailure(error, label).message);
        });
    return () => controller.abort();
  }, [company, value, source, label]);
  return (
    <div className="janso-flow">
      <SearchSelect
        label={label}
        name={service ? 'service_item_id' : 'identifier_profile_id'}
        scopeKey={company + ':' + source}
        value={value}
        selected={
          selected ??
          (value
            ? {
                id: value,
                label: problem
                  ? label + ' unavailable'
                  : 'Loading ' + label.toLowerCase() + '...',
                disabled: true,
              }
            : null)
        }
        minQueryLength={0}
        loadOptions={load}
        clearable
        disabled={disabled}
        error={error ?? (problem || undefined)}
        hint={
          service
            ? 'Optional. Choose an active service SKU in this company.'
            : 'Optional; serial tracking is required. Choose an active identifier profile in this company.'
        }
        onChange={onChange}
      />
      {disabled &&
        returnTo &&
        selected?.id === value &&
        !problem &&
        profileId.test(selected.id) && (
          <a
            className="janso-link janso-fine"
            href={masterLink(
              '/masters/' + source + '/' + selected.id,
              returnTo,
            )}
            onClick={onLeave}
          >
            Open {label.toLowerCase()}
          </a>
        )}
    </div>
  );
}
export function ProfileField({
  company,
  field,
  value,
  disabled,
  error,
  onChange,
  access,
  returnTo,
  onLeave,
}: {
  company: string;
  field: MasterField;
  value: unknown;
  disabled: boolean;
  error?: string;
  onChange: (value: unknown) => void;
  access: ProductProfileAccess;
  returnTo?: string;
  onLeave?: React.MouseEventHandler<HTMLAnchorElement>;
}) {
  const id = useId(),
    control = field.control;
  if (!field.visible || field.conditional_access || !control) return null;
  const label = field.label !== field.key ? field.label : control.label,
    locked = disabled || !field.writable || !!control.disabled_reason;
  if (field.key === 'service_item_id')
    return access.serviceItems ? (
      <ProfileIdentifierReference
        company={company}
        source="items"
        value={typeof value === 'string' ? value : null}
        disabled={locked}
        error={error}
        onChange={onChange}
        returnTo={returnTo}
        onLeave={onLeave}
      />
    ) : (
      <TextField
        label={label}
        value={
          value ? 'Existing service SKU (read access unavailable)' : 'Not set'
        }
        disabled
        hint="The existing reference is retained when other fields are saved."
      />
    );
  if (field.key === 'identifier_profile_id')
    return access.identifiers ? (
      <ProfileIdentifierReference
        returnTo={returnTo}
        onLeave={onLeave}
        company={company}
        value={typeof value === 'string' ? value : null}
        disabled={locked}
        error={error}
        onChange={onChange}
      />
    ) : (
      <TextField
        label={label}
        value={
          value
            ? 'Existing identifier profile (read access unavailable)'
            : 'Not set'
        }
        disabled
        hint="The existing reference is retained when other fields are saved."
      />
    );
  if (
    [
      'instructions',
      'coverage_description',
      'specification',
      'change_reason',
    ].includes(field.key)
  )
    return (
      <div className="janso-field janso-form-grid__full">
        <label className="janso-label" htmlFor={id}>
          {label}
        </label>
        <textarea
          id={id}
          name={field.key}
          className="janso-input"
          rows={4}
          required={field.required && !control.nullable}
          value={String(value ?? '')}
          disabled={locked}
          maxLength={control.max_length ?? 2000}
          aria-invalid={!!error}
          aria-describedby={error ? id + '-error' : undefined}
          onChange={(event) => onChange(event.target.value)}
        />
        {error && (
          <p id={id + '-error'} className="janso-error" role="alert">
            {error}
          </p>
        )}
      </div>
    );
  if (
    control.kind === 'integer' ||
    field.key === 'temperature_min' ||
    field.key === 'temperature_max'
  )
    return (
      <TextField
        label={label}
        name={field.key}
        value={String(value ?? '')}
        disabled={locked}
        required={!control.nullable}
        inputMode={control.kind === 'integer' ? 'numeric' : 'decimal'}
        maxLength={control.max_length ?? undefined}
        error={error}
        hint={
          control.kind === 'integer'
            ? (control.nullable ? 'Optional. ' : '') +
              `Whole number from ${control.minimum ?? 0} to ${control.maximum ?? 36500}.`
            : 'Optional, in °C. Up to 4 decimal places; minimum -273.15.'
        }
        onChange={(event) => onChange(event.target.value)}
      />
    );
  if (control.kind === 'select')
    return (
      <Select
        label={label}
        name={field.key}
        value={String(value ?? '')}
        disabled={locked}
        required={!control.nullable}
        placeholder={control.nullable ? 'Not set' : 'Choose an option'}
        options={control.choices ?? []}
        error={error}
        onChange={(value) => onChange(value || null)}
      />
    );
  return (
    <IdentifierField
      company={company}
      field={field}
      value={value}
      disabled={locked}
      error={error}
      onChange={onChange}
    />
  );
}
