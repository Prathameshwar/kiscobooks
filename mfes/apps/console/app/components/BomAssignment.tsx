'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Button,
  Card,
  CardBody,
  ConfirmDialog,
  DataTable,
  FormActions,
  FormLayout,
  Notice,
  PageHeader,
  Pager,
  SearchSelect,
  SectionHeader,
  TextField,
  businessToday,
  formatDate,
  useDisplayConfig,
  type Column,
  type SearchSelectLoader,
} from '@janso/ui';
import type { MasterRow } from '../lib/catalog-masters';
import { bomBase, bomId, bomWritable, type BomAccess } from '../lib/boms';
import { assertMaster, masterRequest } from '../lib/catalog-master-api';
import {
  useServiceCommand,
  useServiceList,
  useServiceRead,
  type ServicePage,
} from '../lib/service-resource';
import { useProfileFields } from '../lib/product-profiles';
import { masterReturn } from '../lib/master-navigation';
import { ProfileFailure } from './ProductProfileCommon';
import { useAccessDraft } from './AccessCommon';
import { BomNavigation, useBomContext } from './BomCommon';
import { BomReference } from './BomReference';

export function BomApplicabilityList({
  company,
  bom,
}: {
  company: string;
  bom: string;
}) {
  const display = useDisplayConfig();
  const list = useServiceList<MasterRow>(
    `/v1/companies/${company}/bom-assignments`,
    new URLSearchParams({ bom_id: bom }).toString(),
    masterRequest,
    (row) => {
      if (!bomId(row.id))
        throw {
          status: 502,
          message: 'BOM applicability could not be verified.',
        };
    },
  );
  const columns: Column<MasterRow>[] = [
    {
      key: 'valid_from',
      header: 'Applies from',
      type: 'custom',
      render: (row) => (
        <a
          className="janso-link"
          href={`/masters/boms/${bom}/assignments/${row.id}`}
        >
          {row.valid_from
            ? formatDate(String(row.valid_from), display)
            : 'View assignment'}
        </a>
      ),
    },
    {
      key: 'valid_to',
      header: 'Applies through',
      type: 'custom',
      render: (row) =>
        row.valid_to === null
          ? 'No end date'
          : row.valid_to
            ? formatDate(String(row.valid_to), display)
            : 'Protected',
    },
    {
      key: 'scope',
      header: 'Scope',
      type: 'custom',
      render: (row) =>
        row.warehouse_id === null
          ? 'Company default'
          : row.warehouse_id
            ? 'Specific warehouse'
            : 'Protected',
    },
    {
      key: 'is_active',
      header: 'Status',
      type: 'custom',
      render: (row) =>
        row.is_active === true
          ? 'Active'
          : row.is_active === false
            ? 'Withdrawn'
            : 'Protected',
    },
  ];
  return (
    <section className="janso-flow" aria-label="Dated applicability">
      <SectionHeader
        title="Dated applicability"
        description="A matching warehouse assignment takes precedence over the company default."
      />
      <ProfileFailure failure={list.failure} retry={list.first} />
      <Card>
        <DataTable
          caption="BOM applicability"
          columns={columns}
          rows={list.data?.items ?? []}
          rowId={(row) => row.id}
          rowLabel={(row) => String(row.valid_from ?? 'Assignment')}
          loading={list.loading}
          emptyTitle="No dated assignments"
          emptyBody="Assign a published recipe to its primary output and production scope."
        />
        <Pager
          noun="assignment"
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

export function BomAssignment({
  company,
  bom,
  id,
  access,
  returnTo,
}: {
  company: string;
  bom: string;
  id?: string;
  access: BomAccess;
  returnTo?: string;
}) {
  const display = useDisplayConfig(),
    context = useBomContext(company),
    fields = useProfileFields(
      company,
      'catalog.bom_assignment',
      id ? 'update' : 'create',
    );
  const record = useServiceRead<MasterRow>(
    id ? `/v1/companies/${company}/bom-assignments/${id}` : undefined,
    masterRequest,
    (row) => assertMaster(row, company, id),
  );
  const [values, setValues] = useState<Record<string, unknown>>({
    bom_revision_id: null,
    warehouse_id: null,
    valid_from: businessToday(display.timezone),
    valid_to: null,
    change_reason: '',
  });
  const [dirty, setDirty] = useState(false),
    [saved, setSaved] = useState<MasterRow | null>(null),
    [errors, setErrors] = useState<Record<string, string>>({});
  const [withdrawing, setWithdrawing] = useState(false),
    [reload, setReload] = useState(false);
  const command = useServiceCommand(masterRequest, 'BOM applicability'),
    guard = useAccessDraft(dirty || command.uncertain, command.pending),
    form = useRef<HTMLFormElement>(null);
  const frozen = useRef<Record<string, unknown> | null>(null);
  useEffect(() => {
    if (record.data) {
      setValues({ ...record.data });
      setDirty(false);
    }
  }, [record.data]);
  const revisionId =
    typeof values.bom_revision_id === 'string' ? values.bom_revision_id : null;
  const revision = useServiceRead<MasterRow>(
    revisionId
      ? bomBase(company, `/${bom}/revisions/${revisionId}`)
      : undefined,
    masterRequest,
    (row) => {
      assertMaster(row, company, revisionId!);
      if (row.bom_id !== bom)
        throw {
          status: 502,
          message: 'This recipe does not belong to the selected BOM.',
        };
    },
  );
  const outputs = useServiceRead<ServicePage<MasterRow>>(
    revision.data
      ? bomBase(
          company,
          `/${bom}/revisions/${revisionId}/outputs?limit=100&sort=sequence,id`,
        )
      : undefined,
    masterRequest,
    (page) => {
      if (
        !Array.isArray(page.items) ||
        page.page.has_more ||
        page.page.next_cursor ||
        page.items.length !== revision.data?.output_count ||
        page.items.some((row) => row.revision_id !== revisionId)
      )
        throw {
          status: 502,
          message: 'The complete output set is required to assign this recipe.',
        };
    },
  );
  const primaries =
      outputs.data?.items.filter((row) => row.role === 'PRIMARY') ?? [],
    primary =
      primaries.length === 1 && bomId(primaries[0]?.item_id)
        ? String(primaries[0]!.item_id)
        : null;
  const canWithdraw =
    !!id &&
    access.assign &&
    record.data?.is_active === true &&
    Number.isSafeInteger(record.data.row_version) &&
    revision.data?.bom_id === bom &&
    !dirty;
  const editable =
    !withdrawing &&
    access.assign &&
    context.data?.enabled &&
    (!id || record.data?.is_active === true) &&
    bomWritable(fields.data?.fields ?? [], [
      'bom_revision_id',
      'item_id',
      'warehouse_id',
      'valid_from',
      'valid_to',
      'change_reason',
    ]);
  const change = (key: string, value: unknown) => {
    setValues((current) => ({ ...current, [key]: value }));
    setDirty(true);
    setErrors({});
  };
  const warehouses = useCallback<SearchSelectLoader>(
    async ({ q, cursor, signal }) => {
      const params = new URLSearchParams({ is_active: 'true', limit: '50' });
      if (q.trim().length >= 2) params.set('q', q.trim());
      if (cursor) params.set('cursor', cursor);
      const page = await masterRequest<ServicePage<MasterRow>>({
        path: `/v1/companies/${company}/warehouses?${params}`,
        signal,
      });
      if (!Array.isArray(page.items) || !page.page)
        throw {
          status: 502,
          message: 'Warehouse choices could not be verified.',
        };
      return {
        items: page.items
          .filter((row) => row.kind !== 'INTERNAL_TRANSIT')
          .map((row) => ({
            id: row.id,
            label: row.name ?? row.code ?? 'Protected warehouse',
            meta: row.code,
            disabled: row.is_active !== true || !row.kind,
          })),
        nextCursor: page.page.has_more ? page.page.next_cursor : null,
      };
    },
    [company],
  );
  const warehouse = useServiceRead<MasterRow>(
    values.warehouse_id && access.warehouses
      ? `/v1/companies/${company}/warehouses/${values.warehouse_id}`
      : undefined,
    masterRequest,
    (row) => assertMaster(row, company, String(values.warehouse_id)),
  );
  async function save() {
    if (
      command.pending ||
      !editable ||
      !primary ||
      !revisionId ||
      !form.current?.reportValidity()
    )
      return;
    let body = frozen.current;
    if (!command.uncertain) {
      if (
        values.valid_to &&
        String(values.valid_to) < String(values.valid_from)
      ) {
        setErrors({ valid_to: 'Choose an end date on or after the start.' });
        return;
      }
      body = {
        bom_revision_id: revisionId,
        item_id: primary,
        warehouse_id: values.warehouse_id || null,
        valid_from: values.valid_from,
        valid_to: values.valid_to || null,
        change_reason: values.change_reason,
        ...(id ? { expected_version: record.data?.row_version } : {}),
      };
      frozen.current = body;
    }
    const result = await command.execute<MasterRow>(
      {
        path: `/v1/companies/${company}/bom-assignments${id ? '/' + id : ''}`,
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
  async function withdraw() {
    if (!canWithdraw || command.pending) return;
    const result = await command.execute<MasterRow>(
      {
        path: `/v1/companies/${company}/bom-assignments/${id}/deactivate`,
        method: 'POST',
        body: { expected_version: record.data!.row_version },
      },
      (row) => {
        assertMaster(row, company, id);
        if (row.is_active !== false)
          throw { status: 502, message: 'Withdrawal could not be verified.' };
      },
    );
    if (result) {
      setSaved(result);
      setDirty(false);
      setWithdrawing(false);
    }
  }
  const back = masterReturn(returnTo, '/masters/boms/' + bom);
  const labelFor = (key: string, fallback: string) =>
    fields.data?.fields.find((field) => field.key === key)?.control?.label ??
    fallback;
  return (
    <div className="janso-page">
      <BomNavigation
        title={id ? 'BOM applicability' : 'Assign recipe'}
        back={back}
        onLeave={guard.leave}
      />
      <PageHeader
        title={id ? 'BOM applicability' : 'Assign recipe'}
        lede="Choose inclusive dates and an optional production warehouse. The SKU comes from the recipe’s primary output."
        actions={
          canWithdraw && !saved ? (
            <Button variant="ghost" onClick={() => setWithdrawing(true)}>
              Withdraw applicability
            </Button>
          ) : undefined
        }
      />
      <ProfileFailure
        failure={
          fields.failure ??
          context.failure ??
          record.failure ??
          revision.failure ??
          outputs.failure ??
          warehouse.failure ??
          command.failure
        }
        retry={() => {
          if (command.uncertain) {
            if (withdrawing) void withdraw();
            else void save();
          } else if (dirty) setReload(true);
          else {
            command.clear();
            fields.refresh();
            record.refresh();
            context.refresh();
            revision.refresh();
            outputs.refresh();
            warehouse.refresh();
          }
        }}
      />
      {saved ? (
        <Card>
          <CardBody>
            <Notice tone="success">
              {saved.is_active === false
                ? 'Recipe applicability withdrawn.'
                : 'Recipe applicability saved.'}
            </Notice>
            <a
              className="janso-btn janso-btn--primary"
              href={'/masters/boms/' + bom}
            >
              Back to BOM
            </a>
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
                <div className="janso-form-grid">
                  <BomReference
                    company={company}
                    bom={bom}
                    source="revisions"
                    value={revisionId}
                    onChange={(value) => change('bom_revision_id', value)}
                    label={labelFor('bom_revision_id', 'Published recipe')}
                    disabled={!editable || command.pending || command.uncertain}
                  />
                  <BomReference
                    company={company}
                    source="goods"
                    value={primary}
                    onChange={() => {}}
                    label={labelFor('item_id', 'Primary output SKU')}
                    disabled
                    canRead={access.goods}
                  />
                  {access.warehouses ? (
                    <SearchSelect
                      label={labelFor('warehouse_id', 'Production warehouse')}
                      name="warehouse_id"
                      scopeKey={company + ':bom-warehouse'}
                      value={
                        typeof values.warehouse_id === 'string'
                          ? values.warehouse_id
                          : null
                      }
                      selected={
                        warehouse.data
                          ? {
                              id: warehouse.data.id,
                              label:
                                warehouse.data.name ??
                                warehouse.data.code ??
                                'Warehouse',
                            }
                          : values.warehouse_id
                            ? {
                                id: String(values.warehouse_id),
                                label: 'Stored warehouse',
                                disabled: true,
                              }
                            : null
                      }
                      loadOptions={warehouses}
                      clearable
                      hint="Leave empty to use this recipe as the company default."
                      disabled={
                        !editable || command.pending || command.uncertain
                      }
                      onChange={(value) => change('warehouse_id', value)}
                    />
                  ) : (
                    <TextField
                      label="Production scope"
                      value={
                        values.warehouse_id
                          ? 'Existing warehouse scope'
                          : 'Company default'
                      }
                      disabled
                    />
                  )}
                  {(['valid_from', 'valid_to', 'change_reason'] as const).map(
                    (key) => (
                      <TextField
                        key={key}
                        label={labelFor(key, key.replaceAll('_', ' '))}
                        name={key}
                        type={key.startsWith('valid_') ? 'date' : 'text'}
                        value={String(values[key] ?? '')}
                        required={key !== 'valid_to'}
                        maxLength={key === 'change_reason' ? 500 : undefined}
                        error={errors[key] ?? command.failure?.fields?.[key]}
                        disabled={
                          !editable || command.pending || command.uncertain
                        }
                        onChange={(event) =>
                          change(key, event.target.value || null)
                        }
                      />
                    ),
                  )}
                </div>
                {revisionId && !primary && !outputs.loading && (
                  <Notice tone="warning">
                    The primary output cannot be verified. Review the recipe and
                    its output read permissions.
                  </Notice>
                )}
                {!editable && (
                  <Notice>
                    This applicability is read-only or BOM authoring is
                    disabled.
                  </Notice>
                )}
                {command.uncertain && (
                  <Notice tone="warning">
                    The save result is uncertain. Retry uses the same request
                    and key.
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
                Back to BOM
              </a>
              <Button
                type="submit"
                disabled={
                  !editable ||
                  !primary ||
                  command.pending ||
                  (command.blocked && !command.uncertain)
                }
              >
                {command.uncertain ? 'Retry save' : 'Save applicability'}
              </Button>
            </FormActions>
          </FormLayout>
        </form>
      )}
      <ConfirmDialog
        open={withdrawing}
        title="Withdraw recipe applicability?"
        confirmLabel={
          command.uncertain ? 'Retry withdrawal' : 'Withdraw applicability'
        }
        busy={command.pending}
        onCancel={() => {
          if (!command.pending && !command.uncertain) {
            setWithdrawing(false);
            command.clear();
          }
        }}
        onConfirm={() => void withdraw()}
      >
        This stops new selection for these dates and scope. The recipe and
        assignment history are retained.
        {command.failure && (
          <Notice tone="warning">
            {command.failure.message}
            {command.uncertain ? ' Retry uses the same request and key.' : ''}
          </Notice>
        )}
      </ConfirmDialog>
      <ConfirmDialog
        open={reload}
        title="Reload and review?"
        confirmLabel="Reload applicability"
        onCancel={() => setReload(false)}
        onConfirm={() => {
          setReload(false);
          command.clear();
          frozen.current = null;
          fields.refresh();
          record.refresh();
          context.refresh();
        }}
      >
        Unsaved changes will be discarded. Review the current applicability
        before another change.
      </ConfirmDialog>
      {guard.confirmation}
    </div>
  );
}
