'use client';
import { useEffect, useRef, useState } from 'react';
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  ConfirmDialog,
  DataTable,
  FilterBar,
  FormActions,
  FormLayout,
  Notice,
  PageHeader,
  Pager,
  ReviewList,
  SectionHeader,
  TableSearch,
  TextField,
  type Column,
} from '@janso/ui';
import type { MasterConfig, MasterRow } from '../lib/catalog-masters';
import {
  assertMaster,
  masterRequest,
  useMasterRecord,
} from '../lib/catalog-master-api';
import {
  useServiceCommand,
  useServiceList,
  useServiceRead,
  type ServicePage,
} from '../lib/service-resource';
import { bomBase, bomId, bomWritable, type BomAccess } from '../lib/boms';
import { masterLink, masterReturn } from '../lib/master-navigation';
import { useProfileFields } from '../lib/product-profiles';
import { ProfileFailure } from './ProductProfileCommon';
import { useAccessDraft } from './AccessCommon';
import { BomExplanation, BomNavigation, useBomContext } from './BomCommon';
import { BomDefinition } from './BomDefinition';
import { BomApplicabilityList, BomAssignment } from './BomAssignment';

export function BomMasterPage({
  company,
  config,
  record,
  access,
  returnTo,
}: {
  company: string;
  config: MasterConfig;
  record: string[];
  access: BomAccess;
  returnTo?: string;
}) {
  const id = record[0] === 'new' ? undefined : record[0];
  if (record[1] === 'drafts' || record[1] === 'revisions')
    return (
      <BomDefinition
        company={company}
        bom={id!}
        id={record[2] === 'new' ? undefined : record[2]}
        published={record[1] === 'revisions'}
        access={access}
        returnTo={returnTo}
      />
    );
  if (record[1] === 'assignments')
    return (
      <BomAssignment
        company={company}
        bom={id!}
        id={record[2] === 'new' ? undefined : record[2]}
        access={access}
        returnTo={returnTo}
      />
    );
  if (record[0] === 'new' || record[1] === 'edit')
    return (
      <BomIdentityEditor
        company={company}
        config={config}
        id={id}
        returnTo={returnTo}
      />
    );
  if (id)
    return (
      <BomDetail
        company={company}
        config={config}
        id={id}
        access={access}
        returnTo={returnTo}
      />
    );
  return <BomDirectory company={company} access={access} returnTo={returnTo} />;
}

