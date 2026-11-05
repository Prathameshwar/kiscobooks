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
  SectionHeader,
} from '@janso/ui';
import { assertMaster, masterRequest } from '../lib/catalog-master-api';
import type { MasterRow } from '../lib/catalog-masters';
import {
  useServiceCommand,
  useServiceRead,
  type ServicePage,
} from '../lib/service-resource';
import {
  attributeBase,
  attributeId,
  attributeLink,
  attributeMemberErrors,
  attributeReturn,
  attributeVisible,
  attributeWritable,
  useAttributeFields,
  verifyAttributeRevision,
  type AttributeMember,
} from '../lib/attribute-masters';
import type { AttributeAccess } from '../lib/attribute-resources';
import { useAccessDraft } from './AccessCommon';
import {
  AttributeFailure,
  AttributeNavigation,
  AttributeReference,
} from './AttributeMasterCommon';
const memberKeys = [
  'definition_id',
  'position',
  'is_required',
  'allow_variant_axis',
] as const;
export function AttributeSetRevision({
  company,
  setId,
  id,
  returnTo,
  canManage,
  access,
}: {
  company: string;
  setId: string;
  id?: string;
  returnTo?: string;
  canManage: boolean;
  access: AttributeAccess;
}) {
  const root = '/masters/attribute-sets/' + setId,
    back = attributeReturn(returnTo, root),
    base = attributeBase(company, 'attribute-sets/' + setId + '/revisions');
  const parent = useServiceRead<MasterRow>(
    attributeBase(company, 'attribute-sets/' + setId),
    masterRequest,
    (row) => assertMaster(row, company, setId),
  );
  const revision = useServiceRead<MasterRow>(
    id ? base + '/' + id : undefined,
    masterRequest,
    (row) => assertMaster(row, company, id),
  );
  const metadata = useAttributeFields(
    company,
    'catalog.attribute_set_revision',
    id ? 'update' : 'create',
  );
  const memberMetadata = useAttributeFields(
    company,
    'catalog.attribute_set_member',
    id ? 'update' : 'create',
  );
  const publishMetadata = useAttributeFields(
    company,
    'catalog.attribute_set_revision',
    'publish',
    !!id && access.publish,
  );
  const publishMembers = useAttributeFields(
    company,
    'catalog.attribute_set_member',
    'publish',
    !!id && access.publish,
  );
  const fields = memberMetadata.data?.fields ?? [],
    fullRead = ['revision_id', ...memberKeys].every((key) =>
      attributeVisible(fields, key),
    );
  const membersRead = useServiceRead<ServicePage<MasterRow>>(
    id && memberMetadata.data
      ? base +
          '/' +
          id +
          '/members?limit=128&sort=' +
          (attributeVisible(fields, 'position') ? 'position' : 'id')
      : undefined,
    masterRequest,
    (page) => {
      if (
        !Array.isArray(page.items) ||
        !page.page ||
        page.page.has_more ||
        page.items.length > 128 ||
        page.items.some(
          (row) =>
            !attributeId.test(row.id) ||
            (row.revision_id && row.revision_id !== id) ||
            (fullRead &&
              (!memberKeys.every((key) => key in row) ||
                typeof row.is_required !== 'boolean' ||
                typeof row.allow_variant_axis !== 'boolean' ||
                !Number.isSafeInteger(row.position) ||
                !attributeId.test(String(row.definition_id)))),
        )
      )
        throw {
          status: 502,
          message:
            'The complete template membership could not be loaded. Reload before editing.',
        };
    },
  );
  const [members, setMembers] = useState<AttributeMember[]>([]),
    [definitions, setDefinitions] = useState<Record<string, MasterRow>>({}),
    [initialized, setInitialized] = useState(false),
    [dirty, setDirty] = useState(false),
    [errors, setErrors] = useState<Record<string, string>>({}),
    [saved, setSaved] = useState<MasterRow | null>(null),
    [notice, setNotice] = useState(''),
    [reload, setReload] = useState(false),
    [confirmPublish, setConfirmPublish] = useState(false);
  const [frozen, setFrozen] = useState<{
    action: 'save' | 'publish';
    body: Record<string, unknown>;
  } | null>(null);
  const command = useServiceCommand(masterRequest, 'attribute templates'),
    guard = useAccessDraft(dirty || command.uncertain, command.pending),
    form = useRef<HTMLFormElement>(null);
  useEffect(() => {
    if (
      memberMetadata.loading ||
      membersRead.loading ||
      (id && !membersRead.data)
    ) {
      setInitialized(false);
      return;
    }
    setMembers(
      id && fullRead
        ? membersRead.data!.items.map((row) => ({
            definition_id: String(row.definition_id),
            position: Number(row.position),
            is_required: row.is_required === true,
            allow_variant_axis: row.allow_variant_axis === true,
          }))
        : [],
    );
    setDefinitions({});
    setDirty(false);
    setErrors({});
    setInitialized(true);
  }, [
    id,
    memberMetadata.loading,
    membersRead.loading,
    membersRead.data,
    fullRead,
  ]);
  useEffect(() => {
    if (command.failure?.fields) setErrors(command.failure.fields);
  }, [command.failure]);
  useEffect(() => {
    if (Object.keys(errors).length && !command.pending)
      form.current
        ?.querySelector<HTMLElement>('[aria-invalid="true"]')
        ?.focus();
  }, [errors, command.pending]);
  const row = saved ?? revision.data,
    knownDraft =
      !id || (!!row && 'published_at' in row && row.published_at === null),
    active = parent.data?.is_active === true;
  const canEdit =
    canManage &&
    active &&
    knownDraft &&
    fullRead &&
    attributeWritable(fields, memberKeys) &&
    access['attribute-definitions'] &&
    ['row_version', 'attribute_set_id', 'revision', 'published_at'].every(
      (key) => attributeVisible(metadata.data?.fields ?? [], key),
    );
  const canPublish =
    !!id &&
    active &&
    knownDraft &&
    access.publish &&
    access['attribute-definitions'] &&
    fullRead &&
    attributeWritable(publishMembers.data?.fields ?? [], [
      'revision_id',
      ...memberKeys,
    ]) &&
    attributeWritable(publishMetadata.data?.fields ?? [], ['published_at']) &&
    attributeVisible(metadata.data?.fields ?? [], 'row_version');
  const failure =
    parent.failure ??
    revision.failure ??
    metadata.failure ??
    memberMetadata.failure ??
    membersRead.failure ??
    publishMetadata.failure ??
    publishMembers.failure;
  const loading =
    parent.loading ||
    revision.loading ||
    metadata.loading ||
    memberMetadata.loading ||
    membersRead.loading ||
    publishMetadata.loading ||
    publishMembers.loading ||
    (!initialized && !failure);
  const locked =
    !canEdit ||
    command.pending ||
    command.uncertain ||
    (command.blocked && command.failure?.status !== 422);
  function changed(next: AttributeMember[]) {
    setMembers(next.map((member, position) => ({ ...member, position })));
    setDirty(true);
    setErrors({});
    setNotice('');
  }
  function reloadAll() {
    command.clear();
    setFrozen(null);
    setSaved(null);
    setNotice('');
    parent.refresh();
    revision.refresh();
    metadata.refresh();
    memberMetadata.refresh();
    membersRead.refresh();
    publishMetadata.refresh();
    publishMembers.refresh();
  }
  async function execute(action: 'save' | 'publish', recovering = false) {
    if (
      command.pending ||
      loading ||
      failure ||
      (action === 'save' && !canEdit) ||
      (action === 'publish' && (!canPublish || dirty)) ||
      (command.blocked && !command.uncertain) ||
      (!row && id)
    )
      return;
    const body: Record<string, unknown> =
      recovering && frozen
        ? frozen.body
        : action === 'publish'
          ? { expected_version: row!.row_version }
          : {
              ...(id ? { expected_version: row!.row_version } : {}),
              members: members.map((member, position) => ({
                ...member,
                position,
              })),
            };
    if (!recovering) {
      const validation = attributeMemberErrors(
        members,
        definitions,
        action === 'publish',
      );
      setErrors(validation);
      if (Object.keys(validation).length) {
        setConfirmPublish(false);
        return;
      }
    }
    setFrozen({ action, body });
    setNotice('');
    const result = await command.execute<MasterRow>(
      {
        path:
          base +
          (id
            ? '/' + id + (action === 'publish' ? '/publish' : '/members')
            : ''),
        method: action === 'publish' || !id ? 'POST' : 'PUT',
        body,
      },
      (result) => {
        verifyAttributeRevision(
          result,
          company,
          setId,
          id,
          id && action === 'publish'
            ? Number(body.expected_version)
            : undefined,
        );
        if (
          action === 'publish' &&
          (typeof result.published_at !== 'string' ||
            !Number.isFinite(Date.parse(result.published_at)))
        )
          throw {
            status: 502,
            message:
              'Publication could not be confirmed. Retry the same publication.',
          };
      },
    );
    setConfirmPublish(false);
    if (result) {
      setFrozen(null);
      setDirty(false);
      setErrors({});
      setSaved(result);
      setNotice(
        action === 'publish'
          ? 'Template revision published successfully. Its requirements are now immutable.'
          : 'Draft revision saved successfully. Publish it when its requirements are ready.',
      );
      if (id) membersRead.refresh();
    }
  }
  const title = id
    ? 'Template revision' + (row?.revision ? ' ' + row.revision : '')
    : 'New template draft';
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
        lede="A template collects ordered attribute requirements for reuse by product types."
      />
      <AttributeFailure failure={failure} retry={reloadAll} />
      <AttributeFailure
        failure={command.failure}
        write
        retry={
          command.failure?.status === 409 ? () => setReload(true) : undefined
        }
      />
      {notice && <Notice tone="success">{notice}</Notice>}
      {command.uncertain && frozen && (
        <Button
          loading={command.pending}
          onClick={() => void execute(frozen.action, true)}
        >
          Retry same {frozen.action}
        </Button>
      )}
      {loading ? (
        <p role="status">Loading template revision...</p>
      ) : failure ? null : !id && saved ? (
        <Card>
          <CardBody>
            <a
              className="janso-btn janso-btn--primary"
              href={attributeLink(root + '/revisions/' + saved.id, back)}
            >
              View draft revision
            </a>
            <a className="janso-link" href={back}>
              Return to template
            </a>
          </CardBody>
        </Card>
      ) : (
        <FormLayout
          aside={
            <>
              <SectionHeader title="Template requirements" />
              <p className="janso-fine">
                Choose each definition once, mark required values and allow
                variant axes only for eligible definitions. Use the ordering
                buttons to control display order. A draft can be empty;
                publication needs at least one definition. Maximum 128.
              </p>
              {!knownDraft ? (
                <Notice>
                  Published revisions are immutable. Create a new draft to
                  change requirements.
                </Notice>
              ) : !canEdit ? (
                <Notice>
                  Read-only access. Full membership read/write access is needed
                  to replace this draft.
                </Notice>
              ) : null}
              {!active && (
                <Notice tone="warning">
                  The template is inactive or its availability is protected.
                </Notice>
              )}
              {dirty && (
                <Notice>Save the membership changes before publishing.</Notice>
              )}
            </>
          }
        >
          <form
            noValidate
            ref={form}
            onSubmit={(event) => {
              event.preventDefault();
              void execute('save');
            }}
          >
            <Card>
              <CardBody>
                <SectionHeader title="Attribute definitions" />
                {!fullRead && (
                  <Notice tone="warning">
                    Some membership fields are protected. Editing and
                    publication are unavailable so saved requirements are
                    preserved.
                  </Notice>
                )}
                {fullRead && !members.length && (
                  <Notice>No definitions in this draft yet.</Notice>
                )}
                {fullRead &&
                  members.map((member, index) => (
                    <fieldset key={index} className="janso-setup__fields">
                      <legend className="janso-section-header__title">
                        Attribute {index + 1}
                      </legend>
                      <div className="janso-form-grid">
                        {access['attribute-definitions'] ? (
                          <AttributeReference
                            company={company}
                            label={'Attribute ' + (index + 1) + ': definition'}
                            name={'members.' + index + '.definition_id'}
                            required
                            value={member.definition_id || null}
                            disabled={locked}
                            error={
                              errors['members.' + index + '.definition_id']
                            }
                            onRecord={(definition) =>
                              setDefinitions((current) =>
                                current[definition.id] === definition
                                  ? current
                                  : { ...current, [definition.id]: definition },
                              )
                            }
                            onChange={(value) =>
                              changed(
                                members.map((row, current) =>
                                  current === index
                                    ? {
                                        ...row,
                                        definition_id: value ?? '',
                                        allow_variant_axis: false,
                                      }
                                    : row,
                                ),
                              )
                            }
                          />
                        ) : (
                          <Notice>
                            Definition read access is required to resolve this
                            member.
                          </Notice>
                        )}
                        <Checkbox
                          name={'members.' + index + '.is_required'}
                          checked={member.is_required}
                          disabled={locked}
                          onChange={(event) =>
                            changed(
                              members.map((row, current) =>
                                current === index
                                  ? {
                                      ...row,
                                      is_required: event.target.checked,
                                    }
                                  : row,
                              ),
                            )
                          }
                        >
                          Attribute {index + 1}: required
                        </Checkbox>
                        <div className="janso-field">
                          <Checkbox
                            name={'members.' + index + '.allow_variant_axis'}
                            checked={member.allow_variant_axis}
                            disabled={
                              locked ||
                              definitions[member.definition_id]
                                ?.is_variant_capable !== true
                            }
                            aria-invalid={
                              !!errors[
                                'members.' + index + '.allow_variant_axis'
                              ] || undefined
                            }
                            onChange={(event) =>
                              changed(
                                members.map((row, current) =>
                                  current === index
                                    ? {
                                        ...row,
                                        allow_variant_axis:
                                          event.target.checked,
                                      }
                                    : row,
                                ),
                              )
                            }
                          >
                            Attribute {index + 1}: allow variant axis
                          </Checkbox>
                          {errors[
                            'members.' + index + '.allow_variant_axis'
                          ] && (
                            <p role="alert" className="janso-error">
                              {
                                errors[
                                  'members.' + index + '.allow_variant_axis'
                                ]
                              }
                            </p>
                          )}
                        </div>
                      </div>
                      {canEdit && (
                        <div className="janso-flow">
                          <Button
                            type="button"
                            variant="ghost"
                            disabled={locked || index === 0}
                            onClick={() => {
                              const next = [...members];
                              [next[index - 1], next[index]] = [
                                next[index]!,
                                next[index - 1]!,
                              ];
                              changed(next);
                            }}
                          >
                            Move attribute {index + 1} up
                          </Button>
                          <Button
                            type="button"
                            variant="ghost"
                            disabled={locked || index === members.length - 1}
                            onClick={() => {
                              const next = [...members];
                              [next[index + 1], next[index]] = [
                                next[index]!,
                                next[index + 1]!,
                              ];
                              changed(next);
                            }}
                          >
                            Move attribute {index + 1} down
                          </Button>
                          <Button
                            type="button"
                            variant="ghost"
                            disabled={locked}
                            onClick={() =>
                              changed(
                                members.filter(
                                  (_, current) => current !== index,
                                ),
                              )
                            }
                          >
                            Remove attribute {index + 1}
                          </Button>
                        </div>
                      )}
                    </fieldset>
                  ))}
                {canEdit && (
                  <Button
                    type="button"
                    variant="ghost"
                    disabled={
                      locked ||
                      members.length >= 128 ||
                      members.some((member) => !member.definition_id)
                    }
                    onClick={() =>
                      changed([
                        ...members,
                        {
                          definition_id: '',
                          position: members.length,
                          is_required: false,
                          allow_variant_axis: false,
                        },
                      ])
                    }
                  >
                    Add attribute definition
                  </Button>
                )}
                {!fullRead && membersRead.data && (
                  <p>
                    {membersRead.data.items.length} member records. Protected
                    fields remain unchanged.
                  </p>
                )}
                {Object.entries(errors)
                  .filter(
                    ([key]) =>
                      !/^members\.\d+\.(definition_id|allow_variant_axis)$/.test(
                        key,
                      ),
                  )
                  .map(([key, message]) => (
                    <Notice key={key} tone="danger">
                      {message}
                    </Notice>
                  ))}
              </CardBody>
              <FormActions cancel={{ href: back, onClick: guard.leave }}>
                {canEdit && (
                  <Button
                    type="submit"
                    loading={command.pending}
                    disabled={locked}
                  >
                    Save draft revision
                  </Button>
                )}
                {canPublish && (
                  <Button
                    type="button"
                    disabled={dirty || command.blocked || !members.length}
                    onClick={() => setConfirmPublish(true)}
                  >
                    Publish revision
                  </Button>
                )}
              </FormActions>
            </Card>
          </form>
        </FormLayout>
      )}
      <ConfirmDialog
        open={confirmPublish}
        title="Publish this template revision?"
        confirmLabel="Publish revision"
        busy={command.pending}
        onCancel={() => {
          if (!command.pending) setConfirmPublish(false);
        }}
        onConfirm={() => void execute('publish')}
      >
        Publication freezes these requirements. Product types can then pin this
        revision. Later changes require a new draft.
      </ConfirmDialog>
      <ConfirmDialog
        open={reload}
        title="Reload current revision?"
        confirmLabel="Reload and review"
        onCancel={() => setReload(false)}
        onConfirm={() => {
          setReload(false);
          reloadAll();
        }}
      >
        Unsaved membership will be replaced with the current saved revision.
      </ConfirmDialog>
      {guard.confirmation}
    </div>
  );
}
