'use client';
import { useEffect, useRef, useState } from 'react';
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  Checkbox,
  ConfirmDialog,
  DataTable,
  FilterBar,
  FormActions,
  FormLayout,
  Menu,
  Notice,
  PageHeader,
  PageNavigation,
  Pager,
  ReviewList,
  SectionHeader,
  Select,
  TableSearch,
  formatDateTime,
  useDisplayConfig,
  type Column,
} from '@janso/ui';
import type { components } from '@janso/api-client/catalog';
import type { MasterField } from '../lib/catalog-masters';
import { masterRequest } from '../lib/catalog-master-api';
import { masterReturn } from '../lib/master-navigation';
import { profileWritable, useProfileFields } from '../lib/product-profiles';
import {
  stackBase,
  stackRoot,
  stackBody,
  verifyStack,
  stackGroupFields,
  stackPermissionFields,
  stackHeaderFields,
  type StackDraft,
  type StackPolicy,
  type StackValues,
  type StackGroup,
} from '../lib/promotion-stacks';
import {
  useServiceCommand,
  useServiceList,
  useServiceRead,
} from '../lib/service-resource';
import type { ServiceRequest } from '../lib/service-call';
import { useAccessDraft } from './AccessCommon';
import { ProfileFailure, ProfileField } from './ProductProfileCommon';

type Access = { manage: boolean; publish: boolean };
const noProfiles = {
  'inventory-templates': false,
  'warranty-policies': false,
  'return-policies': false,
  'handling-profiles': false,
  publish: false,
  identifiers: false,
};
const explanation =
  'Choose ordered offer groups and explicitly allow the combinations you intend. No permission means no stacking. Publication defines policy; it does not apply offers, reserve budgets or redeem coupons.';
