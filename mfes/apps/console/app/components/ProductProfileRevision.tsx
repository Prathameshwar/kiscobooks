'use client';
import { useEffect, useRef, useState } from 'react';
import {
  Button,
  Card,
  CardBody,
  Checkbox,
  ConfirmDialog,
  FormActions,
  FormLayout,
  Notice,
  PageHeader,
  ReviewList,
  SectionHeader,
} from '@janso/ui';
import { assertMaster, masterRequest } from '../lib/catalog-master-api';
import { nativeProductInitial } from '../lib/product-entry-policy';
import type { MasterConfig, MasterRow } from '../lib/catalog-masters';
import {
  useServiceCommand,
  useServiceRead,
  type ServicePage,
} from '../lib/service-resource';
import {
  conditionCodes,
  profileBase,
  profileBody,
  profileDefaults,
  profileKeys,
  profileLink,
  profileReturn,
  profileVisible,
  profileWritable,
  useProfileFields,
  verifyProfileConditions,
  verifyProfileRevision,
} from '../lib/product-profiles';
import {
  profileDefinitions,
  type ProductProfileAccess,
  type ProductProfileResource,
} from '../lib/product-profile-resources';
import {
  ProfileExplanation,
  ProfileFailure,
  ProfileField,
  ProfileNavigation,
} from './ProductProfileCommon';
import { useAccessDraft } from './AccessCommon';
import { ManufacturingRouteSteps } from './ManufacturingRouteSteps';
import {
  routeStepFields,
  routeStepBody,
  verifyRouteSteps,
  type RouteStep,
} from '../lib/manufacturing-routes';
export function ProductProfileRevision({
  company,
  config,
  parentId,
  id,
  returnTo,
  canManage,
  access,
}: {
  company: string;
  config: MasterConfig;
  parentId: string;
  id?: string;
  returnTo?: string;
  canManage: boolean;
  access: ProductProfileAccess;
}) {
  const resource = config.resource as ProductProfileResource,
    definition = profileDefinitions[resource],
    root = '/masters/' + resource + '/' + parentId,
    back = profileReturn(returnTo, root),
    base = profileBase(company, resource + '/' + parentId + '/revisions'),
    returns = resource === 'return-policies',
    routes = resource === 'manufacturing-routes',
    manufacturing = routes || resource === 'manufacturing-operations';
  const parent = useServiceRead<MasterRow>(
    profileBase(company, resource + '/' + parentId),
    masterRequest,
    (row) => assertMaster(row, company, parentId),
  );
  const revision = useServiceRead<MasterRow>(
    id ? base + '/' + id : undefined,
    masterRequest,
    (row) => verifyProfileRevision(row, company, resource, parentId, id),
  );
  const metadata = useProfileFields(
      company,
      config.entity + '_revision',
      id ? 'update' : 'create',
    ),
    fields = metadata.data?.fields ?? [];
  const memberMetadata = useProfileFields(
    company,
    routes
      ? 'catalog.manufacturing_route_step'
      : 'catalog.return_policy_condition',
    id ? 'update' : 'create',
    returns || routes,
  );
  const publishMetadata = useProfileFields(
    company,
    config.entity + '_revision',
    'publish',
    !!id && access.publish,
  );
  const publishMembers = useProfileFields(
    company,
    routes
      ? 'catalog.manufacturing_route_step'
      : 'catalog.return_policy_condition',
    'publish',
    (returns || routes) && !!id && access.publish,
  );
  const memberFields = memberMetadata.data?.fields ?? [],
    conditionsReadable =
      returns &&
      ['revision_id', 'condition_code'].every((key) =>
        profileVisible(memberFields, key),
      );
  const conditions = useServiceRead<ServicePage<MasterRow>>(
    returns &&
      id &&
      revision.data &&
      conditionsReadable &&
      profileVisible(fields, 'condition_count')
      ? base + '/' + id + '/conditions?limit=5&sort=id'
      : undefined,
    masterRequest,
    (page) => {
      verifyProfileConditions(page, id!, revision.data?.condition_count);
    },
  );
  const routeStepsReadable =
    routes &&
    ['revision_id', ...routeStepFields].every((key) =>
      profileVisible(memberFields, key),
    );
  const routeSteps = useServiceRead<ServicePage<MasterRow>>(
    routes &&
      id &&
      revision.data &&
      routeStepsReadable &&
      profileVisible(fields, 'step_count')
      ? base + '/' + id + '/steps?limit=50&sort=sequence'
      : undefined,
    masterRequest,
    (page) => {
      verifyRouteSteps(page, id!, revision.data?.step_count);
    },
  );
  const [values, setValues] = useState<Record<string, unknown>>({}),
    [dirty, setDirty] = useState(false),
    [errors, setErrors] = useState<Record<string, string>>({}),
    [saved, setSaved] = useState<MasterRow | null>(null),
    [notice, setNotice] = useState(''),
    [reload, setReload] = useState(false),
    [confirmPublish, setConfirmPublish] = useState(false),
    [confirmRetire, setConfirmRetire] = useState(false),
    [initialized, setInitialized] = useState(false);
  const [frozen, setFrozen] = useState<{
    action: 'save' | 'publish' | 'retire';
    body: Record<string, unknown>;
  } | null>(null);
  const command = useServiceCommand(masterRequest, 'product profile revisions'),
    guard = useAccessDraft(dirty || command.uncertain, command.pending),
    form = useRef<HTMLFormElement>(null);
  useEffect(() => {
    if (
      metadata.loading ||
      revision.loading ||
      conditions.loading ||
      routeSteps.loading ||
      (id && !revision.data)
    ) {
      setInitialized(false);
      return;
    }
    setValues(
      id
        ? {
            ...revision.data,
            ...(returns && conditions.data
              ? {
                  condition_codes: verifyProfileConditions(
                    conditions.data,
                    id,
                    revision.data!.condition_count,
                  ),
                }
              : {}),
            ...(routes && routeSteps.data
              ? {
                  steps: verifyRouteSteps(
                    routeSteps.data,
                    id,
                    revision.data!.step_count,
                  ),
                }
              : {}),
          }
        : {
            ...nativeProductInitial(fields, profileDefaults[resource]),
            ...(routes ? { steps: [] } : {}),
          },
    );
    setDirty(false);
    setErrors({});
    setSaved(null);
    setFrozen(null);
    setNotice('');
    setInitialized(true);
  }, [
    metadata.loading,
    metadata.data,
    revision.loading,
    revision.data,
    conditions.loading,
    conditions.data,
    routeSteps.loading,
    routeSteps.data,
    resource,
    id,
  ]);
  useEffect(() => {
    if (command.failure?.fields) setErrors(command.failure.fields);
  }, [command.failure]);
  useEffect(() => {
    if (Object.keys(errors).length)
      form.current
        ?.querySelector<HTMLElement>('[aria-invalid="true"]')
        ?.focus();
  }, [errors]);
  const row = saved ?? revision.data,
    draft =
      !id || (!!row && 'published_at' in row && row.published_at === null),
    active = parent.data?.is_active === true;
  const noun = routes
    ? 'route'
    : resource === 'manufacturing-operations'
      ? 'operation'
      : 'profile';
  const systemRead = [
    'row_version',
    definition.parent,
    'revision',
    'published_at',
    ...(manufacturing ? ['status'] : []),
    ...(routes ? ['step_count'] : []),
  ].every((key) => profileVisible(fields, key));
  const conditionsComplete = !returns || !id || !!conditions.data;
  const routeStepsComplete = !routes || !id || !!routeSteps.data;
  const routeStepsWritable =
    routes &&
    routeStepsComplete &&
    routeStepsReadable &&
    access['manufacturing-operations'] === true &&
    profileWritable(memberFields, ['revision_id', ...routeStepFields]) &&
    !memberFields.some(
      (field) =>
        routeStepFields.includes(
          field.key as (typeof routeStepFields)[number],
        ) && field.control?.disabled_reason,
    );
  const conditionsWritable =
    returns &&
    conditionsReadable &&
    conditionsComplete &&
    profileWritable(memberFields, ['revision_id', 'condition_code']);
  const requiredKeys = profileKeys(resource).filter(
      (key) => profileDefaults[resource][key] !== null,
    ),
    fullCreate =
      profileWritable(fields, [definition.parent, ...requiredKeys]) &&
      (!returns || conditionsWritable);
  const canEdit =
    canManage &&
    active &&
    draft &&
    systemRead &&
    (id
      ? profileKeys(resource).some((key) => profileWritable(fields, [key])) ||
        conditionsWritable ||
        routeStepsWritable
      : fullCreate);
  const publishFields = publishMetadata.data?.fields ?? [],
    publishKeys = [
      ...(manufacturing ? ['status'] : []),
      'published_at',
      ...profileKeys(resource).filter((key) => row?.[key] != null),
    ];
  const canPublish =
    !!id &&
    !!row &&
    active &&
    draft &&
    access.publish &&
    systemRead &&
    profileKeys(resource).every(
      (key) => profileVisible(fields, key) && key in row,
    ) &&
    profileWritable(publishFields, publishKeys) &&
    conditionsComplete &&
    (!routes ||
      (routeStepsComplete &&
        Number(row.step_count) > 0 &&
        access['manufacturing-operations'] === true &&
        profileWritable(publishMembers.data?.fields ?? [], [
          'revision_id',
          ...routeStepFields,
        ]))) &&
    (!returns ||
      Number(row.condition_count) === 0 ||
      profileWritable(publishMembers.data?.fields ?? [], [
        'revision_id',
        'condition_code',
      ]));
  const failure =
      parent.failure ??
      revision.failure ??
      metadata.failure ??
      memberMetadata.failure ??
      conditions.failure ??
      routeSteps.failure,
    publicationFailure = publishMetadata.failure ?? publishMembers.failure;
  const canRetire =
    manufacturing &&
    !!id &&
    row?.status === 'PUBLISHED' &&
    access.publish &&
    profileVisible(fields, 'status') &&
    profileVisible(fields, 'row_version') &&
    profileWritable(publishFields, ['status']);
  const loading =
    parent.loading ||
    revision.loading ||
    metadata.loading ||
    memberMetadata.loading ||
    conditions.loading ||
    routeSteps.loading ||
    (!initialized && !failure);
  const locked = !canEdit || command.pending || command.uncertain || !!saved;
  const original = revision.data
    ? {
        ...revision.data,
        ...(returns && conditions.data
          ? {
              condition_codes: verifyProfileConditions(
                conditions.data,
                id!,
                revision.data.condition_count,
              ),
            }
          : {}),
        ...(routes && routeSteps.data
          ? {
              steps: verifyRouteSteps(
                routeSteps.data,
                id!,
                revision.data.step_count,
              ),
            }
          : {}),
      }
    : revision.data;
  function change(key: string, value: unknown) {
    if (!id && command.failure?.status === 409) command.clear();
    setValues((current) => {
      const next = { ...current, [key]: value };
      // Keep the explicit temperature unit coherent only when that field is writable.
      if (
        ['temperature_min', 'temperature_max'].includes(key) &&
        profileWritable(fields, ['temperature_unit']) &&
        'temperature_min' in next &&
        'temperature_max' in next
      )
        next.temperature_unit =
          (next.temperature_min != null && next.temperature_min !== '') ||
          (next.temperature_max != null && next.temperature_max !== '')
            ? 'CELSIUS'
            : null;
      return next;
    });
    setDirty(true);
    setErrors({});
    setNotice('');
  }
  async function execute(
    action: 'save' | 'publish' | 'retire',
    replay?: Record<string, unknown>,
  ) {
    if (
      command.pending ||
      loading ||
      failure ||
      (command.blocked && !command.uncertain) ||
      (action === 'save' && (!canEdit || saved)) ||
      (action === 'publish' && (!canPublish || dirty || saved)) ||
      (action === 'retire' && (!canRetire || dirty || saved))
    )
      return;
    let body: Record<string, unknown>;
    if (replay) body = replay;
    else if (action === 'publish' || action === 'retire')
      body = { expected_version: row!.row_version };
    else {
      const result = profileBody(
        resource,
        fields,
        values,
        original ?? undefined,
        conditionsWritable,
      );
      if (routes && routeStepsWritable && Array.isArray(values.steps)) {
        const checked = routeStepBody(values.steps as RouteStep[]);
        const previous = Array.isArray(original?.steps)
          ? routeStepBody(original.steps as RouteStep[]).body
          : [];
        if (!id || JSON.stringify(checked.body) !== JSON.stringify(previous)) {
          result.body.steps = checked.body;
          Object.assign(result.errors, checked.errors);
        }
      }
      setErrors(result.errors);
      if (Object.keys(result.errors).length) return;
      body = result.body;
      if (id && Object.keys(body).length === 1) {
        setDirty(false);
        setNotice('No changes to save.');
        return;
      }
    }
    setFrozen({ action, body });
    setNotice('');
    const result = await command.execute<MasterRow>(
      {
        path:
          base + (id ? '/' + id : '') + (action === 'save' ? '' : '/' + action),
        method: action !== 'save' || !id ? 'POST' : 'PATCH',
        body,
      },
      (current) => {
        if (
          manufacturing &&
          action !== 'save' &&
          current.status !== (action === 'publish' ? 'PUBLISHED' : 'RETIRED')
        )
          throw {
            status: 502,
            message:
              'The revision action could not be verified. Retry the same action.',
          };
        verifyProfileRevision(
          current,
          company,
          resource,
          parentId,
          id,
          true,
          id ? row?.row_version : undefined,
          action === 'publish',
        );
      },
    );
    setConfirmPublish(false);
    setConfirmRetire(false);
    if (result) {
      setSaved(result);
      setDirty(false);
      setFrozen(null);
      setNotice(
        action === 'retire'
          ? 'Revision retired. Its specification and history are preserved.'
          : action === 'publish'
            ? 'Revision published successfully. Its definition is now immutable.'
            : id
              ? 'Draft revision updated successfully.'
              : 'Draft revision created successfully.',
      );
    }
  }
  const title = !id
    ? 'New ' + config.singular + ' revision'
    : 'Revision ' +
      (row?.revision ?? '') +
      ' — ' +
      (parent.data?.name ?? config.singular);
  return (
    <div className="janso-page">
      <ProfileNavigation
        resource={config.resource as ProductProfileResource}
        title={title}
        back={back}
        access={access}
        onLeave={guard.leave}
      />
      <PageHeader
        title={title}
        lede={
          'Changes apply to this ' + noun + ' in the company currently open.'
        }
        actions={
          canRetire && !saved ? (
            <Button
              variant="danger"
              disabled={command.pending || command.blocked}
              onClick={() => setConfirmRetire(true)}
            >
              Retire revision
            </Button>
          ) : (
            id &&
            access.publish &&
            draft &&
            !saved && (
              <Button
                onClick={() => setConfirmPublish(true)}
                disabled={
                  !canPublish ||
                  dirty ||
                  command.blocked ||
                  loading ||
                  !!failure ||
                  !!publicationFailure ||
                  publishMetadata.loading ||
                  publishMembers.loading
                }
              >
                Publish revision
              </Button>
            )
          )
        }
      />
      <ProfileExplanation resource={resource} />
      <ProfileFailure
        failure={failure}
        retry={() => {
          parent.refresh();
          metadata.refresh();
          revision.refresh();
          memberMetadata.refresh();
          conditions.refresh();
        }}
      />
      <ProfileFailure
        failure={publicationFailure}
        retry={() => {
          publishMetadata.refresh();
          publishMembers.refresh();
        }}
      />
      <ProfileFailure failure={command.failure} write={command.uncertain} />
      {command.failure && !command.uncertain && id && (
        <Button variant="ghost" onClick={() => setReload(true)}>
          Reload and review
        </Button>
      )}
      {command.failure?.status === 409 && !id && (
        <Notice>
          Your draft is retained. Check the parent profile and correct the
          values before retrying.
        </Notice>
      )}
      {command.uncertain && frozen && (
        <Button
          disabled={command.pending}
          onClick={() => execute(frozen.action, frozen.body)}
        >
          Retry same{' '}
          {frozen.action === 'publish'
            ? 'publication'
            : frozen.action === 'retire'
              ? 'retirement'
              : 'save'}
        </Button>
      )}
      {notice && (
        <Notice tone={saved ? 'success' : 'info'}>
          {notice}
          {saved && (
            <>
              <br />
              <a
                className="janso-link"
                href={profileLink(root + '/revisions/' + saved.id, back)}
              >
                View saved revision
              </a>
              {' · '}
              <a className="janso-link" href={root}>
                Back to {noun}
              </a>
            </>
          )}
        </Notice>
      )}
      {loading ? (
        <p role="status">Loading profile revision...</p>
      ) : (
        !failure && (
          <FormLayout>
            <form
              ref={form}
              noValidate
              onSubmit={(event) => {
                event.preventDefault();
                void execute('save');
              }}
            >
              <Card>
                <CardBody>
                  <div className="janso-flow">
                    <ReviewList
                      items={[
                        {
                          label:
                            noun === 'operation'
                              ? 'Operation'
                              : routes
                                ? 'Route'
                                : 'Profile',
                          value: parent.data?.name ?? 'Protected profile',
                        },
                        {
                          label: 'Status',
                          value: !id
                            ? 'New draft'
                            : !('published_at' in (row ?? {}))
                              ? 'Protected'
                              : row?.status === 'RETIRED'
                                ? 'Retired'
                                : row?.published_at === null
                                  ? 'Draft'
                                  : 'Published',
                        },
                        ...(row?.row_version != null
                          ? [
                              {
                                label: 'Version',
                                value: String(row.row_version),
                              },
                            ]
                          : []),
                      ]}
                    />
                    {!active && (
                      <Notice tone="warning">
                        The {noun} must be active before authoring or
                        publication.
                      </Notice>
                    )}
                    {!canEdit && draft && !saved && (
                      <Notice>
                        Read-only: editing permission or required field access
                        is unavailable.
                      </Notice>
                    )}
                    {!draft && (
                      <Notice>
                        This{' '}
                        {row?.status === 'RETIRED' ? 'retired' : 'published'}{' '}
                        revision is immutable. Create a new draft from the{' '}
                        {noun} page for future changes.
                      </Notice>
                    )}
                    {dirty && access.publish && id && (
                      <Notice>
                        Save this draft and open the saved revision before
                        publishing.
                      </Notice>
                    )}
                    {[
                      ...new Set(
                        fields
                          .map((field) => field.control?.disabled_reason)
                          .filter(Boolean),
                      ),
                    ].map((reason) => (
                      <Notice key={reason}>{reason}</Notice>
                    ))}
                    <div className="janso-form-grid">
                      {fields
                        .filter((field) =>
                          profileKeys(resource).includes(field.key),
                        )
                        .map((field) => (
                          <ProfileField
                            returnTo={
                              id
                                ? profileLink(root + '/revisions/' + id, back)
                                : undefined
                            }
                            onLeave={guard.leave}
                            key={field.key}
                            company={company}
                            field={
                              field.key === 'duration' && field.control
                                ? {
                                    ...field,
                                    control: {
                                      ...field.control,
                                      maximum: Math.min(
                                        field.control.maximum ?? 36500,
                                        values.duration_unit === 'YEARS'
                                          ? 100
                                          : values.duration_unit === 'MONTHS'
                                            ? 1200
                                            : 36500,
                                      ),
                                    },
                                  }
                                : field
                            }
                            value={values[field.key]}
                            disabled={
                              locked ||
                              (!id &&
                                field.key === 'identifier_profile_id' &&
                                !access.identifiers)
                            }
                            error={errors[field.key]}
                            onChange={(value) => change(field.key, value)}
                            access={access}
                          />
                        ))}
                    </div>
                    {routes && (
                      <ManufacturingRouteSteps
                        company={company}
                        fields={memberFields}
                        returnTo={profileLink(
                          root + '/revisions/' + (id ?? 'new'),
                          back,
                        )}
                        onLeave={guard.leave}
                        steps={
                          Array.isArray(values.steps)
                            ? (values.steps as RouteStep[])
                            : []
                        }
                        onChange={(next) => change('steps', next)}
                        disabled={locked || !routeStepsWritable}
                        complete={routeStepsComplete && routeStepsReadable}
                        canReadOperations={
                          access['manufacturing-operations'] === true
                        }
                        errors={errors}
                      />
                    )}
                    {returns && (
                      <>
                        <SectionHeader title="Return conditions" />
                        {!conditionsComplete || !conditionsReadable ? (
                          <Notice tone="warning">
                            The complete condition set is unavailable. Existing
                            conditions are retained; condition replacement and
                            publication are disabled.
                          </Notice>
                        ) : (
                          <div className="janso-form-grid">
                            {conditionCodes.map((code) => (
                              <Checkbox
                                key={code}
                                checked={
                                  Array.isArray(values.condition_codes) &&
                                  values.condition_codes.includes(code)
                                }
                                disabled={locked || !conditionsWritable}
                                onChange={(event) => {
                                  const selected =
                                    (values.condition_codes as string[]) ?? [];
                                  change(
                                    'condition_codes',
                                    event.target.checked
                                      ? [...selected, code]
                                      : selected.filter(
                                          (value) => value !== code,
                                        ),
                                  );
                                }}
                              >
                                {memberFields
                                  .find(
                                    (field) => field.key === 'condition_code',
                                  )
                                  ?.control?.choices?.find(
                                    (choice) => choice.value === code,
                                  )?.label ?? code.replaceAll('_', ' ')}
                              </Checkbox>
                            ))}
                          </div>
                        )}
                        {errors.condition_codes && (
                          <Notice tone="danger">
                            {errors.condition_codes}
                          </Notice>
                        )}
                      </>
                    )}
                    {Object.keys(errors).length > 0 && (
                      <Notice tone="danger">
                        Review the highlighted fields before saving.
                      </Notice>
                    )}
                  </div>
                </CardBody>
                <FormActions
                  cancel={{
                    href: back,
                    label:
                      !draft || !canEdit || saved
                        ? 'Back to ' + noun
                        : 'Cancel',
                    onClick: guard.leave,
                  }}
                >
                  {draft && !saved && (
                    <Button
                      type="submit"
                      loading={command.pending}
                      disabled={!canEdit || command.blocked}
                    >
                      {id ? 'Save draft changes' : 'Create draft revision'}
                    </Button>
                  )}
                </FormActions>
              </Card>
            </form>
          </FormLayout>
        )
      )}
      <ConfirmDialog
        open={confirmPublish}
        title={'Publish this ' + noun + ' revision?'}
        confirmLabel="Publish revision"
        busy={command.pending}
        onCancel={() => {
          if (!command.pending) setConfirmPublish(false);
        }}
        onConfirm={() => void execute('publish')}
      >
        {noun === 'operation'
          ? 'The saved specification will become immutable and available for route definitions. Publishing does not enable production execution.'
          : 'The saved definition will become immutable and available for product configuration. Publishing does not change existing product selections.'}
      </ConfirmDialog>
      <ConfirmDialog
        open={confirmRetire}
        title="Retire this operation revision?"
        confirmLabel="Retire revision"
        busy={command.pending}
        onCancel={() => {
          if (!command.pending) setConfirmRetire(false);
        }}
        onConfirm={() => void execute('retire')}
      >
        Retiring prevents new selection. The specification and existing
        historical references are preserved.
      </ConfirmDialog>
      <ConfirmDialog
        open={reload}
        title="Reload and discard this draft?"
        confirmLabel="Reload"
        onCancel={() => setReload(false)}
        onConfirm={() => {
          setReload(false);
          command.clear();
          parent.refresh();
          metadata.refresh();
          revision.refresh();
          memberMetadata.refresh();
          conditions.refresh();
          publishMetadata.refresh();
          publishMembers.refresh();
        }}
      >
        Your unsaved values will be replaced with the latest saved revision.
      </ConfirmDialog>
      {guard.confirmation}
    </div>
  );
}
