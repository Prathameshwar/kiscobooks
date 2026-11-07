'use client';
import { useCallback, useEffect, useId, useState } from 'react';
import {
  Button,
  ErrorState,
  Notice,
  PageNavigation,
  Pager,
  SearchSelect,
  Select,
  Skeleton,
  TextField,
  Card,
  CardBody,
  CardHeader,
  SectionHeader,
  asErrorStatus,
  useFormatters,
  type SearchSelectLoader,
  type SearchSelectOption,
} from '@janso/ui';
import { accountingFieldSections } from '../lib/accounting-masters';
import {
  accountingRequest,
  accountingFieldActive,
  accountingChoices,
  accountingConstraints,
} from '../lib/accounting-configuration';
import {
  accountingBack,
  accountingBackLabel,
  accountingLink,
  accountingResource,
  accountingRoot,
  accountingUUID,
  type AccountingField,
} from '../lib/accounting-configuration-resources';
import {
  requestFailure,
  serviceCall,
  type RequestFailure,
} from '../lib/service-call';
import { signInUrl } from '../lib/navigate';
import type { ServicePage, useServiceList } from '../lib/service-resource';
import { configurationTrail } from '../lib/configuration-navigation';
import { cleanGstin } from '../lib/gstin';
import { limitMasterCode } from '../lib/accounting-master-code';
import { administrationBackLabel } from '../lib/administration-navigation';

export function AccountingNavigation({
  title,
  back = accountingRoot,
  onLeave,
  resource: currentResource,
  id,
  mode = 'directory',
  availableResources = [],
}: {
  title: string;
  back?: string;
  onLeave?: React.MouseEventHandler<HTMLAnchorElement>;
  resource?: string;
  id?: string;
  mode?: 'directory' | 'detail' | 'new' | 'edit' | 'history';
  availableResources?: readonly string[];
}) {
  const target = accountingBack(back),
    path = new URL(target, 'https://console.invalid').pathname,
    trail = configurationTrail(target);
  const label =
    path === '/settings' || path.startsWith('/companies/')
      ? administrationBackLabel(target)
      : accountingBackLabel(target);
  const directory =
    trail.find(
      (value) =>
        new URL(value, 'https://console.invalid').pathname === accountingRoot,
    ) ?? accountingLink(accountingRoot, trail.at(-1) ?? accountingRoot);
  const config = accountingResource(
      currentResource === 'suppliers' ? 'parties' : (currentResource ?? ''),
    ),
    base = accountingRoot + '/' + currentResource,
    resourceDirectory =
      trail.find(
        (value) => new URL(value, 'https://console.invalid').pathname === base,
      ) ?? accountingLink(base, directory),
    details = id
      ? (trail.find(
          (value) =>
            new URL(value, 'https://console.invalid').pathname ===
            base + '/' + id,
        ) ?? accountingLink(base + '/' + id, resourceDirectory))
      : undefined;
  const area =
    currentResource === 'suppliers'
      ? 'suppliers'
      : config?.owner === 'party_id'
        ? 'parties'
        : config?.owner === 'account_id'
          ? 'accounts'
          : currentResource;
  const masterArea = ['accounts', 'parties', 'suppliers'].includes(area ?? '');
  return (
    <>
      <PageNavigation
        back={{ href: target, label }}
        breadcrumbs={[
          { label: 'Business overview', href: '/' },
          ...(trail.includes('/settings')
            ? [{ label: 'Company settings', href: '/settings' }]
            : []),
          ...(title !== 'Accounting configuration'
            ? [{ label: 'Accounting configuration', href: directory }]
            : []),
          ...(currentResource && mode !== 'directory'
            ? [
                {
                  label:
                    currentResource === 'suppliers'
                      ? 'Suppliers'
                      : (config?.title ?? 'Exchange rates'),
                  href: resourceDirectory,
                },
              ]
            : []),
          ...(details && (mode === 'edit' || mode === 'history')
            ? [
                {
                  label: (config?.singular ?? 'Exchange rate') + ' details',
                  href: details,
                },
              ]
            : []),
          { label: title },
        ]}
        onNavigate={onLeave}
      />
      {masterArea && (
        <nav className="janso-tabs" aria-label="Accounts and parties">
          {['accounts', 'parties', 'suppliers']
            .filter(
              (resource) =>
                resource === area ||
                availableResources.includes(
                  resource === 'suppliers' ? 'parties' : resource,
                ),
            )
            .map((resource) => (
              <a
                key={resource}
                className="janso-tabs__tab"
                aria-current={resource === area ? 'page' : undefined}
                href={'/accounting/' + resource}
                onClick={onLeave}
              >
                {resource[0]!.toUpperCase() + resource.slice(1)}
              </a>
            ))}
        </nav>
      )}
    </>
  );
}
export function AccountingFailure({
  failure,
  retry,
  write = false,
  onLeave,
}: {
  failure: RequestFailure | null;
  retry?: () => void;
  write?: boolean;
  onLeave?: React.MouseEventHandler<HTMLAnchorElement>;
}) {
  if (!failure) return null;
  if (
    failure.status === 409 ||
    failure.status === 422 ||
    (write && failure.status >= 500)
  )
    return (
      <Notice tone="danger">
        {failure.message}
        {failure.status === 409 && (
          <p>
            Reload and review the saved record before submitting a new change.
          </p>
        )}
        {write && failure.status >= 500 && (
          <p>
            The result is unconfirmed. Retry the same request to recover its
            result.
          </p>
        )}
        {retry && (
          <Button variant="ghost" onClick={retry}>
            Reload and review
          </Button>
        )}
      </Notice>
    );
  const auth = signInUrl(),
    login =
      auth +
      (auth.includes('?') ? '&' : '?') +
      new URLSearchParams({
        returnTo:
          typeof window === 'undefined'
            ? accountingRoot
            : window.location.pathname + window.location.search,
      });
  return (
    <ErrorState
      status={asErrorStatus(failure.status)}
      detail={failure.message}
      action={
        failure.status === 401 ? (
          <a className="janso-link" href={login} onClick={onLeave}>
            Sign in again
          </a>
        ) : retry && failure.status !== 403 ? (
          <Button onClick={retry}>Reload configuration</Button>
        ) : undefined
      }
    />
  );
}
export const AccountingLoading = () => (
  <div role="status" aria-label="Loading Accounting configuration">
    <Skeleton />
  </div>
);
export function AccountingPager<T>({
  list,
  noun,
}: {
  list: ReturnType<typeof useServiceList<T>>;
  noun: string;
}) {
  if (list.loading || list.failure || !list.data) return null;
  return (
    <Pager
      count={list.data?.items.length ?? 0}
      limit={list.limit}
      hasPrevious={list.hasPrevious}
      hasNext={!!list.data?.page.has_more}
      onPrevious={list.previous}
      onNext={list.next}
      onLimitChange={list.setLimit}
      busy={list.loading || !!list.failure}
      noun={noun}
    />
  );
}