function BomDirectory({
  company,
  access,
  returnTo,
}: {
  company: string;
  access: BomAccess;
  returnTo?: string;
}) {
  const [search, setSearch] = useState('');
  const fields = useProfileFields(company, 'catalog.bom'),
    context = useBomContext(company);
  const readable = fields.data?.fields ?? [];
  const canSearch = ['code', 'name'].every((key) =>
    readable.some((field) => field.key === key && !field.conditional_access),
  );
  const query = new URLSearchParams({ sort: 'id' });
  if (canSearch && search.trim().length >= 2) query.set('q', search.trim());
  const list = useServiceList<MasterRow>(
    bomBase(company),
    query.toString(),
    masterRequest,
    (row) => {
      if (!bomId(row.id))
        throw { status: 502, message: 'BOM directory could not be verified.' };
    },
  );
  const columns: Column<MasterRow>[] = ['code', 'name', 'is_active']
    .filter((key) =>
      readable.some((field) => field.key === key && !field.conditional_access),
    )
    .map((key) => ({
      key,
      header: key === 'is_active' ? 'Status' : key === 'code' ? 'Code' : 'Name',
      type: 'custom',
      render: (row) =>
        key === 'is_active' ? (
          row.is_active ? (
            'Active'
          ) : (
            'Inactive'
          )
        ) : (
          <a
            className="janso-link"
            href={masterLink('/masters/boms/' + row.id, '/masters/boms')}
          >
            {String(row[key] ?? 'Protected')}
          </a>
        ),
    }));
  if (!columns.length)
    columns.push({
      key: 'record',
      header: 'BOM',
      type: 'custom',
      render: (row) => (
        <a className="janso-link" href={'/masters/boms/' + row.id}>
          View BOM
        </a>
      ),
    });
  return (
    <div className="janso-page">
      <BomNavigation
        title="Bills of materials"
        back={masterReturn(returnTo, '/masters')}
      />
      <PageHeader
        title="Bills of materials"
        lede="Single-level recipes, published definitions and dated applicability for this company."
        actions={
          access.manage && context.data?.enabled ? (
            <a
              className="janso-btn janso-btn--primary"
              href={masterLink('/masters/boms/new', '/masters/boms')}
            >
              New BOM
            </a>
          ) : undefined
        }
      />
      <BomExplanation />
      {context.data && !context.data.enabled && (
        <Notice>
          BOM authoring is disabled. Enable BOM definitions in Company
          configuration to add or publish recipes. Existing history remains
          available.
        </Notice>
      )}
      <ProfileFailure
        failure={fields.failure ?? list.failure ?? context.failure}
        retry={() => {
          fields.refresh();
          list.first();
          context.refresh();
        }}
      />
      <Card>
        <CardHeader title="BOM directory" />
        <FilterBar
          actions={
            <Button
              variant="ghost"
              onClick={list.first}
              disabled={list.loading}
            >
              Refresh
            </Button>
          }
        >
          {canSearch ? (
            <TableSearch
              label="Search BOMs"
              placeholder="Find by code or name"
              value={search}
              onChange={setSearch}
              minLength={2}
              maxLength={200}
            />
          ) : (
            <Notice>Search requires access to the BOM code and name.</Notice>
          )}
        </FilterBar>
        <DataTable
          caption="Bills of materials"
          columns={columns}
          rows={list.data?.items ?? []}
          rowId={(row) => row.id}
          rowLabel={(row) => row.name ?? row.code ?? 'BOM'}
          loading={fields.loading || list.loading}
          emptyTitle="No BOMs found"
          emptyBody="Create a BOM or adjust the search."
          rowActions={(row) => [
            {
              id: 'view',
              label: 'View BOM and recipes',
              href: masterLink('/masters/boms/' + row.id, '/masters/boms'),
            },
          ]}
        />
        <Pager
          noun="BOM"
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
    </div>
  );
}

