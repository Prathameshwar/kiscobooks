'use client';
import { useEffect, useRef, useState } from 'react';
import {
  Button,
  Card,
  CardBody,
  ConfirmDialog,
  CustomFields,
  FormActions,
  FormLayout,
  Notice,
  PageHeader,
  Select,
  TextField,
  businessToday,
  useDisplayConfig,
} from '@janso/ui';
import { useMasterRecord, masterRequest } from '../lib/catalog-master-api';
import {
  masterCustomFields,
  type MasterConfig,
  type MasterRow,
} from '../lib/catalog-masters';
import {
  canEditPricing,
  pricingBase,
  pricingBody,
  pricingCommand,
  pricingLink,
  pricingPurposes,
  pricingReceipt,
  pricingReturn,
  pricingVisible,
  pricingWritable,
} from '../lib/pricing-masters';
import type { PricingAccess } from '../lib/pricing-resources';
import { useServiceCommand } from '../lib/service-resource';
import { useAccessDraft } from './AccessCommon';
import {
  PricingCurrency,
  PricingFailure,
  PricingField,
  PricingLevelReference,
  PricingMasterExplanation,
  PricingNavigation,
} from './PricingMasterCommon';
export function PricingMasterEditor({
  company,
  config,
  id,
  returnTo,
  access,
}: {
  company: string;
  config: MasterConfig;
  id?: string;
  returnTo?: string;
  access: PricingAccess;
}) {
  const root = '/masters/' + config.resource,
    back = pricingReturn(returnTo, id ? root + '/' + id : root),
    record = useMasterRecord(company, config, id, true),
    display = useDisplayConfig();
  const [values, setValues] = useState<Record<string, unknown>>({}),
    [initialized, setInitialized] = useState(false),
    [dirty, setDirty] = useState(false),
    [errors, setErrors] = useState<Record<string, string>>({}),
    [saved, setSaved] = useState<MasterRow | null>(null),
    [frozen, setFrozen] = useState<Record<string, unknown> | null>(null),
    [reload, setReload] = useState(false),
    [unchanged, setUnchanged] = useState(false);
  const command = useServiceCommand(pricingCommand, 'pricing master service'),
    guard = useAccessDraft(dirty || command.uncertain, command.pending),
    form = useRef<HTMLFormElement>(null);
  const plans = config.resource === 'price-plans',
    levels = config.resource === 'price-levels',
    fields = record.fields.map((field) => ({
      ...field,
      writable: field.writable && !field.conditional_access,
    })),
    visible = (key: string) => pricingVisible(fields, key);
  useEffect(() => {
    if (record.loading || (id && !record.row)) {
      setInitialized(false);
      return;
    }
    setValues({
      ...config.initial,
      ...(plans && !id ? { currency: display.currency ?? '' } : {}),
      ...(record.row ?? {}),
    });
    setErrors({});
    setDirty(false);
    setFrozen(null);
    setSaved(null);
    setInitialized(true);
    setUnchanged(false);
  }, [config, id, record.row, record.loading, display.currency]);
  useEffect(() => {
    if (command.failure?.fields) setErrors(command.failure.fields);
  }, [command.failure]);
  useEffect(() => {
    if (Object.keys(errors).length && !command.pending)
      form.current
        ?.querySelector<HTMLElement>('[aria-invalid="true"]')
        ?.focus();
  }, [errors, command.pending]);
  const purchaseAllowed =
    !plans ||
    values.purpose !== 'PURCHASE' ||
    (access.purchaseRead && access.purchaseManage);
  const complete =
    purchaseAllowed &&
    (id
      ? canEditPricing(config, fields, record.row, access)
      : visible('row_version') &&
        pricingWritable(fields, [
          'code',
          'name',
          ...(levels
            ? ['ordinal', 'is_active']
            : plans
              ? ['purpose', 'price_level_id', 'currency', 'tax_basis']
              : ['is_active']),
        ]) &&
        (!plans || values.purpose !== 'SALE' || access['price-levels']));
  const locked = command.pending || command.uncertain;
  function change(key: string, value: unknown) {
    if (!id && command.failure?.status === 409) command.clear();
    setValues((current) => ({
      ...current,
      [key]: value,
      ...(key === 'purpose' && value !== 'SALE'
        ? { price_level_id: null }
        : {}),
    }));
    setDirty(true);
    setErrors({});
    setUnchanged(false);
  }
  async function submit() {
    if (
      !complete ||
      record.loading ||
      !initialized ||
      record.failure ||
      saved ||
      command.pending ||
      (command.blocked && !command.uncertain)
    )
      return;
    const draft = pricingBody(config, fields, values, record.row ?? undefined);
    setErrors(draft.errors);
    if (Object.keys(draft.errors).length) return;
    if (
      id &&
      !Object.entries(draft.body).some(
        ([key, value]) =>
          key !== 'expected_version' &&
          (key === 'custom_fields'
            ? Object.keys(value as object).length > 0
            : JSON.stringify(value) !== JSON.stringify(record.row?.[key])),
      )
    ) {
      setDirty(false);
      setUnchanged(true);
      return;
    }
    const body = command.uncertain && frozen ? frozen : draft.body;
    setFrozen(body);
    const result = await command.execute<MasterRow>(
      {
        path: pricingBase(company, config.resource) + (id ? '/' + id : ''),
        method: id ? 'PATCH' : 'POST',
        body,
      },
      (row) => pricingReceipt(row, company, id, record.row?.row_version),
    );
    if (result) {
      setSaved(result);
      setDirty(false);
      setFrozen(null);
    }
  }
  return (
    <div className="janso-page">
      <PricingNavigation
        title={(id ? 'Edit ' : 'New ') + config.singular}
        back={back}
        access={access}
        onLeave={guard.leave}
      />
      <PageHeader
        title={(id ? 'Edit ' : 'New ') + config.singular}
        lede="Changes apply to the company currently open."
      />
      <PricingMasterExplanation resource={config.resource} />
      <PricingFailure failure={record.failure} retry={record.refresh} />
      <PricingFailure
        failure={
          command.failure?.status === 409 && !id ? null : command.failure
        }
        uncertain={command.uncertain}
      />
      {!id && command.failure?.status === 409 && (
        <Notice tone="danger">
          {command.failure.message} Correct duplicate details or review the
          company settings, then try again. Your values are retained.
        </Notice>
      )}
      {command.failure && !command.uncertain && id && (
        <Button type="button" variant="ghost" onClick={() => setReload(true)}>
          Reload and review
        </Button>
      )}
      {command.uncertain && (
        <Button type="button" disabled={command.pending} onClick={submit}>
          Retry same save
        </Button>
      )}
      {saved && (
        <Notice tone="success">
          {config.singular} {id ? 'updated' : 'created'} successfully.{' '}
          <a
            className="janso-link"
            href={pricingLink(root + '/' + saved.id, back)}
          >
            View {config.singular}
          </a>
        </Notice>
      )}
      {unchanged && <Notice>No changes to save.</Notice>}
      {record.loading || (!initialized && !record.failure) ? (
        <p role="status">Loading pricing master…</p>
      ) : (
        !record.failure &&
        !saved && (
          <FormLayout>
            <form
              ref={form}
              noValidate
              onSubmit={(event) => {
                event.preventDefault();
                void submit();
              }}
            >
              <Card>
                <CardBody>
                  <div className="janso-form-grid">
                    {!complete && (
                      <Notice tone="warning">
                        The required fields or pricing permissions are
                        unavailable. Check your access and company settings
                        before saving.
                      </Notice>
                    )}
                    {fields
                      .filter(
                        (field) =>
                          field.source === 'native' &&
                          visible(field.key) &&
                          [
                            'code',
                            'name',
                            ...(levels ? ['ordinal'] : []),
                          ].includes(field.key),
                      )
                      .map((field) => (
                        <PricingField
                          key={field.key}
                          company={company}
                          field={field}
                          value={values[field.key]}
                          disabled={locked}
                          error={errors[field.key]}
                          onChange={(value) => change(field.key, value)}
                        />
                      ))}
                    {plans &&
                      visible('purpose') &&
                      (id ? (
                        <TextField
                          label="Purpose"
                          value={
                            pricingPurposes.find(
                              (purpose) => purpose.value === values.purpose,
                            )?.label ?? String(values.purpose ?? 'Protected')
                          }
                          disabled
                        />
                      ) : (
                        <Select
                          label="Purpose"
                          name="purpose"
                          required
                          disabled={
                            locked || !pricingWritable(fields, ['purpose'])
                          }
                          value={String(values.purpose ?? '')}
                          options={pricingPurposes.filter(
                            (purpose) =>
                              purpose.value !== 'PURCHASE' ||
                              (access.purchaseRead && access.purchaseManage),
                          )}
                          error={errors.purpose}
                          onChange={(value) => change('purpose', value)}
                        />
                      ))}
                    {plans &&
                      visible('price_level_id') &&
                      values.purpose === 'SALE' &&
                      (id ? (
                        <PricingLevelReference
                          company={company}
                          value={
                            typeof values.price_level_id === 'string'
                              ? values.price_level_id
                              : null
                          }
                          disabled
                          activeOnly={false}
                          onChange={() => undefined}
                        />
                      ) : access['price-levels'] ? (
                        <PricingLevelReference
                          company={company}
                          value={
                            typeof values.price_level_id === 'string'
                              ? values.price_level_id
                              : null
                          }
                          required
                          disabled={
                            locked ||
                            !pricingWritable(fields, ['price_level_id'])
                          }
                          error={errors.price_level_id}
                          onChange={(value) => change('price_level_id', value)}
                        />
                      ) : (
                        <Notice tone="warning">
                          Price level read access is required to choose a sales
                          level.
                        </Notice>
                      ))}
                    {plans &&
                      visible('currency') &&
                      (id ? (
                        <TextField
                          label="Currency"
                          value={String(values.currency ?? 'Protected')}
                          disabled
                        />
                      ) : (
                        <PricingCurrency
                          company={company}
                          value={
                            typeof values.currency === 'string'
                              ? values.currency
                              : null
                          }
                          required
                          disabled={
                            locked || !pricingWritable(fields, ['currency'])
                          }
                          error={errors.currency}
                          onChange={(value) => change('currency', value)}
                        />
                      ))}
                    {plans &&
                      fields
                        .filter((field) => field.key === 'tax_basis')
                        .map((field) => (
                          <PricingField
                            key={field.key}
                            company={company}
                            field={field}
                            value={values[field.key]}
                            disabled={locked}
                            error={errors[field.key]}
                            onChange={(value) => change(field.key, value)}
                          />
                        ))}
                    {plans && (
                      <CustomFields
                        fields={masterCustomFields(fields)}
                        values={
                          (values.custom_fields as Record<string, unknown>) ??
                          {}
                        }
                        nativeValues={values}
                        creating={!id}
                        disabled={locked}
                        currencies={
                          typeof values.currency === 'string'
                            ? [values.currency]
                            : []
                        }
                        errors={errors}
                        onChange={(value) => change('custom_fields', value)}
                        loadOptions={(source, parent) =>
                          async ({ q, cursor, signal }) => {
                            const params = new URLSearchParams({
                              limit: '50',
                              as_of: businessToday(display.timezone),
                            });
                            if (q.trim().length >= 2) params.set('q', q.trim());
                            if (cursor) params.set('cursor', cursor);
                            if (parent) params.set('parent_id', parent);
                            const result = await masterRequest<{
                              items: {
                                value: string;
                                label: string;
                                code: string;
                              }[];
                              page: {
                                has_more: boolean;
                                next_cursor: string | null;
                              };
                            }>({
                              path:
                                pricingBase(
                                  company,
                                  'option-sources/' +
                                    encodeURIComponent(source),
                                ) +
                                '?' +
                                params,
                              signal,
                            });
                            return {
                              items: result.items.map((option) => ({
                                id: option.value,
                                label: option.label,
                                meta: option.code,
                              })),
                              nextCursor: result.page.has_more
                                ? result.page.next_cursor
                                : null,
                            };
                          }}
                      />
                    )}
                    {Object.entries(errors)
                      .filter(
                        ([key]) =>
                          !fields.some(
                            (field) => field.key === key && visible(key),
                          ) && !key.startsWith('custom_fields.'),
                      )
                      .map(([key, error]) => (
                        <Notice key={key} tone="danger">
                          {error}
                        </Notice>
                      ))}
                  </div>
                </CardBody>
                <FormActions cancel={{ href: back, onClick: guard.leave }}>
                  <Button
                    type="submit"
                    disabled={!complete || locked || command.blocked}
                    loading={command.pending}
                    loadingLabel="Saving…"
                  >
                    {id ? 'Save changes' : 'Create ' + config.singular}
                  </Button>
                </FormActions>
              </Card>
            </form>
          </FormLayout>
        )
      )}
      <ConfirmDialog
        open={reload}
        title="Discard unsaved changes and reload?"
        confirmLabel="Discard and reload"
        onCancel={() => setReload(false)}
        onConfirm={() => {
          setReload(false);
          command.clear();
          record.refresh();
        }}
      >
        Reloading replaces your draft with the latest saved values.
      </ConfirmDialog>
      {guard.confirmation}
    </div>
  );
}
