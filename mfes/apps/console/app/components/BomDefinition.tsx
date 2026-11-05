'use client';
import { useEffect, useRef, useState } from 'react';
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  ConfirmDialog,
  FormActions,
  FormLayout,
  Notice,
  PageHeader,
  ReviewList,
  SectionHeader,
  TextField,
  businessToday,
  formatDate,
  useDisplayConfig,
} from '@janso/ui';
import type { MasterRow } from '../lib/catalog-masters';
import { assertMaster, masterRequest } from '../lib/catalog-master-api';
import {
  bomBase,
  bomBody,
  bomComponentFields,
  bomId,
  bomOutputFields,
  bomScalars,
  bomWritable,
  verifyBom,
  verifyBomLines,
  type BomAccess,
  type BomDraft,
} from '../lib/boms';
import {
  useServiceCommand,
  useServiceRead,
  type ServicePage,
} from '../lib/service-resource';
import { useProfileFields } from '../lib/product-profiles';
import { masterReturn } from '../lib/master-navigation';
import { requestFailure, type RequestFailure } from '../lib/service-call';
import { ProfileFailure, ProfileField } from './ProductProfileCommon';
import { useAccessDraft } from './AccessCommon';
import { BomExplanation, BomNavigation, useBomContext } from './BomCommon';
import { BomLines } from './BomLines';
import { BomReference } from './BomReference';

const noProfiles = {
  'inventory-templates': false,
  'warranty-policies': false,
  'return-policies': false,
  'handling-profiles': false,
  publish: false,
  identifiers: false,
};
type Loaded = { row: MasterRow; document: BomDraft; complete: boolean };
function useBomDocument(
  company: string,
  bom: string,
  id: string | undefined,
  published: boolean,
  readable: boolean,
) {
  const [state, setState] = useState<{
    data: Loaded | null;
    loading: boolean;
    failure: RequestFailure | null;
  }>({ data: null, loading: !!id, failure: null });
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setState({ data: null, loading: !!id, failure: null });
    if (id)
      void (async () => {
        const path = bomBase(
          company,
          `/${bom}/${published ? 'revisions' : 'drafts'}/${id}`,
        );
        const row = await masterRequest<MasterRow>({
          path,
          signal: controller.signal,
        });
        assertMaster(row, company, id);
        if (row.bom_id !== bom)
          throw {
            status: 502,
            message: 'The BOM definition belongs to another parent.',
          };
        const document: BomDraft = { ...row, components: [], outputs: [] };
        if (readable) {
          verifyBom(row, company, bom, id);
          for (const kind of ['components', 'outputs'] as const) {
            const pages: ServicePage<MasterRow>[] = [],
              seen = new Set<string>();
            let cursor: string | null = null;
            for (
              let pageNumber = 0;
              pageNumber < (kind === 'components' ? 5 : 1);
              pageNumber++
            ) {
              const query = new URLSearchParams({
                limit: '200',
                sort: 'sequence,id',
              });
              if (cursor) query.set('cursor', cursor);
              const page = await masterRequest<ServicePage<MasterRow>>({
                path: path + '/' + kind + '?' + query,
                signal: controller.signal,
              });
              if (
                !Array.isArray(page.items) ||
                !page.page ||
                typeof page.page.has_more !== 'boolean'
              )
                throw {
                  status: 502,
                  message: 'BOM lines could not be verified.',
                };
              pages.push(page);
              if (!page.page.has_more) break;
              cursor = page.page.next_cursor;
              if (!cursor || seen.has(cursor))
                throw {
                  status: 502,
                  message: 'The complete BOM line set is unavailable.',
                };
              seen.add(cursor);
            }
            document[kind] = verifyBomLines(
              pages,
              id,
              published ? 'revision_id' : 'draft_id',
              Number(
                row[kind === 'components' ? 'component_count' : 'output_count'],
              ),
              kind === 'components' ? bomComponentFields : bomOutputFields,
            );
          }
          const current = await masterRequest<MasterRow>({
            path,
            signal: controller.signal,
          });
          if (current.row_version !== row.row_version)
            throw {
              status: 409,
              message:
                'The BOM changed while its lines loaded. Reload before reviewing.',
            };
        }
        if (!controller.signal.aborted)
          setState({
            data: { row, document, complete: readable },
            loading: false,
            failure: null,
          });
      })().catch((error) => {
        if (!controller.signal.aborted)
          setState({
            data: null,
            loading: false,
            failure: requestFailure(error, 'BOM definition'),
          });
      });
    return () => controller.abort();
  }, [company, bom, id, published, readable, revision]);
  return { ...state, refresh: () => setRevision((value) => value + 1) };
}

