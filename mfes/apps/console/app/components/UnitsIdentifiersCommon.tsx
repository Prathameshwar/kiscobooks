'use client';
import { inventoryBreadcrumbs } from '../lib/inventory-navigation';
import { useCallback, useEffect, useId, useState } from 'react';
import {
  Button,
  Checkbox,
  ErrorState,
  Notice,
  PageNavigation,
  SearchSelect,
  Select,
  TextField,
  asErrorStatus,
  type SearchSelectLoader,
  type SearchSelectOption,
} from '@janso/ui';
import { assertMaster, masterRequest } from '../lib/catalog-master-api';
import type { MasterField, MasterRow } from '../lib/catalog-masters';
import { requestFailure, type RequestFailure } from '../lib/service-call';
import type { ServicePage } from '../lib/service-resource';
import {
  identifierBase,
  identifierLink,
  identifierReturn,
  identifierTitle,
  identifierResources,
} from '../lib/units-identifiers';
import { signInUrl } from '../lib/navigate';

export type IdentifierAccess = {
  units: boolean;
  'unit-conversions': boolean;
  'pack-types': boolean;
  'identifier-types': boolean;
  'identifier-namespaces': boolean;
  'identifier-profiles': boolean;
};
export function IdentifierNavigation({
  title,
  back,
  access,
  onLeave,
}: {
  title: string;
  back?: string;
  access: IdentifierAccess;
  onLeave?: React.MouseEventHandler<HTMLAnchorElement>;
}) {
  return (
    <>
      <PageNavigation
        back={{ href: identifierReturn(back, '/inventory/units-identifiers'), label: 'previous page' }}
        onNavigate={onLeave}
        breadcrumbs={inventoryBreadcrumbs('units-identifiers', title)}
      />
      <nav className="janso-page-navigation" aria-label="Units and identifiers">
        {(['units', ...identifierResources] as const)
          .filter((resource) => access[resource])
          .map((resource) => (
            <a
              className="janso-link"
              key={resource}
              href={'/masters/' + resource}
              onClick={onLeave}
            >
              {
                {
                  units: 'Units',
                  'unit-conversions': 'Conversions',
                  'pack-types': 'Pack types',
                  'identifier-types': 'Identifier types',
                  'identifier-namespaces': 'Namespaces',
                  'identifier-profiles': 'Profiles',
                }[resource]
              }
            </a>
          ))}
      </nav>
    </>
  );
}
export function IdentifierFailure({
  failure,
  retry,
  write = false,
}: {
  failure: RequestFailure | null;
  retry?: () => void;
  write?: boolean;
}) {
  if (!failure) return null;
  if (write && failure.status >= 500)
    return (
      <Notice tone="danger">
        <p>{failure.message}</p>
        <p>
          The save could not be confirmed. Your values are retained. Retry the
          same save to recover its result.
        </p>
      </Notice>
    );
  if ([409, 422].includes(failure.status))
    return (
      <Notice tone="danger">
        {failure.message}
        {failure.status === 409 && (
          <p>
            The current record or its dependencies changed. Your draft is
            retained; reload and review before another save.
          </p>
        )}
        {retry && failure.status === 409 && (
          <Button variant="ghost" onClick={retry}>
            Reload and review
          </Button>
        )}
      </Notice>
    );
  return (
    <ErrorState
      status={asErrorStatus(failure.status)}
      detail={failure.message}
      action={
        failure.status === 401 ? (
          <a className="janso-link" href={signInUrl()}>
            Sign in again
          </a>
        ) : retry && failure.status !== 403 ? (
          <Button onClick={retry}>Retry loading</Button>
        ) : undefined
      }
    />
  );
}
export function IdentifierUnitReference({
  company,
  label,
  name,
  value,
  onChange,
  disabled = false,
  required = false,
  error,
  activeOnly = true,
}: {
  company: string;
  label: string;
  name?: string;
  value: string | null;
  onChange: (id: string | null) => void;
  disabled?: boolean;
  required?: boolean;
  error?: string;
  activeOnly?: boolean;
}) {
  const [selected, setSelected] = useState<SearchSelectOption | null>(null),
    [problem, setProblem] = useState('');
  const load = useCallback<SearchSelectLoader>(
    async ({ q, cursor, signal }) => {
      const params = new URLSearchParams({ limit: '50' });
      if (activeOnly) params.set('is_active', 'true');
      if (q.trim().length >= 2) params.set('q', q.trim());
      if (cursor) params.set('cursor', cursor);
      const page = await masterRequest<ServicePage<MasterRow>>({
        path: identifierBase(company, 'units') + '?' + params,
        signal,
      });
      if (!Array.isArray(page.items) || !page.page)
        throw { status: 502, message: 'Unit options could not be verified.' };
      return {
        items: page.items.map((row) => ({
          id: row.id,
          label: identifierTitle(row),
          meta: [row.code, row.symbol, row.dimension]
            .filter(Boolean)
            .join(' · '),
        })),
        nextCursor: page.page.has_more ? page.page.next_cursor : null,
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
        path: identifierBase(company, 'units') + '/' + value,
        signal: controller.signal,
      })
        .then((row) => {
          assertMaster(row, company, value);
          if (!controller.signal.aborted)
            setSelected({
              id: row.id,
              label: identifierTitle(row),
              meta: row.code,
            });
        })
        .catch((error) => {
          if (!controller.signal.aborted)
            setProblem(requestFailure(error, 'unit references').message);
        });
    return () => controller.abort();
  }, [company, value]);
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
              label: problem ? 'Unit unavailable' : 'Loading unit...',
              disabled: true,
            }
          : null)
      }
      loadOptions={load}
      scopeKey={company + ':units:' + activeOnly}
      minQueryLength={0}
      required={required}
      clearable={!required}
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
export function IdentifierField({
  company,
  field,
  value,
  onChange,
  disabled,
  error,
  prefix = '',
  canReadUnits = true,
}: {
  company: string;
  field: MasterField;
  value: unknown;
  onChange: (value: unknown) => void;
  disabled?: boolean;
  error?: string;
  prefix?: string;
  canReadUnits?: boolean;
}) {
  const c = field.control,
    errorId = useId();
  if (
    field.source !== 'native' ||
    !field.visible ||
    field.conditional_access ||
    !c
  )
    return null;
  const locked = !!disabled || !field.writable,
    label =
      (prefix
        ? 'Requirement ' + (Number(prefix.split('.')[1]) + 1) + ': '
        : '') + (field.label !== field.key ? field.label : c.label),
    name = prefix + field.key;
  const common = {
    label,
    name,
    required: !locked && field.required,
    disabled: locked,
    error,
    hint:
      field.help_text ??
      (field.key === 'code'
        ? 'Use uppercase letters, numbers, dots, hyphens or underscores.'
        : ['numerator', 'denominator'].includes(field.key)
          ? 'Enter a positive whole number. Values retain their full integer precision.'
          : undefined),
  };
  if (c.kind === 'reference')
    return canReadUnits ? (
      <IdentifierUnitReference
        {...common}
        company={company}
        value={typeof value === 'string' ? value : null}
        onChange={onChange}
      />
    ) : (
      <Notice>Unit selection requires unit read access.</Notice>
    );
  if (c.kind === 'select')
    return (
      <Select
        {...common}
        value={value == null ? '' : String(value)}
        options={c.choices ?? []}
        onChange={onChange}
      />
    );
  if (c.kind === 'boolean' && field.key === 'is_active')
    return (
      <TextField
        {...common}
        value={value === false ? 'Inactive' : 'Active'}
        disabled
        hint="New records start active. Lifecycle changes are separate actions."
      />
    );
  if (c.kind === 'boolean')
    return (
      <div className="janso-field">
        <Checkbox
          name={name}
          disabled={locked}
          checked={value === true}
          onChange={(event) => onChange(event.target.checked)}
          aria-invalid={!!error || undefined}
          aria-describedby={error ? errorId : undefined}
        >
          {label}
        </Checkbox>
        {error && (
          <p id={errorId} role="alert" className="janso-error">
            {error}
          </p>
        )}
      </div>
    );
  return (
    <TextField
      {...common}
      value={value == null ? '' : String(value)}
      inputMode={
        c.kind === 'integer' || ['numerator', 'denominator'].includes(field.key)
          ? 'numeric'
          : undefined
      }
      maxLength={c.max_length ?? undefined}
      onChange={(event) => onChange(event.target.value)}
    />
  );
}
export function IdentifierUnitLabel({
  company,
  id,
  here,
  onLeave,
}: {
  company: string;
  id: string;
  here: string;
  onLeave?: React.MouseEventHandler<HTMLAnchorElement>;
}) {
  const [label, setLabel] = useState('Loading unit...');
  useEffect(() => {
    const controller = new AbortController();
    setLabel('Loading unit...');
    masterRequest<MasterRow>({
      path: identifierBase(company, 'units') + '/' + id,
      signal: controller.signal,
    })
      .then((row) => {
        assertMaster(row, company, id);
        if (!controller.signal.aborted) setLabel(identifierTitle(row));
      })
      .catch(() => {
        if (!controller.signal.aborted) setLabel('Unit unavailable');
      });
    return () => controller.abort();
  }, [company, id]);
  return (
    <a
      className="janso-link"
      href={identifierLink('/masters/units/' + id, here)}
      onClick={onLeave}
    >
      {label}
    </a>
  );
}