function BomIdentityEditor({
  company,
  config,
  id,
  returnTo,
}: {
  company: string;
  config: MasterConfig;
  id?: string;
  returnTo?: string;
}) {
  const record = useMasterRecord(company, config, id, true),
    context = useBomContext(company);
  const [values, setValues] = useState({ code: '', name: '' }),
    [dirty, setDirty] = useState(false),
    [saved, setSaved] = useState<MasterRow | null>(null);
  const [reload, setReload] = useState(false),
    frozen = useRef<Record<string, unknown> | null>(null);
  const history = useServiceRead<ServicePage<MasterRow>>(
    id ? bomBase(company, '/' + id + '/drafts?limit=1&sort=-id') : undefined,
    masterRequest,
  );
  const codeLocked =
    !!id &&
    (history.loading || !!history.failure || !!history.data?.items.length);
  const command = useServiceCommand(masterRequest, 'BOM'),
    guard = useAccessDraft(dirty || command.uncertain, command.pending),
    form = useRef<HTMLFormElement>(null);
  useEffect(() => {
    if (!record.loading) {
      setValues({
        code: String(record.row?.code ?? ''),
        name: String(record.row?.name ?? ''),
      });
      setDirty(false);
    }
  }, [record.loading, record.row]);
  const editable = record.fields
    .filter(
      (field) =>
        ['code', 'name'].includes(field.key) &&
        field.visible &&
        !field.conditional_access,
    )
    .map((field) => ({
      ...field,
      writable: field.writable && !(field.key === 'code' && codeLocked),
    }));
  const fieldsReady = id
    ? Number.isSafeInteger(record.row?.row_version) &&
      editable.some((field) => field.writable)
    : bomWritable(record.fields, ['code', 'name', 'is_active']);
  async function save() {
    if (
      !form.current?.reportValidity() ||
      !fieldsReady ||
      !context.data?.enabled ||
      command.pending
    )
      return;
    if (!command.uncertain) {
      const body: Record<string, unknown> = {};
      editable
        .filter((field) => field.writable)
        .forEach((field) => {
          body[field.key] = values[field.key as keyof typeof values];
        });
      if (id) body.expected_version = record.row?.row_version;
      frozen.current = body;
    }
    if (!frozen.current) return;
    const body = frozen.current;
    const result = await command.execute<MasterRow>(
      {
        path: bomBase(company, id ? '/' + id : ''),
        method: id ? 'PATCH' : 'POST',
        body,
      },
      (row) => assertMaster(row, company, id),
    );
    if (result) {
      setSaved(result);
      setDirty(false);
      frozen.current = null;
    }
  }
  const back = masterReturn(
    returnTo,
    id ? '/masters/boms/' + id : '/masters/boms',
  );
  return (
    <div className="janso-page">
      <BomNavigation
        title={id ? 'Edit BOM details' : 'New BOM'}
        back={back}
        onLeave={guard.leave}
      />
      <PageHeader
        title={id ? 'Edit BOM details' : 'New BOM'}
        lede="Start with a stable code and a useful name. Recipes are reviewed and published separately."
      />
      <ProfileFailure
        failure={
          record.failure ??
          context.failure ??
          history.failure ??
          command.failure
        }
        retry={() => {
          if (command.uncertain) void save();
          else if (dirty) setReload(true);
          else {
            command.clear();
            record.refresh();
            context.refresh();
            history.refresh();
          }
        }}
      />
      {context.data && !context.data.enabled && (
        <Notice>
          Enable BOM definitions in Company configuration before creating or
          editing a BOM.
        </Notice>
      )}
      {saved ? (
        <Card>
          <CardBody>
            <Notice tone="success">BOM details saved.</Notice>
            <FormActions>
              <a
                className="janso-btn janso-btn--primary"
                href={'/masters/boms/' + saved.id}
              >
                Open BOM
              </a>
              <a
                className="janso-btn janso-btn--ghost"
                href={'/masters/boms/' + saved.id + '/drafts/new'}
              >
                Add recipe
              </a>
            </FormActions>
          </CardBody>
        </Card>
      ) : (
        <form
          ref={form}
          onSubmit={(event) => {
            event.preventDefault();
            void save();
          }}
        >
          <FormLayout>
            <Card>
              <CardBody>
                {record.loading || context.loading ? (
                  <Notice>Loading BOM settings…</Notice>
                ) : (
                  <div className="janso-form-grid">
                    {editable.map((field) => (
                      <TextField
                        key={field.key}
                        label={
                          field.label !== field.key
                            ? field.label
                            : (field.control?.label ?? field.key)
                        }
                        name={field.key}
                        value={values[field.key as keyof typeof values]}
                        maxLength={field.control?.max_length ?? undefined}
                        required
                        disabled={
                          !field.writable ||
                          !context.data?.enabled ||
                          command.pending ||
                          command.uncertain
                        }
                        pattern={
                          field.key === 'code'
                            ? '[A-Z0-9][A-Z0-9_.-]*'
                            : undefined
                        }
                        error={command.failure?.fields?.[field.key]}
                        onChange={(event) => {
                          setValues((current) => ({
                            ...current,
                            [field.key]: event.target.value,
                          }));
                          setDirty(true);
                        }}
                      />
                    ))}
                  </div>
                )}
                {!fieldsReady && !record.loading && (
                  <Notice tone="warning">
                    The required BOM fields are unavailable for editing.
                  </Notice>
                )}
                {id && (
                  <Notice>
                    The BOM code cannot change after its first recipe draft is
                    created.
                  </Notice>
                )}
              </CardBody>
            </Card>
            <FormActions>
              <a
                className="janso-btn janso-btn--ghost"
                href={back}
                onClick={guard.leave}
              >
                Cancel
              </a>
              <Button
                type="submit"
                disabled={
                  !fieldsReady ||
                  !context.data?.enabled ||
                  (command.blocked && !command.uncertain) ||
                  record.loading
                }
              >
                {command.uncertain ? 'Retry save' : 'Save BOM'}
              </Button>
            </FormActions>
          </FormLayout>
        </form>
      )}
      <ConfirmDialog
        open={reload}
        title="Reload and review?"
        confirmLabel="Reload BOM"
        onCancel={() => setReload(false)}
        onConfirm={() => {
          setReload(false);
          command.clear();
          frozen.current = null;
          record.refresh();
          context.refresh();
          history.refresh();
        }}
      >
        Unsaved changes will be discarded. Review the current record before
        another change.
      </ConfirmDialog>
      {guard.confirmation}
    </div>
  );
}