export function BomDefinition({
  company,
  bom,
  id,
  published,
  access,
  returnTo,
}: {
  company: string;
  bom: string;
  id?: string;
  published: boolean;
  access: BomAccess;
  returnTo?: string;
}) {
  const display = useDisplayConfig(),
    context = useBomContext(company),
    entity = published ? 'catalog.bom_revision' : 'catalog.bom_draft';
  const parent = useServiceRead<MasterRow>(
    bomBase(company, '/' + bom),
    masterRequest,
    (row) => assertMaster(row, company, bom),
  );
  const metadata = useProfileFields(
    company,
    entity,
    published ? undefined : id ? 'update' : 'create',
  );
  const components = useProfileFields(
    company,
    'catalog.bom_component',
    published ? undefined : id ? 'update' : 'create',
  );
  const outputs = useProfileFields(
    company,
    'catalog.bom_output',
    published ? undefined : id ? 'update' : 'create',
  );
  const publishing = useProfileFields(
    company,
    'catalog.bom_draft',
    'publish',
    !!id && !published && access.publish,
  );
  const publishedFields = useProfileFields(
    company,
    'catalog.bom_revision',
    'publish',
    !!id && !published && access.publish,
  );
  const publishedComponents = useProfileFields(
    company,
    'catalog.bom_component',
    'publish',
    !!id && !published && access.publish,
  );
  const publishedOutputs = useProfileFields(
    company,
    'catalog.bom_output',
    'publish',
    !!id && !published && access.publish,
  );
  const fields = metadata.data?.fields ?? [],
    componentFields = components.data?.fields ?? [],
    outputFields = outputs.data?.fields ?? [];
  const has = (source: typeof fields, keys: readonly string[]) =>
    keys.every((key) =>
      source.some((field) => field.key === key && !field.conditional_access),
    );
  const readable =
    has(fields, [
      'bom_id',
      'status',
      'row_version',
      'component_count',
      'output_count',
      ...bomScalars,
    ]) &&
    has(componentFields, [
      published ? 'revision_id' : 'draft_id',
      ...bomComponentFields,
    ]) &&
    has(outputFields, [
      published ? 'revision_id' : 'draft_id',
      ...bomOutputFields,
    ]);
  const record = useBomDocument(company, bom, id, published, readable);
  const [values, setValues] = useState<BomDraft>({
    specification: '',
    change_reason: '',
    definition_date: businessToday(display.timezone),
    route_revision_id: null,
    batch_minimum: null,
    batch_maximum: null,
    batch_multiple: null,
    components: [],
    outputs: [],
  });
  const [dirty, setDirty] = useState(false),
    [errors, setErrors] = useState<Record<string, string>>({}),
    [saved, setSaved] = useState<MasterRow | null>(null),
    [action, setAction] = useState<'publish' | 'retire' | null>(null),
    [reload, setReload] = useState(false);
  const command = useServiceCommand(masterRequest, 'BOM definition'),
    guard = useAccessDraft(dirty || command.uncertain, command.pending),
    form = useRef<HTMLFormElement>(null),
    frozen = useRef<{
      path: string;
      method: 'POST' | 'PATCH';
      body: Record<string, unknown>;
    } | null>(null);
  useEffect(() => {
    if (record.data) {
      setValues(record.data.document);
      setDirty(false);
      setErrors({});
    }
  }, [record.data]);
  useEffect(() => {
    if (command.failure?.fields) setErrors(command.failure.fields);
  }, [command.failure]);
  useEffect(() => {
    if (Object.keys(errors).length)
      form.current
        ?.querySelector<HTMLElement>('[aria-invalid="true"]')
        ?.focus();
  }, [errors]);
  const path = bomBase(
      company,
      `/${bom}/${published ? 'revisions' : 'drafts'}${id ? '/' + id : ''}`,
    ),
    here = `/masters/boms/${bom}/${published ? 'revisions' : 'drafts'}/${id ?? 'new'}`,
    back = masterReturn(returnTo, '/masters/boms/' + bom);
  const complete = !id ? readable : record.data?.complete === true;
  const writable =
    access.manage &&
    !published &&
    (!id || record.data?.row.status === 'DRAFT') &&
    complete &&
    context.data?.enabled &&
    parent.data?.is_active === true &&
    bomWritable(fields, [...bomScalars, ...(!id ? ['bom_id'] : [])]) &&
    bomWritable(componentFields, [
      'draft_id',
      'revision_id',
      ...bomComponentFields,
    ]) &&
    bomWritable(outputFields, ['draft_id', 'revision_id', ...bomOutputFields]);
  const canPublish =
    !!id &&
    !published &&
    record.data?.row.status === 'DRAFT' &&
    !dirty &&
    complete &&
    access.publish &&
    context.data?.enabled &&
    parent.data?.is_active === true &&
    bomWritable(publishing.data?.fields ?? [], [
      'status',
      'published_revision_id',
    ]) &&
    bomWritable(publishedFields.data?.fields ?? [], [
      'bom_id',
      'draft_id',
      'content_sha256',
      'dependency_manifest',
    ]) &&
    bomWritable(publishedComponents.data?.fields ?? [], [
      'draft_id',
      'revision_id',
      ...bomComponentFields,
    ]) &&
    bomWritable(publishedOutputs.data?.fields ?? [], [
      'draft_id',
      'revision_id',
      ...bomOutputFields,
    ]) &&
    values.outputs.filter((row) => row.role === 'PRIMARY').length === 1;
  const change = (key: string, value: unknown) => {
    setValues((current) => ({ ...current, [key]: value }));
    setDirty(true);
    setErrors({});
    setSaved(null);
  };
  function refresh() {
    command.clear();
    frozen.current = null;
    record.refresh();
    context.refresh();
    metadata.refresh();
    components.refresh();
    outputs.refresh();
    parent.refresh();
  }
  async function save() {
    if (command.pending || !writable || !form.current?.reportValidity()) return;
    if (!command.uncertain) {
      const validated = bomBody(values);
      setErrors(validated.errors);
      if (Object.keys(validated.errors).length) return;
      frozen.current = {
        path,
        method: id ? 'PATCH' : 'POST',
        body: {
          ...validated.body,
          ...(id ? { expected_version: record.data?.row.row_version } : {}),
        },
      };
    }
    if (!frozen.current) return;
    const result = await command.execute<MasterRow>(frozen.current, (row) =>
      verifyBom(row, company, bom, id),
    );
    if (result) {
      setSaved(result);
      setDirty(false);
      frozen.current = null;
      if (id) record.refresh();
    }
  }
  async function lifecycle() {
    if (!action || !record.data || command.pending) return;
    if (!command.uncertain)
      frozen.current = {
        path: path + '/' + action,
        method: 'POST',
        body: { expected_version: record.data.row.row_version },
      };
    if (!frozen.current) return;
    const result = await command.execute<MasterRow>(frozen.current, (row) =>
      verifyBom(row, company, bom, id),
    );
    if (result) {
      setAction(null);
      setSaved(result);
      frozen.current = null;
      record.refresh();
    }
  }
  const locked =
    !writable || command.pending || command.uncertain || (!!saved && !id);
  const failure =
    parent.failure ??
    context.failure ??
    metadata.failure ??
    components.failure ??
    outputs.failure ??
    record.failure ??
    publishing.failure ??
    publishedFields.failure ??
    publishedComponents.failure ??
    publishedOutputs.failure ??
    command.failure;
  return (
    <div className="janso-page">
      <BomNavigation
        title={
          !id
            ? 'New recipe draft'
            : published
              ? 'Published recipe'
              : 'Recipe draft'
        }
        back={back}
        onLeave={guard.leave}
      />
      <PageHeader
        title={
          !id
            ? 'New recipe draft'
            : published
              ? `Recipe revision ${record.data?.row.revision ?? ''}`
              : `Recipe draft ${record.data?.row.draft_number ?? ''}`
        }
        lede={parent.data?.name ?? 'Single-level BOM definition'}
        actions={
          published &&
          access.publish &&
          record.data?.row.status === 'PUBLISHED' ? (
            <Button variant="ghost" onClick={() => setAction('retire')}>
              Retire recipe
            </Button>
          ) : canPublish ? (
            <Button onClick={() => setAction('publish')}>
              Review and publish
            </Button>
          ) : undefined
        }
      />
      <BomExplanation />
      <ProfileFailure
        failure={failure}
        retry={() => (command.uncertain || dirty ? setReload(true) : refresh())}
      />
      {record.loading ||
      metadata.loading ||
      components.loading ||
      outputs.loading ? (
        <Notice>Loading the complete recipe…</Notice>
      ) : null}
      {id && !!record.data?.row.status && (
        <Notice>
          {record.data.row.status === 'DRAFT'
            ? 'Draft recipe — save changes before publication.'
            : record.data.row.status === 'RETIRED'
              ? 'Retired recipe — retained for historical review.'
              : 'Published recipe — this definition is immutable.'}
        </Notice>
      )}
      {!complete && !record.loading && (
        <Notice tone="warning">
          The complete recipe and its native fields cannot be reviewed. Editing
          and publication are unavailable; existing values are retained.
        </Notice>
      )}
      {saved && (
        <Notice tone="success">
          {saved.published_revision_id
            ? 'Recipe published. '
            : saved.status === 'RETIRED'
              ? 'Recipe retired. '
              : 'Recipe saved. '}
          {!id && (
            <a
              className="janso-link"
              href={`/masters/boms/${bom}/drafts/${saved.id}`}
            >
              Open saved draft to preview and publish
            </a>
          )}
          {!!saved.published_revision_id && (
            <a
              className="janso-link"
              href={`/masters/boms/${bom}/revisions/${saved.published_revision_id}`}
            >
              Open published recipe
            </a>
          )}
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
              <CardHeader title="Recipe details" />
              <CardBody>
                <div className="janso-form-grid">
                  {fields
                    .filter(
                      (field) =>
                        bomScalars.includes(
                          field.key as (typeof bomScalars)[number],
                        ) &&
                        field.visible &&
                        !field.conditional_access &&
                        field.control,
                    )
                    .map((field) =>
                      field.key === 'route_revision_id' ? (
                        <BomReference
                          key={field.key}
                          company={company}
                          source="routes"
                          value={
                            typeof values.route_revision_id === 'string'
                              ? values.route_revision_id
                              : null
                          }
                          onChange={(value) => {
                            change('route_revision_id', value);
                            setValues((current) => ({
                              ...current,
                              components: current.components.map((line) => ({
                                ...line,
                                route_step_id: null,
                              })),
                            }));
                          }}
                          disabled={locked}
                          label={field.control?.label ?? 'Manufacturing route'}
                          canRead={access.routes}
                          error={errors[field.key]}
                        />
                      ) : (
                        <ProfileField
                          key={field.key}
                          company={company}
                          field={field}
                          value={values[field.key]}
                          disabled={locked}
                          error={errors[field.key]}
                          onChange={(value) => change(field.key, value)}
                          access={noProfiles}
                        />
                      ),
                    )}
                </div>
              </CardBody>
            </Card>
            {complete && (
              <>
                <BomLines
                  company={company}
                  kind="components"
                  rows={values.components}
                  onChange={(value) => change('components', value)}
                  fields={componentFields}
                  disabled={locked}
                  errors={errors}
                  date={String(values.definition_date ?? '')}
                  route={
                    typeof values.route_revision_id === 'string'
                      ? values.route_revision_id
                      : null
                  }
                  access={access}
                />
                <BomLines
                  company={company}
                  kind="outputs"
                  rows={values.outputs}
                  onChange={(value) => change('outputs', value)}
                  fields={outputFields}
                  disabled={locked}
                  errors={errors}
                  date={String(values.definition_date ?? '')}
                  route={
                    typeof values.route_revision_id === 'string'
                      ? values.route_revision_id
                      : null
                  }
                  access={access}
                />
              </>
            )}
            <FormActions>
              <a
                className="janso-btn janso-btn--ghost"
                href={back}
                onClick={guard.leave}
              >
                Back to BOM
              </a>
              {!published && (
                <Button
                  type="submit"
                  disabled={
                    !writable ||
                    command.pending ||
                    (command.blocked && !command.uncertain) ||
                    (!!saved && !id)
                  }
                >
                  {command.uncertain ? 'Retry save' : 'Save draft'}
                </Button>
              )}
            </FormActions>
          </div>
        </FormLayout>
      </form>
      {!!id &&
        complete &&
        !dirty &&
        context.data?.enabled &&
        record.data?.row.status !== 'RETIRED' && (
          <BomPreview company={company} path={path} />
        )}
      {published &&
        record.data?.row.status === 'PUBLISHED' &&
        access.assign &&
        context.data?.enabled && (
          <a
            className="janso-link"
            href={`/masters/boms/${bom}/assignments/new`}
          >
            Assign this recipe
          </a>
        )}
      <ConfirmDialog
        open={!!action}
        title={
          action === 'publish' ? 'Publish this recipe?' : 'Retire this recipe?'
        }
        confirmLabel={
          command.uncertain
            ? 'Retry ' + action
            : action === 'publish'
              ? 'Publish recipe'
              : 'Retire recipe'
        }
        busy={command.pending}
        onCancel={() => {
          if (!command.pending && !command.uncertain) {
            setAction(null);
            command.clear();
          }
        }}
        onConfirm={() => void lifecycle()}
      >
        <ReviewList
          items={[
            { label: 'Components', value: String(values.components.length) },
            { label: 'Outputs', value: String(values.outputs.length) },
            {
              label: 'Definition date',
              value: formatDate(String(values.definition_date ?? ''), display),
            },
            {
              label: 'Effect',
              value:
                action === 'publish'
                  ? 'Preserve this recipe as an immutable revision.'
                  : 'Prevent new applicability and retain history.',
            },
          ]}
        />
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
        confirmLabel="Reload recipe"
        onCancel={() => setReload(false)}
        onConfirm={() => {
          setReload(false);
          refresh();
        }}
      >
        Unsaved changes will be discarded. If the last result was uncertain, its
        operation may already have completed; reloading checks the current
        record before another action.
      </ConfirmDialog>
      {guard.confirmation}
    </div>
  );
}

function BomPreview({ company, path }: { company: string; path: string }) {
  const [quantity, setQuantity] = useState(''),
    [count, setCount] = useState(''),
    [runs, setRuns] = useState('');
  const [countError, setCountError] = useState<string>();
  const [result, setResult] = useState<{
    nominal_run_quantity: string;
    operational_ready: false;
    requirements: {
      line_key: string;
      item_id: string;
      required_quantity: string;
      base_quantity: string;
    }[];
    outputs: {
      line_key: string;
      item_id: string;
      expected_quantity: string;
      base_quantity: string;
      role: string;
    }[];
  } | null>(null);
  const command = useServiceCommand(masterRequest, 'BOM quantity preview');
  async function calculate() {
    if (count && (!/^[1-9]\d{0,3}$/.test(count) || Number(count) > 1000)) {
      setCountError('Enter a whole run count from 1 to 1000.');
      return;
    }
    setCountError(undefined);
    const value = await command.execute<typeof result & {}>(
      {
        path: path + '/preview',
        method: 'POST',
        body: {
          requested_good_quantity: quantity,
          ...(count ? { run_count: Number(count) } : {}),
          ...(runs.trim()
            ? { run_quantities: runs.split(',').map((value) => value.trim()) }
            : {}),
        },
      },
      (data) => {
        if (
          data.operational_ready !== false ||
          !Array.isArray(data.requirements) ||
          !Array.isArray(data.outputs) ||
          typeof data.nominal_run_quantity !== 'string'
        )
          throw {
            status: 502,
            message: 'The quantity preview could not be verified.',
          };
      },
    );
    if (value) setResult(value);
  }
  return (
    <section className="janso-flow" aria-label="Quantity preview">
      <SectionHeader
        title="Quantity preview"
        description="Exact non-posting requirements. No availability, reservation, production or costing is performed."
      />
      <Card>
        <CardBody>
          <div className="janso-form-grid">
            <TextField
              label="Requested good output"
              name="requested_good_quantity"
              inputMode="decimal"
              value={quantity}
              onChange={(event) => {
                setQuantity(event.target.value);
                setResult(null);
                command.clear();
              }}
            />
            <TextField
              label="Run count"
              name="run_count"
              inputMode="numeric"
              value={count}
              error={countError}
              onChange={(event) => {
                setCount(event.target.value);
                setCountError(undefined);
                setResult(null);
                command.clear();
              }}
              hint="Required for fixed-per-run components or a run breakdown."
            />
            <TextField
              label="Nominal run quantities"
              name="run_quantities"
              value={runs}
              onChange={(event) => {
                setRuns(event.target.value);
                setResult(null);
                command.clear();
              }}
              hint="Comma-separated exact quantities. Required when the recipe has batch constraints."
            />
          </div>
          <ProfileFailure
            failure={command.failure}
            retry={() => {
              command.clear();
              void calculate();
            }}
          />
          <FormActions>
            <Button
              type="button"
              variant="ghost"
              disabled={!quantity || command.pending}
              onClick={() => void calculate()}
            >
              Calculate quantities
            </Button>
          </FormActions>
          {result && (
            <div className="janso-flow">
              <Notice>
                Nominal run output: {result.nominal_run_quantity}. This is a
                definition preview.
              </Notice>
              {[
                ...result.requirements.map((row) => ({
                  ...row,
                  value: row.required_quantity,
                  label: 'Required component',
                })),
                ...result.outputs.map((row) => ({
                  ...row,
                  value: row.expected_quantity,
                  label: row.role.replaceAll('_', ' '),
                })),
              ].map((row) => (
                <Card nested key={row.line_key}>
                  <CardBody>
                    <BomReference
                      company={company}
                      source="goods"
                      value={row.item_id}
                      onChange={() => {}}
                      disabled
                      label={row.label}
                    />
                    <ReviewList
                      items={[
                        { label: 'Quantity in pinned unit', value: row.value },
                        {
                          label: 'Quantity in base unit',
                          value: row.base_quantity,
                        },
                      ]}
                    />
                  </CardBody>
                </Card>
              ))}
            </div>
          )}
        </CardBody>
      </Card>
    </section>
  );
}
