'use client';
import { useEffect, useState } from 'react';
import { masterRevisionActions } from '../lib/master-navigation';
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  ConfirmDialog,
  DataTable,
  FormActions,
  FormLayout,
  Notice,
  PageHeader,
  Pager,
  SectionHeader,
  useFormatters,
} from '@janso/ui';
import type { MasterRow } from '../lib/catalog-masters';
import type { EmbeddedMasterEditor } from '../lib/embedded-master-editor';
import { masterRequest } from '../lib/catalog-master-api';
import { nativeProductInitial } from '../lib/product-entry-policy';
import {
  catalogBack,
  catalogBase,
  catalogId,
  catalogLink,
  catalogReceipt,
  catalogVisible,
  catalogWritable,
  nativeCatalogBody,
  useCatalogFields,
  validateTypeRequirements,
} from '../lib/product-classification';
import {
  typeRevisionDefaults,
  type ClassificationAccess,
} from '../lib/product-classification-resources';
import {
  useServiceCommand,
  useServiceList,
  useServiceRead,
} from '../lib/service-resource';
import type { ServiceRequest } from '../lib/service-call';
import { AccessFocusErrors, useAccessDraft } from './AccessCommon';
import {
  ProductCatalogField,
  ProductCatalogFailure,
  ProductCatalogNavigation,
} from './ProductCatalogCommon';