function BomHistory({
  company,
  bom,
  collection,
}: {
  company: string;
  bom: string;
  collection: 'drafts' | 'revisions';
}) {
  const list = useServiceList<MasterRow>(
    bomBase(company, '/' + bom + '/' + collection),
    '',
    masterRequest,
    (row) => {
      if (!bomId(row.id) || (row.bom_id && row.bom_id !== bom))
        throw { status: 502, message: 'BOM history could not be verified.' };
    },
  );
  const title = collection === 'drafts' ? 'Recipe drafts' : 'Published recipes';
  const columns: Column<MasterRow>[] = [
    {
      key: 'revision',
      header: collection === 'drafts' ? 'Draft' : 'Revision',
      type: 'custom',
      render: (row) => (
        <a
          className="janso-link"
          href={masterLink(
            `/masters/boms/${bom}/${collection}/${row.id}`,
            '/masters/boms/' + bom,
          )}
        >
          {String(
            (collection === 'drafts' ? row.draft_number : row.revision) ??
              'View recipe',
          )}
        </a>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      type: 'custom',
      render: (row) => String(row.status ?? 'Protected'),
    },
    {
      key: 'lines',
      header: 'Recipe',
      type: 'custom',
      render: (row) =>
        typeof row.component_count === 'number' &&
        typeof row.output_count === 'number'
          ? `${row.component_count} inputs · ${row.output_count} outputs`
          : 'Protected',
    },
  ];
  return (
    <section className="janso-flow" aria-label={title}>
      <SectionHeader title={title} />
      <ProfileFailure failure={list.failure} retry={list.first} />
      <Card>
        <DataTable
          caption={title}
          columns={columns}
          rows={list.data?.items ?? []}
          rowId={(row) => row.id}
          rowLabel={(row) =>
            String(row.revision ?? row.draft_number ?? 'Recipe')
          }
          loading={list.loading}
          emptyTitle={'No ' + title.toLowerCase()}
          emptyBody="Add a draft to define the recipe."
        />
        <Pager
          noun="recipe"
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

function BomDetail({
  company,
  config,
  id,
  access,
  returnTo,
}: {
  company: string;
  config: MasterConfig;
  id: string;
  access: BomAccess;
  returnTo?: string;
}) {
  const record = useMasterRecord(company, config, id, false),
    context = useBomContext(company);
  const command = useServiceCommand(masterRequest, 'BOM'),
    [action, setAction] = useState<'activate' | 'deactivate' | null>(null);
  const guard = useAccessDraft(command.uncertain, command.pending),
    frozen = useRef<{
      path: string;
      method: 'POST';
      body: { expected_version: unknown };
    } | null>(null);
  const [reload, setReload] = useState(false);
  const enabled = context.data?.enabled,
    editable =
      access.manage && enabled && Number.isSafeInteger(record.row?.row_version),
    canLifecycle =
      access.manage &&
      Number.isSafeInteger(record.row?.row_version) &&
      (record.row?.is_active === true || enabled) &&
      typeof record.row?.is_active === 'boolean';
  const lifecycle = async () => {
    if (!action || !record.row || command.pending) return;
    if (!command.uncertain)
      frozen.current = {
        path: bomBase(company, `/${id}/${action}`),
        method: 'POST',
        body: { expected_version: record.row.row_version },
      };
    if (!frozen.current) return;
    const result = await command.execute<MasterRow>(frozen.current, (row) =>
      assertMaster(row, company, id),
    );
    if (result) {
      setAction(null);
      frozen.current = null;
      record.refresh();
    }
  };
  return (
    <div className="janso-page">
      <BomNavigation
        title={record.row?.name ?? 'BOM details'}
        back={masterReturn(returnTo, '/masters/boms')}
        onLeave={guard.leave}
      />
      <PageHeader
        title={record.row?.name ?? 'BOM details'}
        lede="Review drafts, immutable publications and dated applicability."
        actions={
          editable || canLifecycle ? (
            <>
              {editable && (
                <a
                  className="janso-btn janso-btn--ghost"
                  href={masterLink(
                    '/masters/boms/' + id + '/edit',
                    '/masters/boms/' + id,
                  )}
                >
                  Edit details
                </a>
              )}
              {canLifecycle && (
                <Button
                  variant="ghost"
                  onClick={() =>
                    setAction(record.row?.is_active ? 'deactivate' : 'activate')
                  }
                >
                  {record.row?.is_active ? 'Deactivate' : 'Activate'}
                </Button>
              )}
            </>
          ) : undefined
        }
      />
      <ProfileFailure
        failure={record.failure ?? context.failure ?? command.failure}
        retry={() => {
          if (command.uncertain) void lifecycle();
          else setReload(true);
        }}
      />
      {record.loading ? (
        <Notice>Loading BOM…</Notice>
      ) : (
        record.row && (
          <Card>
            <CardBody>
              <ReviewList
                items={record.fields
                  .filter((field) =>
                    ['code', 'name', 'is_active'].includes(field.key),
                  )
                  .map((field) => ({
                    label:
                      field.label !== field.key
                        ? field.label
                        : (field.control?.label ?? field.key),
                    value:
                      field.key === 'is_active'
                        ? record.row!.is_active
                          ? 'Active'
                          : 'Inactive'
                        : String(record.row![field.key] ?? 'Protected'),
                  }))}
              />
            </CardBody>
          </Card>
        )
      )}
      <BomExplanation />
      {enabled && record.row?.is_active && access.manage && (
        <div className="janso-toolbar">
          <a
            className="janso-btn janso-btn--primary"
            href={masterLink(
              '/masters/boms/' + id + '/drafts/new',
              '/masters/boms/' + id,
            )}
          >
            Add recipe draft
          </a>
        </div>
      )}
      <BomHistory company={company} bom={id} collection="drafts" />
      <BomHistory company={company} bom={id} collection="revisions" />
      <BomApplicabilityList company={company} bom={id} />
      {access.assign && enabled && (
        <a
          className="janso-link"
          href={masterLink(
            `/masters/boms/${id}/assignments/new`,
            '/masters/boms/' + id,
          )}
        >
          Assign a published recipe
        </a>
      )}
      <ConfirmDialog
        open={!!action}
        title={(action === 'activate' ? 'Activate' : 'Deactivate') + ' BOM?'}
        confirmLabel={
          command.uncertain
            ? 'Retry ' + action
            : action === 'activate'
              ? 'Activate'
              : 'Deactivate'
        }
        busy={command.pending}
        onCancel={() => {
          if (!command.pending && !command.uncertain) {
            setAction(null);
            command.clear();
            frozen.current = null;
          }
        }}
        onConfirm={() => void lifecycle()}
      >
        History is retained. An inactive BOM is unavailable for new
        applicability or publication.
        {command.failure && (
          <Notice tone="warning">
            {command.failure.message}
            {command.uncertain
              ? ' Retry uses the same request and key.'
              : ''}{' '}
            <Button variant="ghost" onClick={() => setReload(true)}>
              Reload and review
            </Button>
          </Notice>
        )}
      </ConfirmDialog>
      <ConfirmDialog
        open={reload}
        title="Reload and review?"
        confirmLabel="Reload BOM"
        onCancel={() => setReload(false)}
        onConfirm={() => {
          setReload(false);
          setAction(null);
          command.clear();
          frozen.current = null;
          record.refresh();
          context.refresh();
        }}
      >
        The last operation may already have completed. Reload the current BOM
        before another change.
      </ConfirmDialog>
      {guard.confirmation}
    </div>
  );
}
