'use client';
import { useEffect, useRef, useState } from 'react';
import { Button, Card, CardBody, ConfirmDialog, FormActions, FormLayout, Notice, PageHeader, SectionHeader, FieldGroup } from '@janso/ui';
import { type MasterConfig, type MasterRow } from '../lib/catalog-masters';
import type { EmbeddedMasterEditor } from '../lib/embedded-master-editor';
import { masterRequest } from '../lib/catalog-master-api';
import { nativeProductInitial } from '../lib/product-entry-policy';
import { classificationDefinitions, type ClassificationResource, type ClassificationAccess } from '../lib/product-classification-resources';
import { catalogBack, catalogBase, catalogLink, catalogReceipt, catalogVisible, catalogWritable, classificationBody, useCatalogFields } from '../lib/product-classification';
import { useServiceCommand, useServiceRead, type ServicePage } from '../lib/service-resource';
import type { ServiceRequest } from '../lib/service-call';
import { ProductCatalogCustomFields } from './ProductCatalogCustomFields';
import { AccessFocusErrors, useAccessDraft } from './AccessCommon';
import { ProductCatalogField, ProductCatalogFailure, ProductCatalogNavigation } from './ProductCatalogCommon';
export function ProductCatalogEditor({ company, config, id, returnTo, access, embedded, blockedByMode = false, }: {
  company: string;
  config: MasterConfig;
  id?: string;
  returnTo?: string;
  access: ClassificationAccess;
  embedded?: EmbeddedMasterEditor;
  blockedByMode?: boolean;
}) {
  const resource = config.resource as ClassificationResource, definition = classificationDefinitions[resource];
  const root = '/masters/' + resource, back = catalogBack(returnTo, root), detail = catalogLink(root + '/' + id, back);
  const metadata = useCatalogFields(company, config.entity, id ? 'update' : 'create', id), fields = metadata.data?.fields ?? [];
  const record = useServiceRead<MasterRow>(id ? catalogBase(company, resource + '/' + id) : undefined, masterRequest, (row) => catalogReceipt(row, company, id));
  const history = useServiceRead<ServicePage<MasterRow>>(id && resource === 'product-types'
    ? catalogBase(company, resource + '/' + id + '/revisions?limit=1&sort=-id')
    : undefined, masterRequest);
  const [values, setValues] = useState<Record<string, unknown>>({}), [dirty, setDirty] = useState(false), [initialized, setInitialized] = useState(false), [errors, setErrors] = useState<Record<string, string>>({}), [saved, setSaved] = useState<{
    row: MasterRow;
  } | null>(null), [frozen, setFrozen] = useState<ServiceRequest | null>(null), [reload, setReload] = useState(false), [unchanged, setUnchanged] = useState(false);
  const command = useServiceCommand(masterRequest, 'product catalog');
  const guard = useAccessDraft(dirty || command.uncertain, command.pending);
  const form = useRef<HTMLFormElement>(null);
  useEffect(() => { embedded?.onStateChange({ dirty, busy: command.pending || command.uncertain }); }, [embedded?.onStateChange, dirty, command.pending, command.uncertain]);
  useEffect(() => {
    if (metadata.loading ||
      record.loading ||
      history.loading ||
      (id && !record.data)) {
      setInitialized(false);
      return;
    }
    setValues(id
      ? { ...definition.initial, ...record.data }
      : nativeProductInitial(fields, { ...definition.initial, ...embedded?.initialValues }));
    setInitialized(true);
    setDirty(false);
    setErrors({});
    setSaved(null);
    setFrozen(null);
  }, [
    metadata.data,
    record.data,
    history.data,
    id,
    resource,
  ]);
  useEffect(() => {
    if (command.failure?.fields) {
      setErrors(command.failure.fields);
    }
  }, [command.failure]);
  const failure = metadata.failure ??
    record.failure ??
    history.failure, loading = metadata.loading ||
      record.loading ||
      history.loading ||
      (!initialized && !failure);
  const keys: readonly string[] = id ? definition.update : definition.create, typeFrozen = resource === 'product-types' && !!history.data?.items.length;
  const writableKeys = keys.filter((key) => !(typeFrozen && ['code', 'kind'].includes(key)) &&
    catalogWritable(fields, [key]));
  const fieldCanSave = (writableKeys.length > 0 ||
    (!!id &&
      fields.some((field) => field.source === 'custom' &&
        field.visible &&
        field.writable &&
        !field.conditional_access &&
        field.custom?.is_active &&
        !field.custom.is_immutable_after_create)))
    &&
    (!id || catalogVisible(fields, 'row_version'));
  const canSave = fieldCanSave && (!blockedByMode || command.uncertain);
  const recoverableCreate = !id && command.failure?.status === 409 && !command.uncertain;
  function beginChange() {
    if (blockedByMode) return false;
    if (command.blocked && !recoverableCreate)
      return false;
    if (recoverableCreate || command.failure?.status === 422)
      command.clear();
    return true;
  }
  function change(key: string, next: unknown) {
    if (!beginChange())
      return;
    setValues((current) => {
      const updated = { ...current, [key]: next };
      const paired = key === 'country_code'
        ? 'state_code'
        : key === 'brand_id'
          ? 'series_id'
          : key === 'scheme_id'
            ? 'parent_id'
            : key === 'kind'
              ? 'product_type_revision_id'
              : undefined;
      if (paired && current[key] !== next && catalogWritable(fields, [paired]))
        updated[paired] = null;
      return updated;
    });
    setDirty(true);
    setErrors({});
    setUnchanged(false);
  }
  async function save() {
    if (loading ||
      failure ||
      saved ||
      !canSave ||
      command.pending ||
      (command.blocked && !command.uncertain))
      return;
    let request = frozen;
    if (!command.uncertain || !request) {
      const result = classificationBody(config, fields, values, record.data ?? undefined);
      if (typeFrozen) {
        delete result.body.code;
        delete result.body.kind;
      }
      setErrors(result.errors);
      if (Object.keys(result.errors).length) {
        requestAnimationFrame(() => form.current
          ?.querySelector<HTMLElement>('[aria-invalid="true"]')
          ?.focus());
        return;
      }
      if (id && Object.keys(result.body).length === 1) {
        setUnchanged(true);
        setDirty(false);
        return;
      }
      request = {
        path: catalogBase(company, resource + (id ? '/' + id : '')),
        method: id ? 'PATCH' : 'POST',
        body: result.body,
      };
      setFrozen(request);
    }
    {
      const result = await command.execute<MasterRow>(request, (response) => catalogReceipt(response, company, id));
      if (result) {
        setSaved({ row: result });
        setDirty(false);
        setFrozen(null);
        embedded?.onSaved(result);
      }
    }
  }
  const disabled = blockedByMode || (command.blocked && !recoverableCreate) || !!saved;
  const productRecord = ['items', 'product-families'].includes(resource);
  const tradingKeys = ['sellable', 'purchasable', 'min_sale_quantity'];
  const renderFields = (include: readonly string[] = keys) => <div className="janso-form-grid">{fields.filter(field => include.includes(field.key)).map(field => {
    const pair = field.key === 'brand_id' ? 'series_id' : field.key === 'country_code' ? 'state_code' : undefined;
    const protectedPair = pair && values[pair] != null && !catalogWritable(fields, [pair]);
    return <ProductCatalogField key={field.key} company={company} field={typeFrozen && ['code', 'kind'].includes(field.key) ? { ...field, writable: false } : field} values={values} access={access} disabled={disabled || !!protectedPair} error={errors[field.key]} onChange={next => change(field.key, next)} />;
  })}</div>;
  return (<div className={'janso-page' + (['items', 'product-families'].includes(resource) ? ' janso-product-management' : '')}>
    {!embedded && <><ProductCatalogNavigation resource={resource} title={id
      ? `Edit ${definition.singular}`
      :
      `New ${definition.singular}`} back={id ? detail : back} access={access} onLeave={guard.leave} />
      <PageHeader title={id
        ? `Edit ${definition.singular}`
        :
        `New ${definition.singular}`} lede={(definition.description)} />
    </>}
    {blockedByMode && <Notice tone="warning">Product mode changed. Reload this page and review before saving. An interrupted save can still be recovered.</Notice>}
    {recoverableCreate ? (<Notice tone="warning">
      <p>{command.failure?.message}</p>
      <p>
        Your draft is retained. Correct the conflicting values and save
        again, or reload to review updated settings.
      </p>
      <Button variant="ghost" onClick={() => setReload(true)}>
        Reload settings
      </Button>

    </Notice>) : (<ProductCatalogFailure failure={failure ?? command.failure} write={!failure} retry={failure
      ? () => {
        metadata.refresh();
        record.refresh();
        history.refresh();
      }
      : command.uncertain
        ? () => void save()
        : command.failure?.status === 409
          ? () => setReload(true)
          : undefined} />)}
    {failure ? null : loading ? (<p role="status">Loading form...</p>) : saved ? (<Card>
      <CardBody>
        <div className="janso-flow">
          <Notice tone="success">
            {id
              ? 'Changes saved.'
              :
              `${definition.title} record created.`}
          </Notice>

          <div className="janso-form-actions">
            <a className="janso-btn janso-btn--primary" href={catalogLink(root + '/' + saved.row.id, back)} onClick={guard.leave}>
              View {definition.singular}
            </a>

            <a className="janso-link" href={back} onClick={guard.leave}>
              Return to directory
            </a>
            {!id && (<a className="janso-link" href={catalogLink(root + '/new', back)} onClick={guard.leave}>
              Create another
            </a>)}
          </div>
        </div>
      </CardBody>
    </Card>) : (<FormLayout aside={<div className="janso-flow">
      {(<SectionHeader title={'Before you save'} />)}

      {(<p className="janso-fine">
        Required fields are marked. Search references by name or code.
        Changes apply to the company currently open.
      </p>)}

      {typeFrozen && (<Notice>
        Revisions already exist. The type code and kind are fixed;
        create a new type for a different meaning.
      </Notice>)}
      {record.data?.is_active === false && (<Notice tone="warning">This record is inactive.</Notice>)}
      {!fieldCanSave && (<Notice tone="warning">
        Your field access does not allow this save.
      </Notice>)}

    </div>}>
      <form noValidate ref={form} aria-label={id ? `Edit ${definition.singular}` : `New ${definition.singular}`} onSubmit={(event) => {
        event.preventDefault();
        void save();
      }}>
        <Card>
          <CardBody>
            <div className="janso-flow">
              {(<section className="janso-flow" aria-label="Details">
                <SectionHeader title="Details" />
                {renderFields(productRecord ? keys.filter(key => !tradingKeys.includes(key)) : keys)}
                {productRecord && fields.some(field => keys.includes(field.key) && tradingKeys.includes(field.key) && field.visible) && <FieldGroup title="Trading">{renderFields(tradingKeys)}</FieldGroup>}
                <ProductCatalogCustomFields company={company} fields={fields} values={values} creating={!id} disabled={disabled} errors={errors} onChange={(next) => change('custom_fields', next)} />
              </section>)}

              {Object.keys(errors).length > 0 && (<Notice tone="danger">
                <p>Check the highlighted fields before saving.</p>
                <ul>
                  {[...new Set(Object.values(errors))].map((message) => (<li key={message}>{message}</li>))}
                </ul>
              </Notice>)}
              {unchanged && <Notice>No changes to save.</Notice>}
            </div>
          </CardBody>
          <FormActions cancel={embedded ? { onCancel: embedded.onCancel, disabled: command.pending || command.uncertain } : { href: id ? detail : back, onClick: guard.leave }}>

            <Button type="submit" loading={command.pending} disabled={!canSave ||
              (command.blocked && !command.uncertain) ||
              (!!id && !dirty && !command.uncertain)} loadingLabel="Saving...">
              {command.uncertain
                ? 'Retry same save'
                : id
                  ? 'Save changes'
                  :
                  `Create ${definition.singular}`}
            </Button>
          </FormActions>
        </Card>
      </form>
    </FormLayout>)}
    {guard.confirmation}
    <AccessFocusErrors fields={errors} />
    <ConfirmDialog open={reload && !command.uncertain} title="Discard draft and reload?" confirmLabel="Discard and reload" onCancel={() => setReload(false)} onConfirm={() => {
      command.clear();
      setReload(false);
      setDirty(false);
      setFrozen(null);
      metadata.refresh();
      record.refresh();
      history.refresh();
    }}>
      Reloading replaces unsaved values with the latest record.
    </ConfirmDialog>
  </div>);
}