function useStackContext(company: string) {
  return useServiceRead<components['schemas']['StackAuthoringContext']>(
    stackBase(company) + '/authoring-context',
    masterRequest,
    (value) => {
      if (
        value.company_id !== company ||
        typeof value.enabled !== 'boolean' ||
        value.operational_ready !== false
      )
        throw {
          status: 502,
          message: 'Promotion definition configuration could not be verified.',
        };
    },
  );
}
function Navigation({
  title,
  back,
  leave,
}: {
  title: string;
  back: string;
  leave?: React.MouseEventHandler<HTMLAnchorElement>;
}) {
  return (
    <PageNavigation
      back={{ href: back, label: 'previous page' }}
      breadcrumbs={[
        { label: 'Business overview', href: '/' },
        { label: 'Masters', href: '/masters' },
        ...(title === 'Promotion stacking policies'
          ? []
          : [{ label: 'Promotion stacking policies', href: stackRoot }]),
        { label: title },
      ]}
      onNavigate={leave}
    />
  );
}
export function PromotionStacks({
  company,
  detail,
  id,
  published,
  access,
  returnTo,
}: {
  company: string;
  detail: boolean;
  id?: string;
  published: boolean;
  access: Access;
  returnTo?: string;
}) {
  return detail ? (
    <StackEditor
      company={company}
      id={id}
      published={published}
      access={access}
      returnTo={returnTo}
    />
  ) : (
    <StackDirectory company={company} access={access} returnTo={returnTo} />
  );
}
function StackDirectory({
  company,
  access,
  returnTo,
}: {
  company: string;
  access: Access;
  returnTo?: string;
}) {
  const context = useStackContext(company),
    [search, setSearch] = useState('');
  return (
    <div className="janso-page">
      <Navigation
        title="Promotion stacking policies"
        back={masterReturn(returnTo, '/masters')}
      />
      <PageHeader
        title="Promotion stacking policies"
        lede="Review draft combinations and immutable published policies for this company."
        actions={
          access.manage && context.data?.enabled ? (
            <a
              className="janso-btn janso-btn--primary"
              href={stackRoot + '/drafts/new'}
            >
              New policy draft
            </a>
          ) : undefined
        }
      />
      <Notice>{explanation}</Notice>
      <ProfileFailure failure={context.failure} retry={context.refresh} />
      {context.data && !context.data.enabled && (
        <Notice>
          Enable Sales promotion definitions in Company configuration before
          creating or publishing policies. Existing history remains available.
        </Notice>
      )}
      <StackList
        company={company}
        published={false}
        search={search}
        onSearch={setSearch}
      />
      <StackList company={company} published search={search} />
    </div>
  );
}
function StackList({
  company,
  published,
  search,
  onSearch,
}: {
  company: string;
  published: boolean;
  search: string;
  onSearch?: (value: string) => void;
}) {
  type Row = components['schemas']['StackDraftListItem'] &
    components['schemas']['StackPolicyListItem'];
  const display = useDisplayConfig(),
    entity = published
      ? 'catalog.promotion_stack_policy'
      : 'catalog.promotion_stack_draft';
  const fields = useProfileFields(company, entity),
    canSearch = fields.data?.fields.some(
      (field) => field.key === 'code' && !field.conditional_access,
    );
  const query = new URLSearchParams();
  if (canSearch && search.trim().length >= 2) query.set('q', search.trim());
  const list = useServiceList<Row>(
    stackBase(company) + (published ? '/revisions' : '/drafts'),
    query.toString(),
    masterRequest,
    (row) => {
      if (!/^[0-9a-f-]{36}$/i.test(row.id))
        throw { status: 502, message: 'Policy history could not be verified.' };
    },
  );
  const title = published ? 'Published policies' : 'Policy drafts';
  const columns: Column<Row>[] = [
    {
      key: 'code',
      header: 'Policy',
      type: 'custom',
      render: (row) => (
        <a
          className="janso-link"
          href={`${stackRoot}/${published ? 'revisions' : 'drafts'}/${row.id}`}
        >
          {row.code ?? 'Protected policy'}
        </a>
      ),
    },
    {
      key: 'version',
      header: published ? 'Version' : 'Status',
      type: 'custom',
      render: (row) =>
        String((published ? row.version : row.status) ?? 'Protected'),
    },
    {
      key: 'maximum_applied',
      header: 'Maximum offers',
      type: 'custom',
      render: (row) => String(row.maximum_applied ?? 'Protected'),
    },
    ...(published
      ? [
          {
            key: 'published_at',
            header: 'Published',
            type: 'custom' as const,
            render: (row: Row) =>
              row.published_at
                ? formatDateTime(row.published_at, display)
                : 'Protected',
          },
        ]
      : []),
  ];
  return (
    <section className="janso-flow" aria-label={title}>
      <SectionHeader title={title} />
      <ProfileFailure
        failure={fields.failure ?? list.failure}
        retry={() => {
          fields.refresh();
          list.first();
        }}
      />
      <Card>
        {onSearch && (
          <FilterBar>
            {canSearch ? (
              <TableSearch
                label="Search policy codes"
                value={search}
                onChange={onSearch}
                minLength={2}
                maxLength={200}
              />
            ) : (
              <Notice>Search requires readable policy codes.</Notice>
            )}
          </FilterBar>
        )}
        <DataTable
          caption={title}
          columns={columns}
          rows={list.data?.items ?? []}
          rowId={(row) => row.id}
          rowLabel={(row) => row.code ?? 'Policy'}
          loading={list.loading || fields.loading}
          emptyTitle={'No ' + title.toLowerCase()}
          emptyBody="Create and review a draft to define the intended combinations."
        />
        <Pager
          noun="policy"
          count={list.data?.items.length ?? 0}
          limit={list.limit}
          hasPrevious={list.hasPrevious}
          hasNext={list.data?.page.has_more ?? false}
          onPrevious={list.previous}
          onNext={list.next}
          onLimitChange={list.setLimit}
          busy={list.loading}
        />
      </Card>
    </section>
  );
}
function StackEditor({
  company,
  id,
  published,
  access,
  returnTo,
}: {
  company: string;
  id?: string;
  published: boolean;
  access: Access;
  returnTo?: string;
}) {
  const context = useStackContext(company),
    entity = published
      ? 'catalog.promotion_stack_policy'
      : 'catalog.promotion_stack_draft';
  const path =
    stackBase(company) +
    (published ? '/revisions' : '/drafts') +
    (id ? '/' + id : '');
  const record = useServiceRead<StackDraft | StackPolicy>(
    id ? path : undefined,
    masterRequest,
    (row) => verifyStack(row, company, id),
  );
  const fields = useProfileFields(
    company,
    entity,
    published ? undefined : id ? 'update' : 'create',
  );
  const groups = useProfileFields(
    company,
    published
      ? 'catalog.promotion_stack_group'
      : 'catalog.promotion_stack_draft_group',
    published ? undefined : id ? 'update' : 'create',
  );
  const pairs = useProfileFields(
    company,
    published
      ? 'catalog.promotion_stack_permission'
      : 'catalog.promotion_stack_draft_permission',
    published ? undefined : id ? 'update' : 'create',
  );
  const publication = !!id && !published && access.publish;
  const draftPublish = useProfileFields(
    company,
    'catalog.promotion_stack_draft',
    'publish',
    publication,
  );
  const policyPublish = useProfileFields(
    company,
    'catalog.promotion_stack_policy',
    'publish',
    publication,
  );
  const groupPublish = useProfileFields(
    company,
    'catalog.promotion_stack_group',
    'publish',
    publication,
  );
  const pairPublish = useProfileFields(
    company,
    'catalog.promotion_stack_permission',
    'publish',
    publication,
  );
  const [values, setValues] = useState<StackValues>({
    code: '',
    change_reason: '',
    maximum_applied: '1',
    groups: [],
    permissions: [],
  });
  const [dirty, setDirty] = useState(false),
    [errors, setErrors] = useState<Record<string, string>>({}),
    [saved, setSaved] = useState<StackDraft | null>(null),
    [review, setReview] = useState(false),
    [reload, setReload] = useState(false);
  const command = useServiceCommand(masterRequest, 'promotion stacking policy'),
    frozen = useRef<ServiceRequest | null>(null),
    form = useRef<HTMLFormElement>(null);
  const guard = useAccessDraft(dirty || command.uncertain, command.pending),
    back = masterReturn(returnTo, stackRoot);
  useEffect(() => {
    if (record.data?.complete) {
      setValues({
        code: record.data.code!,
        change_reason:
          'change_reason' in record.data
            ? (record.data.change_reason ?? '')
            : '',
        maximum_applied: String(record.data.maximum_applied),
        groups: record.data.groups!,
        permissions: record.data.permissions!,
      });
      setDirty(false);
    }
  }, [record.data]);
  const allFields = fields.data?.fields ?? [],
    groupFields = groups.data?.fields ?? [],
    pairFields = pairs.data?.fields ?? [];
  const readable = (source: readonly MasterField[], keys: readonly string[]) =>
    keys.every((key) =>
      source.some((field) => field.key === key && !field.conditional_access),
    );
  const complete = id
    ? record.data?.complete === true
    : readable(allFields, stackHeaderFields) &&
      readable(groupFields, stackGroupFields) &&
      readable(pairFields, stackPermissionFields);
  const draft =
    !published &&
    (!id ||
      ('status' in (record.data ?? {}) &&
        (record.data as StackDraft).status === 'DRAFT'));
  const editable =
    access.manage &&
    draft &&
    complete &&
    context.data?.enabled &&
    profileWritable(allFields, stackHeaderFields) &&
    profileWritable(groupFields, stackGroupFields) &&
    profileWritable(pairFields, stackPermissionFields);
  const canPublish =
    publication &&
    draft &&
    complete &&
    !dirty &&
    context.data?.enabled &&
    values.groups.length > 0 &&
    profileWritable(draftPublish.data?.fields ?? [], [
      'status',
      'published_policy_id',
      'row_version',
    ]) &&
    profileWritable(policyPublish.data?.fields ?? [], [
      'code',
      'version',
      'maximum_applied',
      'published_at',
      'source_sha256',
    ]) &&
    profileWritable(groupPublish.data?.fields ?? [], [
      'policy_revision_id',
      'position',
      'stage',
      'selection',
      'changes_basket',
    ]) &&
    profileWritable(pairPublish.data?.fields ?? [], [
      'policy_revision_id',
      'earlier_group_id',
      'later_group_id',
      'include_reward_units',
    ]);
  const locked =
    !editable || command.pending || command.uncertain || (!!saved && !id);
  const change = (key: keyof StackValues, value: unknown) => {
    setValues((current) => ({ ...current, [key]: value }));
    setDirty(true);
    setErrors({});
    setSaved(null);
  };
  async function save(publishing = false) {
    if (
      command.pending ||
      (publishing ? !canPublish : !editable || !form.current?.reportValidity())
    )
      return;
    if (!command.uncertain) {
      if (publishing)
        frozen.current = {
          path: path + '/publish',
          method: 'POST',
          body: { expected_version: (record.data as StackDraft)?.row_version },
        };
      else {
        const validated = stackBody(values);
        setErrors(validated.errors);
        if (Object.keys(validated.errors).length) return;
        frozen.current = {
          path,
          method: id ? 'PATCH' : 'POST',
          body: {
            ...validated.body,
            ...(id
              ? { expected_version: (record.data as StackDraft)?.row_version }
              : {}),
          },
        };
      }
    }
    if (!frozen.current) return;
    const result = await command.execute<StackDraft>(frozen.current, (row) =>
      verifyStack(row, company, id),
    );
    if (result) {
      setSaved(result);
      setDirty(false);
      setReview(false);
      frozen.current = null;
      if (id) record.refresh();
    }
  }
  function refresh() {
    command.clear();
    frozen.current = null;
    record.refresh();
    fields.refresh();
    groups.refresh();
    pairs.refresh();
    context.refresh();
  }
  const failure =
    record.failure ??
    context.failure ??
    fields.failure ??
    groups.failure ??
    pairs.failure ??
    draftPublish.failure ??
    policyPublish.failure ??
    groupPublish.failure ??
    pairPublish.failure ??
    command.failure;
  const title = published
    ? 'Published stacking policy'
    : id
      ? 'Stacking policy draft'
      : 'New stacking policy draft';
  return (
    <div className="janso-page">
      <Navigation title={title} back={back} leave={guard.leave} />
      <PageHeader
        title={title}
        lede="Define combinations explicitly and review their order before publication."
        actions={
          canPublish ? (
            <Button onClick={() => setReview(true)}>Review and publish</Button>
          ) : undefined
        }
      />
      <Notice>{explanation}</Notice>
      <ProfileFailure
        failure={failure}
        retry={() =>
          command.uncertain
            ? void save(review)
            : dirty
              ? setReload(true)
              : refresh()
        }
      />
      {record.loading || fields.loading || groups.loading || pairs.loading ? (
        <Notice>Loading the complete policy...</Notice>
      ) : null}
      {!complete && !record.loading && (
        <Notice tone="warning">
          The complete native policy cannot be reviewed. Editing and publication
          are unavailable; stored groups and permissions are retained.
        </Notice>
      )}
      {published && (
        <Notice>
          Published policy content is immutable. Create another draft with the
          same policy code to publish a replacement version. Operational
          suspension belongs to the sale authority.
        </Notice>
      )}
      {saved && (
        <Notice tone="success">
          {saved.published_policy_id
            ? 'Stacking policy published. '
            : 'Policy draft saved. '}
          {saved.published_policy_id ? (
            <a
              className="janso-link"
              href={stackRoot + '/revisions/' + saved.published_policy_id}
            >
              Open published policy
            </a>
          ) : !id ? (
            <a className="janso-link" href={stackRoot + '/drafts/' + saved.id}>
              Open saved draft
            </a>
          ) : null}
        </Notice>
      )}
      <form
        ref={form}
        onSubmit={(event) => {
          event.preventDefault();
          void save();
        }}
      >
        <FormLayout>
          <div className="janso-flow">
            <Card>
              <CardHeader title="Policy details" />
              <CardBody>
                <div className="janso-form-grid">
                  {allFields
                    .filter(
                      (field) =>
                        stackHeaderFields.includes(
                          field.key as (typeof stackHeaderFields)[number],
                        ) &&
                        (!published || field.key !== 'change_reason'),
                    )
                    .map((field) => (
                      <ProfileField
                        key={field.key}
                        company={company}
                        field={field}
                        value={values[field.key as keyof StackValues]}
                        disabled={locked}
                        error={
                          errors[field.key] ??
                          command.failure?.fields?.[field.key]
                        }
                        onChange={(value) =>
                          change(field.key as keyof StackValues, value)
                        }
                        access={noProfiles}
                      />
                    ))}
                </div>
              </CardBody>
            </Card>
            {complete && (
              <StackGroups
                company={company}
                values={values}
                fields={groupFields}
                pairFields={pairFields}
                locked={locked}
                errors={errors}
                onChange={change}
              />
            )}
            <FormActions>
              <a
                className="janso-btn janso-btn--ghost"
                href={back}
                onClick={guard.leave}
              >
                Back to policies
              </a>
              {!published && (
                <Button
                  type="submit"
                  disabled={
                    !editable ||
                    (command.blocked && !command.uncertain) ||
                    (!!saved && !id)
                  }
                >
                  {command.uncertain && !review
                    ? 'Retry save'
                    : 'Save policy draft'}
                </Button>
              )}
            </FormActions>
          </div>
        </FormLayout>
      </form>
      <ConfirmDialog
        open={review}
        title="Publish this stacking policy?"
        confirmLabel={
          command.uncertain ? 'Retry publication' : 'Publish policy'
        }
        busy={command.pending}
        onCancel={() => {
          if (!command.pending && !command.uncertain) {
            setReview(false);
            command.clear();
          }
        }}
        onConfirm={() => void save(true)}
      >
        <ReviewList
          items={[
            { label: 'Policy code', value: values.code },
            { label: 'Ordered groups', value: String(values.groups.length) },
            {
              label: 'Allowed pairs',
              value: String(values.permissions.length),
            },
            { label: 'Maximum applied offers', value: values.maximum_applied },
            {
              label: 'Effect',
              value:
                'Preserve this definition as an immutable version. Sale application remains separately governed.',
            },
          ]}
        />
        {command.failure && (
          <Notice tone="warning">
            {command.failure.message}
            {command.uncertain
              ? ' Retry retains the same request and key.'
              : ''}
          </Notice>
        )}
      </ConfirmDialog>
      <ConfirmDialog
        open={reload}
        title="Reload and review?"
        confirmLabel="Reload policy"
        onCancel={() => setReload(false)}
        onConfirm={() => {
          setReload(false);
          refresh();
        }}
      >
        Unsaved changes will be discarded. The last operation may already have
        completed; review the current record before another action.
      </ConfirmDialog>
      {guard.confirmation}
    </div>
  );
}
function StackGroups({
  company,
  values,
  fields,
  pairFields,
  locked,
  errors,
  onChange,
}: {
  company: string;
  values: StackValues;
  fields: readonly MasterField[];
  pairFields: readonly MasterField[];
  locked: boolean;
  errors: Record<string, string>;
  onChange: (key: keyof StackValues, value: unknown) => void;
}) {
  const label = (field: MasterField) =>
    field.label !== field.key
      ? field.label
      : (field.control?.label ?? field.key);
  function move(index: number, direction: number) {
    const groups = [...values.groups];
    [groups[index], groups[index + direction]] = [
      groups[index + direction]!,
      groups[index]!,
    ];
    onChange('groups', groups);
  }
  function remove(index: number) {
    const id = values.groups[index]!.group_id;
    onChange(
      'permissions',
      values.permissions.filter(
        (pair) => pair.earlier_group_id !== id && pair.later_group_id !== id,
      ),
    );
    onChange(
      'groups',
      values.groups.filter((_, position) => position !== index),
    );
  }
  function addPair() {
    const seen = new Set(
      values.permissions.map(
        (pair) => pair.earlier_group_id + ':' + pair.later_group_id,
      ),
    );
    for (let first = 0; first < values.groups.length; first++)
      for (let second = first + 1; second < values.groups.length; second++) {
        const earlier_group_id = values.groups[first]!.group_id,
          later_group_id = values.groups[second]!.group_id;
        if (!seen.has(earlier_group_id + ':' + later_group_id)) {
          onChange('permissions', [
            ...values.permissions,
            { earlier_group_id, later_group_id, include_reward_units: false },
          ]);
          return;
        }
      }
  }
  return (
    <>
      <section className="janso-flow" aria-label="Ordered offer groups">
        <div className="janso-toolbar">
          <div className="janso-toolbar__side">
            <SectionHeader
              title="Ordered offer groups"
              description="Product and scheme groups come first, then basket offers, then manual discounts."
            />
          </div>
          <div className="janso-toolbar__side janso-toolbar__side--end">
            <Button
              type="button"
              variant="ghost"
              disabled={locked || values.groups.length >= 20}
              onClick={() =>
                onChange('groups', [
                  ...values.groups,
                  {
                    group_id: crypto.randomUUID(),
                    stage: values.groups.at(-1)?.stage ?? 'PRODUCT_SCHEME',
                    selection: 'PRIORITY',
                    changes_basket: false,
                  } satisfies StackGroup,
                ])
              }
            >
              Add offer group
            </Button>
          </div>
        </div>
        {errors.groups && <Notice tone="warning">{errors.groups}</Notice>}
        {!values.groups.length && (
          <Notice>
            No offer groups added. Publication requires at least one group.
          </Notice>
        )}
        {values.groups.map((group, index) => (
          <section
            key={group.group_id}
            aria-label={'Offer group ' + (index + 1)}
          >
            <Card nested>
              <CardHeader
                title={'Group ' + (index + 1)}
                action={
                  <Menu
                    label={'Group ' + (index + 1) + ' actions'}
                    items={[
                      {
                        id: 'up',
                        label: 'Move up',
                        disabledReason:
                          locked || index === 0
                            ? 'This group cannot move up.'
                            : undefined,
                      },
                      {
                        id: 'down',
                        label: 'Move down',
                        disabledReason:
                          locked || index === values.groups.length - 1
                            ? 'This group cannot move down.'
                            : undefined,
                      },
                      {
                        id: 'remove',
                        label: 'Remove group',
                        destructive: true,
                        disabledReason: locked
                          ? 'This policy cannot be edited.'
                          : undefined,
                      },
                    ]}
                    onSelect={(action) =>
                      action === 'remove'
                        ? remove(index)
                        : move(index, action === 'up' ? -1 : 1)
                    }
                  />
                }
              />
              <CardBody>
                <div className="janso-form-grid">
                  {fields
                    .filter((field) =>
                      ['stage', 'selection', 'changes_basket'].includes(
                        field.key,
                      ),
                    )
                    .map((field) => (
                      <ProfileField
                        key={field.key}
                        company={company}
                        field={field}
                        value={group[field.key as keyof StackGroup]}
                        disabled={locked}
                        onChange={(value) =>
                          onChange(
                            'groups',
                            values.groups.map((row, position) =>
                              position === index
                                ? { ...row, [field.key]: value }
                                : row,
                            ),
                          )
                        }
                        access={noProfiles}
                      />
                    ))}
                </div>
              </CardBody>
            </Card>
          </section>
        ))}
      </section>
      <section className="janso-flow" aria-label="Allowed stacking pairs">
        <div className="janso-toolbar">
          <div className="janso-toolbar__side">
            <SectionHeader
              title="Allowed stacking pairs"
              description="Only earlier-to-later pairs may combine. No pair grants implicit permission to other groups."
            />
          </div>
          <div className="janso-toolbar__side janso-toolbar__side--end">
            <Button
              type="button"
              variant="ghost"
              disabled={
                locked ||
                values.permissions.length >=
                  (values.groups.length * (values.groups.length - 1)) / 2
              }
              onClick={addPair}
            >
              Allow a combination
            </Button>
          </div>
        </div>
        {errors.permissions && (
          <Notice tone="warning">{errors.permissions}</Notice>
        )}
        {!values.permissions.length && (
          <Notice>No stacking pairs allowed.</Notice>
        )}
        {values.permissions.map((pair, index) => (
          <Card nested key={index}>
            <CardHeader
              title={'Allowed pair ' + (index + 1)}
              action={
                <Button
                  type="button"
                  variant="ghost"
                  disabled={locked}
                  onClick={() =>
                    onChange(
                      'permissions',
                      values.permissions.filter(
                        (_, position) => position !== index,
                      ),
                    )
                  }
                >
                  Remove pair {index + 1}
                </Button>
              }
            />
            <CardBody>
              <div className="janso-form-grid">
                {pairFields
                  .filter(
                    (field) =>
                      [
                        'earlier_group_id',
                        'later_group_id',
                        'include_reward_units',
                      ].includes(field.key) &&
                      field.visible &&
                      !field.conditional_access,
                  )
                  .map((field) =>
                    field.key === 'include_reward_units' ? (
                      <Checkbox
                        key={field.key}
                        checked={pair.include_reward_units ?? false}
                        disabled={locked || !field.writable}
                        onChange={(event) =>
                          onChange(
                            'permissions',
                            values.permissions.map((row, position) =>
                              position === index
                                ? {
                                    ...row,
                                    include_reward_units: event.target.checked,
                                  }
                                : row,
                            ),
                          )
                        }
                      >
                        {label(field)}
                      </Checkbox>
                    ) : (
                      <Select
                        key={field.key}
                        label={label(field)}
                        value={
                          pair[
                            field.key as 'earlier_group_id' | 'later_group_id'
                          ]
                        }
                        disabled={locked || !field.writable}
                        options={values.groups.map((group, position) => ({
                          value: group.group_id,
                          label:
                            'Group ' +
                            (position + 1) +
                            ' - ' +
                            group.stage.replaceAll('_', ' ').toLowerCase(),
                        }))}
                        onChange={(value) =>
                          onChange(
                            'permissions',
                            values.permissions.map((row, position) =>
                              position === index
                                ? { ...row, [field.key]: value }
                                : row,
                            ),
                          )
                        }
                      />
                    ),
                  )}
              </div>
            </CardBody>
          </Card>
        ))}
      </section>
    </>
  );
}