export function ProductTypeHistory({
  company,
  parentId,
  active,
  here,
  canManage,
  blocked,
  onLeave,
}: {
  company: string;
  parentId: string;
  active: boolean;
  here: string;
  canManage: boolean;
  blocked: boolean;
  onLeave?: React.MouseEventHandler<HTMLAnchorElement>;
}) {
  const root = '/masters/product-types/' + parentId + '/revisions',
    metadata = useCatalogFields(company, 'catalog.product_type_revision'),
    fields = metadata.data?.fields ?? [],
    format = useFormatters();
  const list = useServiceList<MasterRow>(
    catalogBase(company, 'product-types/' + parentId + '/revisions'),
    catalogVisible(fields, 'revision') ? 'sort=-revision' : 'sort=-id',
    masterRequest,
    (row) => {
      if (
        !catalogId.test(row.id) ||
        ('product_type_id' in row && row.product_type_id !== parentId)
      )
        throw {
          status: 502,
          message: 'The revision history does not match this type.',
        };
    },
  );
  const failure = metadata.failure ?? list.failure;
  return (
    <Card>
      <CardHeader
        title="Requirements revisions"
        action={
          canManage && active && !blocked ? (
            <a
              className="janso-btn janso-btn--primary"
              href={catalogLink(root + '/new', here)}
              onClick={onLeave}
            >
              New draft revision
            </a>
          ) : undefined
        }
      />
      <CardBody>
        <p className="janso-fine">
          Published requirements remain immutable. A new revision applies when
          explicitly selected or adopted by products.
        </p>
        <ProductCatalogFailure
          failure={failure}
          retry={() => {
            metadata.refresh();
            list.first();
          }}
        />
      </CardBody>
      <DataTable
        rowActions={(row) =>
          masterRevisionActions(
            root,
            row,
            here,
            canManage && active && catalogVisible(fields, 'published_at'),
            blocked,
          )
        }
        caption="Product type requirements revisions"
        columns={[
          {
            key: 'record',
            header: 'Revision',
            type: 'custom',
            render: (row) => (
              <a
                className="janso-link"
                href={catalogLink(root + '/' + row.id, here)}
                onClick={onLeave}
              >
                {catalogVisible(fields, 'revision') && row.revision != null
                  ? 'Revision ' + row.revision
                  : 'View revision'}
              </a>
            ),
          },
          ...(catalogVisible(fields, 'published_at')
            ? [
                {
                  key: 'published_at',
                  header: 'Status',
                  type: 'custom' as const,
                  render: (row: MasterRow) =>
                    'published_at' in row
                      ? row.published_at
                        ? 'Published ' +
                          format.date(String(row.published_at).slice(0, 10))
                        : 'Draft'
                      : 'Protected',
                },
              ]
            : []),
        ]}
        rows={failure ? [] : (list.data?.items ?? [])}
        rowId={(row) => row.id}
        loading={metadata.loading || list.loading}
        emptyTitle="No requirements revisions"
        emptyBody="Create and publish a draft to make this product type available to new families."
      />
      <Pager
        count={list.loading || failure ? 0 : (list.data?.items.length ?? 0)}
        from={list.hasPrevious ? null : 1}
        limit={list.limit}
        hasPrevious={list.hasPrevious}
        hasNext={!!list.data?.page.has_more}
        onPrevious={list.previous}
        onNext={list.next}
        busy={list.loading || blocked}
        noun="revision"
      />
    </Card>
  );
}
export function ProductTypeRevision({
  company,
  parentId,
  id,
  canManage,
  access,
  returnTo,
  embedded,
}: {
  company: string;
  parentId: string;
  id?: string;
  canManage: boolean;
  access: ClassificationAccess;
  returnTo?: string;
  embedded?: EmbeddedMasterEditor;
}) {
  const parentRoot = '/masters/product-types/' + parentId,
    back = catalogBack(returnTo, parentRoot),
    root = parentRoot + '/revisions',
    entity = 'catalog.product_type_revision';
  const parent = useServiceRead<MasterRow>(
    catalogBase(company, 'product-types/' + parentId),
    masterRequest,
    (row) => catalogReceipt(row, company, parentId),
  );
  const record = useServiceRead<MasterRow>(
    id
      ? catalogBase(company, 'product-types/' + parentId + '/revisions/' + id)
      : undefined,
    masterRequest,
    (row) =>
      catalogReceipt(row, company, id, {
        key: 'product_type_id',
        id: parentId,
      }),
  );
  const metadata = useCatalogFields(company, entity, id ? 'update' : 'create'),
    publication = useCatalogFields(
      company,
      entity,
      'publish',
      undefined,
      !!id && access.publish,
    );
  const fields = metadata.data?.fields ?? [],
    publisherFields = publication.data?.fields ?? [];
  const [values, setValues] = useState<Record<string, unknown>>({}),
    [initialized, setInitialized] = useState(false),
    [dirty, setDirty] = useState(false),
    [errors, setErrors] = useState<Record<string, string>>({}),
    [saved, setSaved] = useState<MasterRow | null>(null),
    [frozen, setFrozen] = useState<ServiceRequest | null>(null),
    [confirm, setConfirm] = useState(false),
    [reload, setReload] = useState(false),
    [message, setMessage] = useState('');
  const command = useServiceCommand(masterRequest, 'product type revisions'),
    guard = useAccessDraft(
      dirty || command.uncertain || confirm,
      command.pending,
    ),
    format = useFormatters();
  useEffect(() => { embedded?.onStateChange({ dirty: dirty || confirm, busy: command.pending || command.uncertain }); }, [embedded?.onStateChange, dirty, confirm, command.pending, command.uncertain]);
  useEffect(() => {
    if (
      metadata.loading ||
      record.loading ||
      parent.loading ||
      (id && !record.data)
    ) {
      setInitialized(false);
      return;
    }
    setValues(
      id
        ? { ...record.data }
        : nativeProductInitial(fields, structuredClone(typeRevisionDefaults)),
    );
    setInitialized(true);
    setDirty(false);
    setSaved(null);
    setFrozen(null);
    setErrors({});
  }, [metadata.data, record.data, parent.data, id]);
  useEffect(() => {
    if (command.failure?.fields) setErrors(command.failure.fields);
  }, [command.failure]);
  const unconfirmedPublication =
    command.uncertain && !!frozen?.path.endsWith('/publish');
  const row = saved ?? record.data,
    active = parent.data?.is_active === true,
    draft = !id || (!!row && row.published_at === null),
    keys = Object.keys(typeRevisionDefaults);
  const systemReadable = [
    'product_type_id',
    'row_version',
    'revision',
    'published_at',
  ].every((key) => catalogVisible(fields, key));
  const canSave =
    canManage &&
    active &&
    draft &&
    (id
      ? systemReadable && keys.some((key) => catalogWritable(fields, [key]))
      : catalogWritable(fields, [
          'product_type_id',
          ...keys.filter((key) => typeRevisionDefaults[key] != null),
        ]));
  const canPublish =
    !!id &&
    access.publish &&
    active &&
    draft &&
    systemReadable &&
    !dirty &&
    !!row &&
    catalogWritable(publisherFields, [
      'published_at',
      ...keys.filter((key) => row[key] != null),
    ]);
  const failure =
      parent.failure ??
      record.failure ??
      metadata.failure ??
      publication.failure,
    loading =
      parent.loading ||
      record.loading ||
      metadata.loading ||
      publication.loading ||
      (!initialized && !failure);
  function refresh() {
    parent.refresh();
    record.refresh();
    metadata.refresh();
    publication.refresh();
  }
  async function save() {
    if (
      !canSave ||
      loading ||
      failure ||
      (command.blocked && !command.uncertain)
    )
      return;
    let request = frozen;
    if (!command.uncertain || !request) {
      const result = nativeCatalogBody(
        fields,
        keys,
        values,
        id ? (row ?? undefined) : undefined,
      );
      Object.assign(
        result.errors,
        validateTypeRequirements(values, parent.data?.kind),
      );
      setErrors(result.errors);
      if (Object.keys(result.errors).length) return;
      if (id && Object.keys(result.body).length === 1) {
        setMessage('No changes to save.');
        setDirty(false);
        return;
      }
      request = {
        path: catalogBase(
          company,
          'product-types/' + parentId + '/revisions' + (id ? '/' + id : ''),
        ),
        method: id ? 'PATCH' : 'POST',
        body: result.body,
      };
      setFrozen(request);
    }
    const result = await command.execute<MasterRow>(request, (response) =>
      catalogReceipt(response, company, id, {
        key: 'product_type_id',
        id: parentId,
      }),
    );
    if (result) {
      setSaved(result);
      setValues(result);
      setDirty(false);
      setFrozen(null);
      setMessage('Draft requirements saved. Review them before publication.');
      embedded?.onSaved(result);
    }
  }
  async function publish() {
    if (!canPublish || !row || (command.blocked && !command.uncertain)) return;
    const request = frozen ?? {
      path: catalogBase(
        company,
        'product-types/' + parentId + '/revisions/' + id + '/publish',
      ),
      method: 'POST',
      body: { expected_version: row.row_version },
    };
    setFrozen(request);
    const result = await command.execute<MasterRow>(request, (response) => {
      catalogReceipt(response, company, id, {
        key: 'product_type_id',
        id: parentId,
      });
      if (!response.published_at)
        throw {
          status: 502,
          message:
            'Publication could not be verified. Retry the same publication.',
        };
    });
    if (result) {
      setSaved(result);
      setValues(result);
      setConfirm(false);
      setFrozen(null);
      setMessage(
        'Requirements published. This revision is now available for new product families.',
      );
      embedded?.onSaved(result);
    }
  }
  return (
    <div className="janso-page">
      {!embedded && <ProductCatalogNavigation
        resource={'product-types'}
        title={id ? 'Product type requirements' : 'New requirements revision'}
        back={back}
        access={access}
        onLeave={guard.leave}
      />}
      <PageHeader
        title={
          id
            ? `Requirements revision ${row?.revision ?? ''}`
            : 'New requirements revision'
        }
        lede={
          parent.data?.name
            ? 'Product type: ' + parent.data.name
            : 'Define how products of this type behave.'
        }
        actions={
          canPublish && (
            <Button
              disabled={command.blocked}
              onClick={() => {
                setFrozen(null);
                setConfirm(true);
              }}
            >
              Publish requirements
            </Button>
          )
        }
      />
      {unconfirmedPublication && !confirm && (
        <Button
          disabled={command.pending}
          onClick={() => {
            setConfirm(true);
            void publish();
          }}
        >
          Retry same publication
        </Button>
      )}
      <ProductCatalogFailure
        failure={failure ?? (!confirm ? command.failure : null)}
        write={!failure}
        retry={
          failure
            ? refresh
            : command.failure?.status === 409
              ? () => setReload(true)
              : undefined
        }
      />
      {message && <Notice tone="success">{message}</Notice>}
      {loading ? (
        <p role="status">Loading requirements...</p>
      ) : failure ? null : !id && saved ? (
        <Card>
          <CardBody>
            <a
              className="janso-btn janso-btn--primary"
              href={catalogLink(root + '/' + saved.id, back)}
            >
              Review saved draft
            </a>
          </CardBody>
        </Card>
      ) : (
        <FormLayout
          aside={
            <div className="janso-flow">
              <SectionHeader title="Publish with confidence" />
              <p className="janso-fine">
                Choose allowed inventory, tracking and unit modes. Services use
                non-stock inventory without physical tracking. Serial tracking
                requires count units.
              </p>
              {!!row?.published_at && (
                <Notice>
                  Published {format.date(String(row.published_at).slice(0, 10))}
                  . This revision is immutable.
                </Notice>
              )}
              {!active && (
                <Notice tone="warning">
                  Activate the product type before changing revisions.
                </Notice>
              )}
              {dirty && <Notice>Save your changes before publishing.</Notice>}
            </div>
          }
        >
          <form
            noValidate
            onSubmit={(event) => {
              event.preventDefault();
              void save();
            }}
          >
            <Card>
              <CardBody>
                <div className="janso-flow">
                  <SectionHeader title="Allowed modes and requirements" />
                  <div className="janso-form-grid">
                    {fields
                      .filter(
                        (field) =>
                          keys.includes(field.key) &&
                          !field.key.endsWith('_id'),
                      )
                      .map((field) => (
                        <ProductCatalogField
                          returnTo={
                            id ? catalogLink(root + '/' + id, back) : undefined
                          }
                          onLeave={guard.leave}
                          key={field.key}
                          company={company}
                          field={field}
                          values={values}
                          access={access}
                          disabled={!canSave || command.blocked}
                          error={errors[field.key]}
                          onChange={(next) => {
                            setValues((current) => ({
                              ...current,
                              [field.key]: next,
                            }));
                            setDirty(true);
                            setErrors({});
                          }}
                        />
                      ))}
                  </div>
                  <SectionHeader
                    title="Reusable defaults"
                    description="Optional. Choose published profiles; leave empty when products should supply their own settings."
                  />
                  <div className="janso-form-grid">
                    {fields
                      .filter(
                        (field) =>
                          keys.includes(field.key) && field.key.endsWith('_id'),
                      )
                      .map((field) => (
                        <ProductCatalogField
                          returnTo={
                            id ? catalogLink(root + '/' + id, back) : undefined
                          }
                          onLeave={guard.leave}
                          key={field.key}
                          company={company}
                          field={field}
                          values={values}
                          access={access}
                          disabled={!canSave || command.blocked}
                          error={errors[field.key]}
                          onChange={(next) => {
                            setValues((current) => ({
                              ...current,
                              [field.key]: next,
                            }));
                            setDirty(true);
                            setErrors({});
                          }}
                        />
                      ))}
                  </div>
                  {Object.keys(errors).length > 0 && (
                    <Notice tone="danger">
                      <ul>
                        {[...new Set(Object.values(errors))].map((error) => (
                          <li key={error}>{error}</li>
                        ))}
                      </ul>
                    </Notice>
                  )}
                </div>
              </CardBody>
              <FormActions cancel={embedded ? { onCancel: embedded.onCancel, disabled: command.pending || command.uncertain } : { href: back, onClick: guard.leave }}>
                <Button
                  type="submit"
                  disabled={
                    !canSave ||
                    unconfirmedPublication ||
                    (command.blocked && !command.uncertain)
                  }
                  loading={command.pending}
                  loadingLabel="Saving..."
                >
                  {command.uncertain && !unconfirmedPublication
                    ? 'Retry same save'
                    : 'Save draft requirements'}
                </Button>
              </FormActions>
            </Card>
          </form>
        </FormLayout>
      )}
      <ConfirmDialog
        open={confirm}
        title="Publish product type requirements?"
        confirmLabel={
          command.uncertain ? 'Retry same publication' : 'Publish requirements'
        }
        busy={command.pending}
        error={command.failure?.message}
        onCancel={() => {
          setConfirm(false);
          if (!command.uncertain) {
            setFrozen(null);
            command.clear();
          }
        }}
        onConfirm={() => void publish()}
      >
        <p>
          The reviewed requirements will become immutable and selectable for new
          families. Existing products retain their selected revision.
        </p>
      </ConfirmDialog>
      <ConfirmDialog
        open={reload && !command.uncertain}
        title="Discard draft and reload?"
        confirmLabel="Discard and reload"
        onCancel={() => setReload(false)}
        onConfirm={() => {
          command.clear();
          setReload(false);
          setConfirm(false);
          setFrozen(null);
          refresh();
        }}
      >
        Reload and review the latest requirements before saving.
      </ConfirmDialog>
      {guard.confirmation}
      <AccessFocusErrors fields={errors} />
    </div>
  );
}