type Option = { value: string; label: string; code?: string | null };
type IdentityReference = {
  id: string;
  company_id?: string;
  label?: string;
  bank_name?: string;
  account_number_last4?: string;
  tax_system?: string;
  jurisdiction_code?: string;
  number?: string | null;
  valid_from?: string;
};
async function referencePage(
  company: string,
  source: string,
  params: URLSearchParams,
  signal: AbortSignal,
) {
  if (source.startsWith('identity:')) {
    const resource = source.slice(9),
      value = params.get('value');
    const query = new URLSearchParams({ limit: params.get('limit') ?? '50' });
    if (params.get('cursor')) query.set('cursor', params.get('cursor')!);
    const result = await serviceCall<
      IdentityReference | ServicePage<IdentityReference>
    >(
      '/api/product-fields',
      {
        service: 'identity',
        path:
          `/v1/companies/${company}/${resource}` +
          (value ? '/' + value : '?' + query),
        signal,
      },
      'company reference',
    );
    const rows = 'items' in result ? result.items : [result];
    if (
      !Array.isArray(rows) ||
      rows.some(
        (row) => (row.company_id && row.company_id !== company) || !row.id,
      )
    )
      throw {
        status: 502,
        message: 'Company references could not be verified.',
      };
    return {
      items: rows
        .filter(
          (row) =>
            value ||
            !params.get('tax_system') ||
            row.tax_system === params.get('tax_system'),
        )
        .map((row) => ({
          value: row.id,
          label:
            row.label ??
            row.bank_name ??
            ([
              row.tax_system,
              row.jurisdiction_code,
              row.number ?? row.valid_from,
            ]
              .filter(Boolean)
              .join(' · ') ||
              'Reference details protected'),
          code: row.account_number_last4,
        })),
      page:
        'items' in result
          ? result.page
          : { limit: 1, has_more: false, next_cursor: null },
    };
  }
  if (source === 'catalog:tax-rules') {
    const value = params.get('value');
    if (value) {
      const row = await serviceCall<{
        id: string;
        company_id: string;
        code?: string;
        name?: string;
      }>(
        '/api/product-fields',
        {
          service: 'catalog',
          path: `/v1/companies/${company}/tax-rules/${value}`,
          signal,
        },
        'tax rule reference',
      );
      if (
        row.id !== value ||
        row.company_id !== company ||
        !row.code ||
        !row.name
      )
        throw {
          status: 403,
          message: 'The tax rule reference is unavailable or protected.',
        };
      return {
        items: [{ value: row.id, label: row.name, code: row.code }],
        page: { limit: 1, has_more: false, next_cursor: null },
      };
    }
    return serviceCall<ServicePage<Option>>(
      '/api/product-fields',
      {
        service: 'catalog',
        path: `/v1/companies/${company}/option-sources/catalog.tax_rules?${params}`,
        signal,
      },
      'tax rule reference',
    );
  }
  return accountingRequest<ServicePage<Option>>({
    path: `/v1/companies/${company}/configuration/options/${source}?${params}`,
    signal,
  });
}
export function AccountingReference({
  company,
  source,
  value,
  label,
  onChange,
  disabled,
  required,
  error,
  filters = '',
  returnTo,
  onLeave,
  linkLabel,
  allowedValues,
  hint,
}: {
  company: string;
  source: string;
  value: string | null;
  label: string;
  onChange: (value: string | null) => void;
  disabled?: boolean;
  required?: boolean;
  error?: string;
  filters?: string;
  returnTo?: string;
  onLeave?: React.MouseEventHandler<HTMLAnchorElement>;
  linkLabel?: string;
  allowedValues?: readonly string[] | null;
  hint?: string;
}) {
  const [selected, setSelected] = useState<SearchSelectOption | null>(null),
    [lookupError, setLookupError] = useState('');
  const load = useCallback<SearchSelectLoader>(
    async ({ q, cursor, signal }) => {
      const params = new URLSearchParams(filters);
      params.set('limit', '50');
      if (q.trim().length >= 2 && !source.startsWith('identity:'))
        params.set('q', q.trim());
      if (cursor) params.set('cursor', cursor);
      const result = await referencePage(company, source, params, signal);
      if (
        !Array.isArray(result.items) ||
        !result.page ||
        result.items.some(
          (row) =>
            typeof row.value !== 'string' || typeof row.label !== 'string',
        )
      )
        throw new Error('Invalid reference choices');
      const items = result.items
        .filter((row) => !allowedValues || allowedValues.includes(row.value))
        .map((row) => ({
          id: row.value,
          label: row.label,
          meta: row.code ?? undefined,
        }));
      return {
        items: source.startsWith('identity:')
          ? items.filter(
              (row) => !q || row.label.toLowerCase().includes(q.toLowerCase()),
            )
          : items,
        nextCursor: result.page.has_more ? result.page.next_cursor : null,
      };
    },
    [company, source, filters, allowedValues],
  );
  useEffect(() => {
    const controller = new AbortController();
    setSelected(null);
    setLookupError('');
    if (value) {
      const params = new URLSearchParams(filters);
      params.set('value', value);
      params.set('limit', '1');
      referencePage(company, source, params, controller.signal)
        .then((result) => {
          if (!controller.signal.aborted) {
            const option = result.items.find((row) => row.value === value);
            if (option)
              setSelected({
                id: option.value,
                label: option.label,
                meta: option.code ?? undefined,
              });
            else
              setLookupError(
                'This reference is unavailable. Choose an available reference or ask an administrator.',
              );
          }
        })
        .catch((problem) => {
          if (!controller.signal.aborted)
            setLookupError(
              requestFailure(problem, 'reference service').message,
            );
        });
    }
    return () => controller.abort();
  }, [company, source, value, filters]);
  const related =
    value && accountingUUID.test(value)
      ? accountingResource(source)
      : undefined;
  const relatedPath =
    value && accountingUUID.test(value)
      ? related
        ? '/accounting/' + source + '/' + value
        : source === 'catalog:tax-rules'
          ? '/tax/rules/' + value
          : undefined
      : undefined;
  return (
    <div className="janso-field">
      <SearchSelect
        label={label}
        value={value}
        selected={
          selected ??
          (value
            ? {
                id: value,
                label: lookupError
                  ? 'Reference unavailable'
                  : 'Loading reference…',
                disabled: true,
              }
            : null)
        }
        onChange={(next, option) => {
          setSelected(option);
          setLookupError('');
          onChange(next);
        }}
        loadOptions={load}
        scopeKey={
          company +
          ':' +
          source +
          ':' +
          filters +
          ':' +
          (allowedValues?.join(',') ?? '')
        }
        disabled={disabled}
        required={required}
        error={error ?? (lookupError || undefined)}
        minQueryLength={0}
        placeholder="Search and select…"
        clearable={!required}
        hint={hint}
      />
      {returnTo &&
        relatedPath &&
        value &&
        selected?.id === value &&
        !lookupError && (
          <a
            className="janso-link"
            href={accountingLink(relatedPath, returnTo)}
            onClick={onLeave}
          >
            {linkLabel ??
              'Open ' + (related?.singular.toLowerCase() ?? 'tax rule')}
          </a>
        )}
    </div>
  );
}
function FieldValue({
  field,
  value,
}: {
  field: AccountingField;
  value: unknown;
}) {
  const format = useFormatters();
  if (value === undefined) return <>Not readable</>;
  if (value === null || value === '') return <>Not set</>;
  return (
    <>
      {field.control.kind === 'date'
        ? format.date(String(value))
        : field.control.kind === 'datetime'
          ? format.dateTime(String(value))
          : typeof value === 'boolean'
            ? value
              ? 'Yes'
              : 'No'
            : field.control.kind === 'select'
              ? String(value).slice(0, 1) +
                String(value).slice(1).toLowerCase().replaceAll('_', ' ')
              : String(value)}
    </>
  );
}
function decimalHint(field: AccountingField) {
  const bounds = field.control.decimal_bounds ?? {};
  const labels: Record<string, string> = {
    minimum: 'Minimum ',
    maximum: 'Maximum ',
    exclusiveMinimum: 'Greater than ',
    exclusiveMaximum: 'Less than ',
  };
  return [
    'Exact decimal; up to four decimal places.',
    ...Object.entries(bounds).map(
      ([key, value]) => (labels[key] ?? '') + value + '.',
    ),
  ].join(' ');
}
export function AccountingFields({
  company,
  fields,
  values,
  onChange,
  disabled = false,
  errors = {},
  resource,
  returnTo,
  onLeave,
  readView = false,
}: {
  readView?: boolean;
  company: string;
  fields: AccountingField[];
  values: Record<string, unknown>;
  onChange: (key: string, value: unknown) => void;
  disabled?: boolean;
  errors?: Record<string, string>;
  resource: string;
  returnTo?: string;
  onLeave?: React.MouseEventHandler<HTMLAnchorElement>;
}) {
  const id = useId();
  return (
    <div className="janso-form-grid">
      {fields
        .filter(
          (field) =>
            field.visible && (field.readable || field.control.write_only),
        )
        .map((field) => {
          const value = values[field.key],
            active = accountingFieldActive(field, values),
            locked =
              disabled ||
              !field.editable ||
              !!field.control.disabled_reason ||
              !active,
            common = {
              label: field.label,
              disabled: locked,
              required:
                active &&
                (field.required || !!field.control.required_when_active),
              error: errors[field.key],
              hint:
                field.control.disabled_reason ??
                (!active
                  ? 'Available when ' +
                    Object.entries(field.control.depends_on ?? {})
                      .map(
                        ([key, choices]) =>
                          (fields.find((item) => item.key === key)?.label ??
                            key.replaceAll('_', ' ')) +
                          ' is ' +
                          choices
                            .map((choice) =>
                              choice.toLowerCase().replaceAll('_', ' '),
                            )
                            .join(' or '),
                      )
                      .join(' and ') +
                    '.'
                  : !disabled && field.editable && field.key === 'code'
                    ? String(accountingConstraints(field).description ?? ('Choose a unique code, up to ' +
                      (accountingConstraints(field).maxLength ?? 40) +
                        ' characters. It is fixed after creation.'))
                    : !disabled && field.editable && field.key === 'legal_name'
                      ? 'Use the legal registered name. The display name can be different.'
                      : !disabled &&
                          field.editable &&
                          field.key === 'group_id' &&
                          resource === 'accounts'
                        ? "Select an active group that matches this account's financial purpose."
                        : undefined),
            },
            control = field.control;
          if (readView && !control.reference)
            return (
              <div
                className={
                  ['notes', 'description'].includes(field.key)
                    ? 'janso-field janso-form-grid__full'
                    : 'janso-field'
                }
                key={field.key}
              >
                <span className="janso-label">{field.label}</span>
                <p className="console-audit-detail__value">
                  <FieldValue field={field} value={value} />
                </p>
              </div>
            );
          if (control.reference) {
            const filter = new URLSearchParams(control.reference_filters ?? {});
            if (
              resource === 'account-tax-profiles' &&
              control.reference === 'identity:tax-registrations' &&
              ['GST_IN', 'VAT'].includes(String(values.scheme))
            )
              filter.set(
                'tax_system',
                values.scheme === 'GST_IN' ? 'gst_in' : 'vat',
              );
            if (
              resource === 'accounts' &&
              control.reference === 'parties' &&
              values.party_role
            )
              filter.set('role', String(values.party_role));
            if (control.reference === 'withholding-sections' && values.kind)
              filter.set('kind', String(values.kind));
            if (
              [
                'party-addresses',
                'party-contacts',
                'party-identifiers',
                'party-tax-registrations',
              ].includes(control.reference) &&
              values.party_id
            )
              filter.set('party_id', String(values.party_id));
            if (control.reference === 'states' && values.country_code)
              filter.set('country_code', String(values.country_code));
            if (
              field.editable &&
              (control.reference === 'account-groups' ||
                control.reference === 'payment-terms' ||
                control.reference === 'parties')
            )
              filter.set('status', 'ACTIVE');
            if (
              control.reference === 'accounts' &&
              field.editable &&
              ['account-bank-profiles', 'account-tax-profiles'].includes(
                resource,
              )
            )
              filter.set('status', 'DRAFT');
            if (
              resource === 'charge-policies' &&
              field.editable &&
              control.reference === 'accounts'
            ) {
              filter.set('status', 'ACTIVE');
              filter.set(
                'kind',
                field.key === 'account_id' ? 'PARTY' : 'GENERAL',
              );
              if (field.key === 'offset_account_id')
                filter.set('currency_mode', 'BASE');
            }
            return (
              <AccountingReference
                key={field.key}
                company={company}
                source={control.reference}
                value={typeof value === 'string' && value ? value : null}
                {...common}
                disabled={
                  locked ||
                  (control.reference === 'states' && !values.country_code)
                }
                filters={filter.toString()}
                allowedValues={control.reference_values}
                onChange={(next) => onChange(field.key, next)}
                returnTo={returnTo}
                onLeave={onLeave}
                linkLabel={'Open ' + field.label.toLowerCase()}
              />
            );
          }
          if (control.kind === 'select' || control.kind === 'boolean')
            return (
              <Select
                key={field.key}
                {...common}
                value={value == null ? '' : String(value)}
                placeholder="Choose…"
                options={[
                  ...(control.nullable
                    ? [{ value: '', label: 'Not set' }]
                    : []),
                  ...(control.kind === 'boolean'
                    ? [
                        { value: 'true', label: 'Yes' },
                        { value: 'false', label: 'No' },
                      ]
                    : accountingChoices(field, values).map((choice) => ({
                        value: choice,
                        label:
                          choice.charAt(0) +
                          choice.slice(1).toLowerCase().replaceAll('_', ' '),
                      }))),
                  ...(control.kind === 'select' &&
                  value != null &&
                  value !== '' &&
                  !accountingChoices(field, values).includes(String(value))
                    ? [
                        {
                          value: String(value),
                          label:
                            String(value).charAt(0) +
                            String(value)
                              .slice(1)
                              .toLowerCase()
                              .replaceAll('_', ' ') +
                            ' (unavailable for new selection)',
                          disabled: true,
                        },
                      ]
                    : []),
                ]}
                onChange={(next) =>
                  onChange(
                    field.key,
                    next === '' && control.nullable
                      ? null
                      : control.kind === 'boolean'
                        ? next === 'true'
                        : next,
                  )
                }
              />
            );
          if (!field.editable && !control.write_only)
            return (
              <div className="janso-field" key={field.key}>
                <span className="janso-label">{field.label}</span>
                <p className="console-audit-detail__value">
                  <FieldValue field={field} value={value} />
                </p>
              </div>
            );
          const definition = accountingConstraints(field) as {
            maxLength?: number;
          };
          if (
            control.kind === 'text' &&
            (definition.maxLength ?? 0) >= 500 &&
            !control.write_only
          )
            return (
              <div
                className="janso-field janso-form-grid__full"
                key={field.key}
              >
                <label className="janso-label" htmlFor={id + field.key}>
                  {field.label}
                </label>
                <textarea
                  id={id + field.key}
                  className="janso-input"
                  rows={4}
                  disabled={locked}
                  required={field.required}
                  value={String(value ?? '')}
                  maxLength={definition.maxLength}
                  aria-invalid={!!errors[field.key]}
                  aria-describedby={
                    [
                      common.hint ? id + field.key + '-hint' : '',
                      errors[field.key] ? id + field.key + '-error' : '',
                    ]
                      .filter(Boolean)
                      .join(' ') || undefined
                  }
                  onChange={(event) => onChange(field.key, event.target.value)}
                />
                {common.hint && (
                  <p id={id + field.key + '-hint'} className="janso-hint">
                    {common.hint}
                  </p>
                )}
                {errors[field.key] && (
                  <p
                    id={id + field.key + '-error'}
                    className="janso-error"
                    role="alert"
                  >
                    {errors[field.key]}
                  </p>
                )}
              </div>
            );
          const masterCode = field.key === 'code' && ['accounts', 'parties'].includes(resource);
          return (
            <TextField
              key={field.key}
              {...common}
              type={
                control.write_only
                  ? 'password'
                  : control.kind === 'date'
                    ? 'date'
                    : 'text'
              }
              inputMode={
                control.kind === 'decimal'
                  ? 'decimal'
                  : control.kind === 'integer'
                    ? 'numeric'
                    : undefined
              }
              autoComplete={control.write_only ? 'off' : undefined}
              value={String(value ?? '')}
              maxLength={masterCode && definition.maxLength ? definition.maxLength * 2 : definition.maxLength}
              hint={
                common.hint ??
                (control.write_only
                  ? 'Stored securely. When editing, leave empty to keep the existing number.'
                  : control.kind === 'decimal'
                    ? decimalHint(field)
                    : control.kind === 'datetime'
                      ? 'UTC date/time, for example 2026-10-25T00:00:00Z.'
                      : undefined)
              }
              onChange={(event) => onChange(
                field.key,
                masterCode ? limitMasterCode(event.target.value, definition.maxLength ?? 40)
                  : resource === 'party-tax-registrations' && field.key === 'registration_number'
                  && values.scheme === 'GST_IN'
                  ? cleanGstin(event.target.value)
                  : event.target.value,
              )}
            />
          );
        })}
    </div>
  );
}
export function AccountingSections({
  withinForm = false,
  ...props
}: React.ComponentProps<typeof AccountingFields> & { withinForm?: boolean }) {
  return (
    <>
      {accountingFieldSections(props.fields, props.resource).map((section) =>
        withinForm ? (
          <section
            key={section.title}
            className="janso-flow"
            aria-label={section.title}
          >
            <SectionHeader title={section.title} />
            <AccountingFields {...props} fields={section.fields} />
          </section>
        ) : (
          <Card key={section.title}>
            <CardHeader title={section.title} />
            <CardBody>
              <AccountingFields {...props} fields={section.fields} />
            </CardBody>
          </Card>
        ),
      )}
    </>
  );
}
