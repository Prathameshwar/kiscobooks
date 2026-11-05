'use client';
import { useEffect, useRef, useState } from 'react';
import {
  Button,
  Card,
  CardBody,
  ConfirmDialog,
  FormActions,
  FormLayout,
  Notice,
  PageHeader,
  SectionHeader,
} from '@janso/ui';
import {
  assertMaster,
  masterRequest,
  useMasterRecord,
} from '../lib/catalog-master-api';
import type { MasterConfig, MasterRow } from '../lib/catalog-masters';
import { useServiceCommand, useServiceRead } from '../lib/service-resource';
import {
  attributeBase,
  attributeEditKeys,
  attributeBody,
  attributeId,
  attributeLink,
  attributeReceipt,
  attributeReturn,
  attributeVisible,
  attributeWritable,
} from '../lib/attribute-masters';
import type { AttributeAccess } from '../lib/attribute-resources';
import { useAccessDraft } from './AccessCommon';
import {
  AttributeFailure,
  AttributeField,
  AttributeNavigation,
  AttributeReference,
} from './AttributeMasterCommon';
export function AttributeMasterEditor({
  company,
  config,
  id,
  returnTo,
  definitionId,
  access,
}: {
  company: string;
  config: MasterConfig;
  id?: string;
  returnTo?: string;
  definitionId?: string;
  access: AttributeAccess;
}) {
  const root = '/masters/' + config.resource,
    back = attributeReturn(returnTo, id ? root + '/' + id : root),
    option = config.resource === 'attribute-options',
    record = useMasterRecord(company, config, id, true);
  const [values, setValues] = useState<Record<string, unknown>>({}),
    [initialized, setInitialized] = useState(false),
    [dirty, setDirty] = useState(false),
    [saved, setSaved] = useState<MasterRow | null>(null),
    [errors, setErrors] = useState<Record<string, string>>({}),
    [frozen, setFrozen] = useState<Record<string, unknown> | null>(null),
    [reload, setReload] = useState(false),
    [unchanged, setUnchanged] = useState(false);
  const command = useServiceCommand(masterRequest, 'attribute masters'),
    guard = useAccessDraft(dirty || command.uncertain, command.pending),
    form = useRef<HTMLFormElement>(null);
  useEffect(() => {
    if (record.loading || (id && !record.row)) {
      setInitialized(false);
      return;
    }
    setValues({
      ...config.initial,
      is_active: true,
      ...(definitionId && !id ? { definition_id: definitionId } : {}),
      ...(record.row ?? {}),
    });
    setDirty(false);
    setErrors({});
    setFrozen(null);
    setSaved(null);
    setInitialized(true);
  }, [config, id, definitionId, record.row, record.loading]);
  const selectedDefinition =
    option &&
    attributeVisible(record.fields, 'definition_id') &&
    typeof values.definition_id === 'string' &&
    attributeId.test(values.definition_id)
      ? values.definition_id
      : undefined;
  const definition = useServiceRead<MasterRow>(
    selectedDefinition && access['attribute-definitions']
      ? attributeBase(company, 'attribute-definitions/' + selectedDefinition)
      : undefined,
    masterRequest,
    (row) => assertMaster(row, company, selectedDefinition),
  );
  const type = option
      ? id
        ? record.row?.value_type
        : definition.data?.value_type
      : values.value_type,
    typedKey = 'value_' + String(type).toLowerCase(),
    measured = !!definition.data?.measurement_dimension;
  const fields = record.fields,
    visible = (key: string) => attributeVisible(fields, key);
  const createKeys = [
    'code',
    'name',
    'is_active',
    ...(option
      ? ['definition_id', 'value_type', ...(type ? [typedKey] : [])]
      : config.resource === 'attribute-definitions'
        ? ['value_type', 'is_variant_capable']
        : []),
  ];
  const complete = id
    ? visible('row_version') &&
      attributeEditKeys(config.resource, record.row).some(
        (key) =>
          attributeWritable(fields, [key]) &&
          (key !== 'unit_id' || access.units),
      )
    : visible('row_version') &&
      attributeWritable(fields, createKeys) &&
      (!option ||
        (!!definition.data &&
          definition.data.is_active === true &&
          ['value_type', 'measurement_dimension', 'is_active'].every(
            (key) => key in definition.data!,
          ) &&
          (!measured ||
            (access.units && attributeWritable(fields, ['unit_id'])))));
  const loading =
      record.loading || (!initialized && !record.failure) || definition.loading,
    failure = record.failure ?? definition.failure,
    locked = command.pending || command.uncertain;
  useEffect(() => {
    if (command.failure?.fields) setErrors(command.failure.fields);
  }, [command.failure]);
  useEffect(() => {
    if (Object.keys(errors).length && !command.pending)
      form.current
        ?.querySelector<HTMLElement>('[aria-invalid="true"]')
        ?.focus();
  }, [errors, command.pending]);
  function change(key: string, value: unknown) {
    if (!id && command.failure?.status === 409) command.clear();
    setValues((current) => ({
      ...current,
      [key]: value,
      ...(key === 'value_type'
        ? { measurement_dimension: null }
        : key === 'definition_id'
          ? {
              value_text: null,
              value_integer: null,
              value_decimal: null,
              value_boolean: null,
              value_date: null,
              unit_id: null,
            }
          : {}),
    }));
    setDirty(true);
    setErrors({});
    setUnchanged(false);
  }
  async function submit() {
    if (
      !complete ||
      loading ||
      failure ||
      saved ||
      command.pending ||
      (command.blocked && !command.uncertain)
    )
      return;
    const draft = attributeBody(
      config,
      fields,
      values,
      record.row ?? undefined,
      definition.data,
    );
    setErrors(draft.errors);
    if (Object.keys(draft.errors).length) return;
    if (id && Object.keys(draft.body).length === 1) {
      setDirty(false);
      setUnchanged(true);
      return;
    }
    const body = command.uncertain && frozen ? frozen : draft.body;
    setFrozen(body);
    const result = await command.execute<MasterRow>(
      {
        path: attributeBase(company, config.resource) + (id ? '/' + id : ''),
        method: id ? 'PATCH' : 'POST',
        body,
      },
      (row) =>
        attributeReceipt(
          row,
          company,
          id,
          id ? record.row?.row_version : undefined,
        ),
    );
    if (result) {
      setSaved(result);
      setDirty(false);
      setErrors({});
    }
  }
  const shownFields = fields.filter(
    (field) =>
      field.control &&
      visible(field.key) &&
      !['row_version', 'definition_id', 'unit_id'].includes(field.key) &&
      (!option || !field.key.startsWith('value_') || field.key === typedKey) &&
      (!option || field.key !== 'value_type') &&
      (field.key !== 'measurement_dimension' ||
        ['INTEGER', 'DECIMAL'].includes(String(type)) ||
        !!id),
  );
  const title = (id ? 'Edit ' : 'New ') + config.singular;
  return (
    <div className="janso-page">
      <AttributeNavigation
        title={title}
        back={back}
        access={access}
        onLeave={guard.leave}
      />
      <PageHeader
        title={title}
        lede="Required fields are marked. Changes apply to the company currently open."
      />
      <AttributeFailure
        failure={failure}
        retry={() => {
          record.refresh();
          definition.refresh();
        }}
      />
      {!id && command.failure?.status === 409 ? (
        <Notice tone="danger">
          <p>{command.failure.message}</p>
          <p>
            Your inputs are retained. Correct duplicate values and save again,
            or reload to review changed dependencies.
          </p>
          <Button type="button" variant="ghost" onClick={() => setReload(true)}>
            Reload and review
          </Button>
        </Notice>
      ) : (
        <AttributeFailure
          failure={command.failure}
          write
          retry={
            command.failure?.status === 409 ? () => setReload(true) : undefined
          }
        />
      )}
      {unchanged && <Notice>No changes to save.</Notice>}
      {loading ? (
        <p role="status">Loading {config.singular} form...</p>
      ) : failure ? null : saved ? (
        <Card>
          <CardBody>
            <Notice tone="success">
              {config.singular} {id ? 'updated' : 'created'} successfully.
            </Notice>
            <div className="janso-flow">
              <a
                className="janso-btn janso-btn--primary"
                href={attributeLink(root + '/' + saved.id, back)}
              >
                View {config.singular}
              </a>
              <a className="janso-link" href={back}>
                Return to previous page
              </a>
              {!id && (
                <a
                  className="janso-link"
                  href={attributeLink(root + '/new', back)}
                >
                  Create another
                </a>
              )}
            </div>
          </CardBody>
        </Card>
      ) : (
        <FormLayout
          aside={
            <>
              <SectionHeader title="Before you save" />
              <p className="janso-fine">
                Definitions describe a value type. Options are distinct typed
                choices for one definition. Templates collect definitions into
                reusable requirements. Referenced semantics are protected by the
                service.
              </p>
              {!complete && (
                <Notice tone="warning">
                  The required fields or definition/unit read access are
                  unavailable. Choose a definition or ask an administrator to
                  review access.
                </Notice>
              )}
            </>
          }
        >
          <form
            noValidate
            ref={form}
            onSubmit={(event) => {
              event.preventDefault();
              void submit();
            }}
          >
            <Card>
              <CardBody>
                <SectionHeader title="Details" />
                <div className="janso-form-grid">
                  {option &&
                    visible('definition_id') &&
                    access['attribute-definitions'] && (
                      <AttributeReference
                        company={company}
                        label="Definition"
                        name="definition_id"
                        required
                        value={selectedDefinition ?? null}
                        disabled={
                          locked ||
                          !!id ||
                          !attributeWritable(fields, ['definition_id'])
                        }
                        error={errors.definition_id}
                        onChange={(value) => change('definition_id', value)}
                      />
                    )}
                  {option && !!type && (
                    <Notice>
                      Value type: {String(type)}
                      {measured
                        ? ' · ' + String(definition.data?.measurement_dimension)
                        : ''}
                      .{' '}
                      {id
                        ? 'Definition and value type remain fixed.'
                        : 'Enter one value for this definition.'}
                    </Notice>
                  )}
                  {shownFields.map((field) => (
                    <AttributeField
                      key={field.key}
                      company={company}
                      field={field}
                      value={values[field.key]}
                      disabled={
                        locked ||
                        (field.key === 'measurement_dimension' &&
                          !['INTEGER', 'DECIMAL'].includes(String(type)))
                      }
                      error={errors[field.key]}
                      onChange={(value) =>
                        change(
                          field.key,
                          field.key === 'measurement_dimension'
                            ? value || null
                            : value,
                        )
                      }
                    />
                  ))}
                  {option &&
                    (measured || !!record.row?.unit_id) &&
                    visible('unit_id') &&
                    access.units && (
                      <AttributeReference
                        company={company}
                        resource="units"
                        label="Measurement unit"
                        name="unit_id"
                        required
                        value={
                          typeof values.unit_id === 'string'
                            ? values.unit_id
                            : null
                        }
                        dimension={
                          typeof definition.data?.measurement_dimension ===
                          'string'
                            ? definition.data.measurement_dimension
                            : undefined
                        }
                        disabled={
                          locked || !attributeWritable(fields, ['unit_id'])
                        }
                        error={errors.unit_id}
                        onChange={(value) => change('unit_id', value)}
                      />
                    )}
                </div>
                {Object.entries(errors)
                  .filter(
                    ([key]) =>
                      !shownFields.some((field) => field.key === key) &&
                      !(
                        key === 'definition_id' &&
                        option &&
                        visible(key) &&
                        access['attribute-definitions']
                      ) &&
                      !(
                        key === 'unit_id' &&
                        option &&
                        (measured || !!record.row?.unit_id) &&
                        visible(key) &&
                        access.units
                      ),
                  )
                  .map(([key, message]) => (
                    <Notice key={key} tone="danger">
                      {message}
                    </Notice>
                  ))}
              </CardBody>
              <FormActions cancel={{ href: back, onClick: guard.leave }}>
                <Button
                  type="submit"
                  loading={command.pending}
                  disabled={
                    !complete || (command.blocked && !command.uncertain)
                  }
                >
                  {command.uncertain
                    ? 'Retry same save'
                    : id
                      ? 'Save changes'
                      : 'Create ' + config.singular}
                </Button>
              </FormActions>
            </Card>
          </form>
        </FormLayout>
      )}
      <ConfirmDialog
        open={reload}
        title="Reload current definition?"
        confirmLabel="Reload and review"
        onCancel={() => setReload(false)}
        onConfirm={() => {
          setReload(false);
          command.clear();
          record.refresh();
          definition.refresh();
        }}
      >
        Unsaved values will be replaced with the current record.
      </ConfirmDialog>
      {guard.confirmation}
    </div>
  );
}
