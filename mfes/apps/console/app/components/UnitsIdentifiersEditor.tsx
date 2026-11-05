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
import { masterRequest, useMasterRecord } from '../lib/catalog-master-api';
import type { MasterConfig, MasterRow } from '../lib/catalog-masters';
import {
  identifierBase,
  identifierBody,
  identifierLink,
  identifierReceipt,
  identifierReturn,
  identifierVisible,
  identifierWritable,
  initialRequirement,
  reducedRatio,
  useIdentifierFields,
} from '../lib/units-identifiers';
import { useServiceCommand } from '../lib/service-resource';
import { useAccessDraft } from './AccessCommon';
import {
  IdentifierFailure,
  IdentifierField,
  IdentifierNavigation,
  type IdentifierAccess,
} from './UnitsIdentifiersCommon';

export function UnitsIdentifiersEditor({
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
  access: IdentifierAccess;
}) {
  const root = '/masters/' + config.resource,
    back = identifierReturn(returnTo, id ? root + '/' + id : root),
    conversion = config.resource === 'unit-conversions',
    profile = config.resource === 'identifier-profiles';
  const record = useMasterRecord(company, config, id, true),
    child = useIdentifierFields(
      company,
      'catalog.identifier_profile_requirement',
      'create',
      profile && !id,
    );
  const [values, setValues] = useState<Record<string, unknown>>({}),
    [requirements, setRequirements] = useState<Record<string, unknown>[]>([
      initialRequirement(),
    ]),
    [errors, setErrors] = useState<Record<string, string>>({}),
    [dirty, setDirty] = useState(false),
    [saved, setSaved] = useState<MasterRow | null>(null),
    [frozen, setFrozen] = useState<Record<string, unknown> | null>(null),
    [reload, setReload] = useState(false),
    [unchanged, setUnchanged] = useState(false),
    [initialized, setInitialized] = useState(false);
  const command = useServiceCommand(masterRequest, 'units and identifiers'),
    guard = useAccessDraft(dirty || command.uncertain, command.pending),
    form = useRef<HTMLFormElement>(null);
  useEffect(() => {
    if (record.loading || (id && !record.row)) {
      setInitialized(false);
      return;
    }
    setValues({ ...config.initial, is_active: true, ...(record.row ?? {}) });
    setRequirements([initialRequirement()]);
    setDirty(false);
    setErrors({});
    setFrozen(null);
    setSaved(null);
    setInitialized(true);
  }, [config, id, record.row, record.loading]);
  useEffect(() => {
    if (command.failure?.fields) setErrors(command.failure.fields);
  }, [command.failure]);
  useEffect(() => {
    if (Object.keys(errors).length && !command.pending)
      form.current
        ?.querySelector<HTMLElement>('[aria-invalid="true"]')
        ?.focus();
  }, [errors, command.pending]);
  const fields = record.fields,
    failure = record.failure ?? child.failure,
    loading = record.loading || child.loading || (!initialized && !failure);
  const editable =
    config.resource === 'identifier-types' ||
    config.resource === 'identifier-namespaces'
      ? ['name']
      : ['code', 'name'];
  const complete = id
    ? identifierVisible(fields, 'row_version') &&
      editable.some((key) => identifierWritable(fields, [key]))
    : identifierWritable(
        fields,
        conversion
          ? ['from_unit_id', 'canonical_unit_id', 'numerator', 'denominator']
          : [
              'code',
              'name',
              'is_active',
              ...(config.resource === 'identifier-types' ? ['is_barcode'] : []),
            ],
      ) &&
      (conversion ? access.units : identifierVisible(fields, 'row_version')) &&
      (!profile ||
        identifierWritable(child.data?.fields ?? [], [
          'identifier_type',
          'namespace_rule',
          'min_count',
          'max_count',
          'requires_slot',
        ]));
  function change(key: string, value: unknown) {
    setValues((current) => ({ ...current, [key]: value }));
    setDirty(true);
    setErrors({});
    setUnchanged(false);
  }
  function changeRequirement(index: number, key: string, value: unknown) {
    setRequirements((rows) =>
      rows.map((row, current) =>
        current === index ? { ...row, [key]: value } : row,
      ),
    );
    setDirty(true);
    setErrors({});
  }
  function hasErrorControl(key: string) {
    if (
      fields.some(
        (field) =>
          field.key === key &&
          field.source === 'native' &&
          field.visible &&
          !field.conditional_access &&
          field.control,
      )
    )
      return true;
    const match =
      /^requirements\.(\d+)\.(identifier_type|namespace_rule|min_count|max_count|requires_slot)$/.exec(
        key,
      );
    return (
      !!match &&
      profile &&
      !id &&
      Number(match[1]) < requirements.length &&
      !!child.data?.fields.some(
        (field) =>
          field.key === match[2] &&
          field.source === 'native' &&
          field.visible &&
          !field.conditional_access &&
          field.control,
      )
    );
  }
  async function submit() {
    if (
      !complete ||
      loading ||
      failure ||
      command.pending ||
      saved ||
      (command.blocked && !command.uncertain)
    )
      return;
    const draft = identifierBody(
      config,
      fields,
      values,
      requirements,
      child.data?.fields ?? [],
      record.row ?? undefined,
    );
    setErrors(draft.errors);
    if (Object.keys(draft.errors).length) return;
    if (id && Object.keys(draft.body).length === 1) {
      setUnchanged(true);
      setDirty(false);
      return;
    }
    const body = command.uncertain && frozen ? frozen : draft.body;
    setFrozen(body);
    const result = await command.execute<MasterRow>(
      {
        path: identifierBase(company, config.resource) + (id ? '/' + id : ''),
        method: id ? 'PATCH' : 'POST',
        body,
      },
      (row) =>
        identifierReceipt(
          row,
          company,
          conversion,
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
  const title = (id ? 'Edit ' : 'New ') + config.singular,
    locked = command.pending || command.uncertain,
    ratio = conversion
      ? reducedRatio(values.numerator, values.denominator)
      : null;
  return (
    <div className="janso-page">
      <IdentifierNavigation
        title={title}
        back={back}
        access={access}
        onLeave={guard.leave}
      />
      <PageHeader
        title={title}
        lede="Save reusable definitions for the company currently open."
      />
      <IdentifierFailure
        failure={failure}
        retry={() => {
          record.refresh();
          child.refresh();
        }}
      />
      <IdentifierFailure
        failure={command.failure}
        write
        retry={
          command.failure?.status === 409 ? () => setReload(true) : undefined
        }
      />
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
                href={identifierLink(root + '/' + saved.id, back)}
              >
                View {config.singular}
              </a>
              <a className="janso-link" href={back}>
                Return to previous page
              </a>
              {!id && (
                <a
                  className="janso-link"
                  href={identifierLink(root + '/new', back)}
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
                {conversion
                  ? 'A conversion states how many canonical units make one source unit: numerator divided by denominator. First declare the canonical root as a 1 to 1 self-conversion. Units must be active and share a dimension. Existing conversions remain immutable.'
                  : profile
                    ? 'Requirements are fixed when the profile is created. A changed requirement needs a new profile; existing product and device references keep their original definition.'
                    : config.resource === 'pack-types'
                      ? 'A pack type names packaging, such as box or bottle. Item-specific quantities belong to unit definitions, rather than this label.'
                      : 'Codes are unique in this company and remain stable. Referenced identifiers cannot be retired.'}
              </p>
              {!complete && (
                <Notice tone="warning">
                  Your field or unit read access does not allow the required
                  inputs. Ask an administrator to review your access.
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
                  {fields
                    .filter(
                      (field) =>
                        field.control &&
                        !['row_version', 'normalization_version'].includes(
                          field.key,
                        ),
                    )
                    .map((field) => (
                      <IdentifierField
                        key={field.key}
                        company={company}
                        field={field}
                        value={values[field.key]}
                        onChange={(value) => change(field.key, value)}
                        disabled={locked}
                        error={errors[field.key]}
                        canReadUnits={access.units}
                      />
                    ))}
                </div>
                {conversion && ratio && (
                  <Notice>
                    One source unit = {ratio.numerator} / {ratio.denominator}{' '}
                    canonical units. The ratio is saved in its simplest form.
                  </Notice>
                )}
                {profile && !id && (
                  <section
                    className="janso-flow"
                    aria-label="Identifier requirements"
                  >
                    <SectionHeader title="Identifier requirements" />
                    <p className="janso-fine">
                      Add one or two distinct types. IMEI uses company
                      uniqueness; multiple values need explicit slots.
                    </p>
                    {requirements.map((row, index) => (
                      <fieldset
                        key={index}
                        disabled={locked}
                        className="janso-setup__fields"
                      >
                        <legend className="janso-section-header__title">
                          Requirement {index + 1}
                        </legend>
                        <div className="janso-form-grid">
                          {child.data?.fields
                            .filter((field) =>
                              [
                                'identifier_type',
                                'namespace_rule',
                                'min_count',
                                'max_count',
                                'requires_slot',
                              ].includes(field.key),
                            )
                            .map((field) => (
                              <IdentifierField
                                key={field.key}
                                company={company}
                                field={field}
                                value={row[field.key]}
                                prefix={'requirements.' + index + '.'}
                                onChange={(value) =>
                                  changeRequirement(index, field.key, value)
                                }
                                disabled={locked}
                                error={
                                  errors[
                                    'requirements.' + index + '.' + field.key
                                  ]
                                }
                              />
                            ))}
                        </div>
                        {requirements.length > 1 && (
                          <Button
                            type="button"
                            variant="ghost"
                            disabled={locked}
                            onClick={() => {
                              setRequirements((rows) =>
                                rows.filter((_, current) => current !== index),
                              );
                              setDirty(true);
                              setErrors({});
                            }}
                          >
                            Remove requirement {index + 1}
                          </Button>
                        )}
                      </fieldset>
                    ))}
                    <Button
                      type="button"
                      variant="ghost"
                      disabled={locked || requirements.length >= 2 || !complete}
                      onClick={() => {
                        setRequirements((rows) => [
                          ...rows,
                          {
                            ...initialRequirement(),
                            identifier_type:
                              rows[0]?.identifier_type === 'SERIAL'
                                ? 'IMEI'
                                : 'SERIAL',
                          },
                        ]);
                        setDirty(true);
                        setErrors({});
                      }}
                    >
                      Add identifier requirement
                    </Button>
                  </section>
                )}
                {Object.entries(errors)
                  .filter(([key]) => !hasErrorControl(key))
                  .map(([key, message]) => (
                    <Notice tone="danger" key={key}>
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
          child.refresh();
        }}
      >
        Unsaved values will be replaced with the current definition.
      </ConfirmDialog>
      {guard.confirmation}
    </div>
  );
}
