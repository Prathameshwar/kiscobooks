'use client';
import { SubjectHistory } from './SubjectHistory';
import { catalogRelatedLinks } from '../lib/master-navigation';
import { useState } from 'react';
import { Button, Card, CardBody, ConfirmDialog, Menu, Notice, PageHeader, ReviewList, SectionHeader, Select, Checkbox } from '@janso/ui';
import type { components } from '@janso/api-client/catalog';
import type { MasterConfig, MasterField, MasterRow } from '../lib/catalog-masters';
import { masterRequest } from '../lib/catalog-master-api';
import { catalogBack, catalogBase, catalogLink, catalogReceipt, catalogVisible, catalogWritable, useCatalogFields } from '../lib/product-classification';
import { classificationDefinitions, type ClassificationResource, type ClassificationAccess } from '../lib/product-classification-resources';
import { useServiceCommand, useServiceRead } from '../lib/service-resource';
import type { ServiceRequest } from '../lib/service-call';
import { useAccessDraft } from './AccessCommon';
import { ProductCatalogField, ProductCatalogFailure, ProductCatalogNavigation, ProductCatalogReference } from './ProductCatalogCommon';
import { ProductTypeHistory } from './ProductTypeRevision';
import { ProductCatalogCustomFields } from './ProductCatalogCustomFields';
import { ProductInventoryActions } from './ProductInventoryActions';
import { ProductDetailHeader, ProductDetailView } from './ProductDetailView';
type SchemePreview = components['schemas']['SchemeTransitionPreview'];
export function ProductCatalogDetail({ company, config, id, returnTo, canManage, access, completed = false }: {
  company: string;
  config: MasterConfig;
  id: string;
  returnTo?: string;
  canManage: boolean;
  access: ClassificationAccess;
  completed?: boolean;
}) {
  const resource = config.resource as ClassificationResource, definition = classificationDefinitions[resource], root = '/masters/' + resource, back = catalogBack(returnTo, root);
  const metadata = useCatalogFields(company, config.entity), fields = metadata.data?.fields ?? [], record = useServiceRead<MasterRow>(catalogBase(company, resource + '/' + id), masterRequest, (row) => catalogReceipt(row, company, id));
  const [updated, setUpdated] = useState<MasterRow | null>(null), [action, setAction] = useState<string | null>(null), [dialogOpen, setDialogOpen] = useState(false), [parent, setParent] = useState<string | null>(null), [scheme, setScheme] = useState<Record<string, unknown>>({}), [preview, setPreview] = useState<SchemePreview | null>(null), [frozen, setFrozen] = useState<ServiceRequest | null>(null), [message, setMessage] = useState(''), [reload, setReload] = useState(false);
  const here = catalogLink(root + '/' + id, back);
  const command = useServiceCommand(masterRequest, 'product catalog actions'), guard = useAccessDraft(!!action || command.uncertain, command.pending), row = updated ?? record.data, versioned = !!row && catalogVisible(fields, 'row_version');
  const moveKey = resource === 'brands' ? 'parent_brand_id' : 'parent_id';
  const canMove = access.move &&
    catalogVisible(fields, moveKey) &&
    Number.isSafeInteger(row?.policy_generation);
  const canLifecycle = versioned &&
    (canManage && catalogWritable(fields, ['is_active']));
  const canTransition = canManage &&
    versioned &&
    resource === 'category-schemes' &&
    catalogWritable(fields, ['membership_mode', 'is_required', 'is_active']);
  const canEdit = canManage;
  function refresh() {
    setUpdated(null);
    setMessage('');
    record.refresh();
    metadata.refresh();
  }
  function open(next: string) {
    if (command.blocked)
      return;
    setAction(next);
    setDialogOpen(true);
    setPreview(null);
    setFrozen(null);
    setParent(typeof row?.[moveKey] === 'string' ? (row[moveKey] as string) : null);
    setScheme({
      membership_mode: row?.membership_mode,
      is_required: row?.is_required,
      is_active: row?.is_active,
    });
  }
  async function prepare() {
    if (!row || (command.blocked && !command.uncertain) || !action)
      return;
    const request = frozen ?? {
      path: catalogBase(company, resource + '/' + id + '/transition-preview'),
      method: 'POST', body: { expected_version: row.row_version, ...scheme },
    };
    setFrozen(request);
    const result = await command.execute<SchemePreview>(request, (result) => {
      if (result.scheme_id !== id || result.expected_version !== row.row_version)
        throw {
          status: 502,
          message: 'The review response did not match this record.',
        };
      if (!result.preview_token || typeof result.eligible !== 'boolean')
        throw {
          status: 502,
          message: 'The service review could not be verified.',
        };
    });
    if (result) {
      setPreview(result);
      setFrozen(null);
      setDialogOpen(true);
    }
  }
  async function run() {
    if (!row || !action || (command.blocked && !command.uncertain))
      return;
    if (frozen?.path.endsWith('-preview')) {
      await prepare();
      return;
    }
    let request = frozen;
    if (!command.uncertain || !request) {
      let body: Record<string, unknown> = { expected_version: row.row_version };
      if (action === 'reparent') {
        if (!canMove || parent === id)
          return;
        body = {
          ...body,
          expected_generation: row.policy_generation,
          [moveKey]: parent,
        };
      }
      if (action === 'transition') {
        if (!canTransition ||
          !preview ||
          !('scheme_id' in preview) ||
          !preview.eligible)
          return;
        body = { ...body, ...scheme, preview_token: preview.preview_token };
      }
      request = {
        path: catalogBase(company, resource + '/' + id + '/' + action),
        method: 'POST',
        body,
      };
      setFrozen(request);
    }
    {
      const result = await command.execute<MasterRow>(request, (receipt) => catalogReceipt(receipt, company, id));
      if (result) {
        setUpdated(result);
        setAction(null);
        setDialogOpen(false);
        setFrozen(null);
        setPreview(null);
        setMessage(action === 'transition'
          ? 'Category scheme rules updated after review.'
          : action === 'reparent'
            ? 'Parent updated.'
            : action === 'activate'
              ? 'Record activated.'
              : 'Record deactivated. Existing references are retained.');
      }
    }
  }
  const failure = metadata.failure ?? record.failure, blockedReason = command.blocked || action
    ? 'Finish the current action first.'
    :
    undefined;
  const title = completed ? (resource === 'product-families' ? 'Product Profile saved' : 'Product saved') : row?.name ?? definition.singular + ' details';
  const related: {
    resource: string;
    key: string;
    label: string;
    allowed: boolean;
  }[] = resource === 'item-categories'
      ? [
        {
          resource: 'category-schemes',
          key: 'scheme_id',
          label: 'Open category scheme',
          allowed: access['category-schemes'],
        },
      ]
      : resource === 'brand-series'
        ? [
          {
            resource: 'brands',
            key: 'brand_id',
            label: 'Open brand',
            allowed: access.brands,
          },
        ]
        : resource === 'manufacturer-sites'
          ? [
            {
              resource: 'manufacturers',
              key: 'manufacturer_id',
              label: 'Open manufacturer',
              allowed: access.manufacturers,
            },
          ]
          : [];
  const relatedActions = row
    ? catalogRelatedLinks(resource, row, (key) => catalogVisible(fields, key), access, here)
    : [];
  function factValue(field: MasterField) {
    const value = row?.[field.key];
    return value == null ? 'Not set' : String(value).replaceAll('_', ' ').toLowerCase();
  }
  const productRecord = resource === 'items' || resource === 'product-families';
  const Header = productRecord ? ProductDetailHeader : PageHeader;
  return (<div className={'janso-page' + (productRecord ? ' janso-product-management' : '')}>
    <ProductCatalogNavigation resource={resource} title={title} back={back} access={access} onLeave={guard.leave} />
    <Header title={title} fields={fields} row={row} family={resource === 'product-families'} completed={completed} lede={definition.description} actions={row &&
      !failure &&
      !metadata.loading &&
      !record.loading &&
      (productRecord || canEdit ||
        canLifecycle ||
        canTransition ||
        canMove ||
        relatedActions.length > 0) && (<>

          {productRecord && canEdit && <a className="janso-btn janso-btn--ghost" href={catalogLink(root + '/' + id + '/edit', here)} onClick={guard.leave}>Edit details</a>}
          {productRecord && <ProductInventoryActions triggerLabel={resource === 'product-families' ? 'Manage profile' : 'Manage product'} company={company} row={row} family={resource === 'product-families'} access={access} returnTo={here} items={access.attributes ? [{ id: 'attributes', label: 'Manage attributes', href: '/products/attributes?' + new URLSearchParams(resource === 'items' ? { item_id: id } : { family_id: id }) }] : []} />}
          {(canEdit ||
            canLifecycle ||
            canTransition ||
            canMove ||
            relatedActions.length > 0) && (<Menu label="Record actions" onNavigate={guard.leave} items={[
              ...(canEdit
                ? [
                  {
                    id: 'edit',
                    label: 'Edit details',
                    href: catalogLink(root + '/' + id + '/edit', here),
                    disabledReason: blockedReason,
                  },
                ]
                : []),
              ...(canLifecycle && resource !== 'category-schemes'
                ? [
                  {
                    id: !row.is_active
                      ? 'activate'
                      : 'deactivate',
                    label: row.is_active
                      ? 'Deactivate'
                      : 'Activate',
                    destructive: row.is_active === true,
                    disabledReason: blockedReason,
                  },
                ]
                : []),
              ...(canTransition
                ? [
                  {
                    id: 'transition',
                    label: 'Review scheme rules',
                    disabledReason: blockedReason,
                  },
                ]
                : []),
              ...(canMove
                ? [
                  {
                    id: 'reparent',
                    label: 'Change parent',
                    disabledReason: blockedReason,
                  },
                ]
                : []),
              ...relatedActions.filter(link => true).map((link) => ({
                ...link,
                disabledReason: blockedReason,
              })),
            ]} onSelect={(next) => {
              if (next !== 'edit')
                open(next);
            }} />)}
        </>)} />
    <ProductCatalogFailure failure={failure} retry={refresh} />
    <ProductCatalogFailure failure={command.failure} write={command.uncertain} />
    {command.failure && !command.uncertain && (<Button variant="ghost" onClick={() => setReload(true)}>
      Reload and review
    </Button>)}
    {command.uncertain && frozen && (<Button disabled={command.pending} onClick={() => void run()}>
      Retry same action
    </Button>)}
    {message && <Notice tone="success">{message}</Notice>}
    {completed && row && !failure && !record.loading && <Notice tone="info">The product is saved. Review its current status and setup below. Creation does not by itself confirm stock or tax posting.</Notice>}
    {metadata.loading || record.loading ? (<p role="status">Loading record...</p>) : row && !failure ? (<div className="janso-flow">
      {row.is_active === false && (<Notice tone="warning">
        This record is inactive. Existing references remain available.
      </Notice>)}

      {productRecord ? <ProductDetailView company={company} fields={fields} row={row} access={access} returnTo={here} family={resource === 'product-families'} onLeave={guard.leave} /> : <div role="region" aria-label="Record details" tabIndex={-1}>
        <Card>
          <CardBody>
            <div className="janso-flow">
              <SectionHeader title="Details" />

              <ReviewList items={fields
                .filter((field) => catalogVisible(fields, field.key) &&
                  field.key in row &&
                  (!field.control)
                  &&
                  !['custom_fields', 'id', 'company_id'].includes(field.key) &&
                  !field.key.endsWith('_id'))
                .map((field) => ({
                  label: field.key.replaceAll('_', ' '),
                  value: factValue(field),
                }))} />
              <div className="janso-form-grid">
                {fields
                  .filter((field) => field.control &&
                    field.key in row)
                  .map((field) => (<ProductCatalogField returnTo={here} onLeave={guard.leave} key={field.key} company={company} field={field} values={row} readView access={access} disabled onChange={() => undefined} />))}
              </div>
              <ProductCatalogCustomFields company={company} fields={fields} values={row} disabled onChange={() => undefined} />
              <nav className="janso-page-navigation" aria-label="Related records">
                {related
                  .filter((link) => link.allowed &&
                    typeof row[link.key] === 'string' &&
                    catalogVisible(fields, link.key))
                  .map((link) => (<a key={link.key} className="janso-link" href={catalogLink('/masters/' + link.resource + '/' + row[link.key], here)} onClick={guard.leave}>
                    {link.label}
                  </a>))}
                {resource === 'brands' && access['brand-series'] && (<a className="janso-link" href={catalogLink('/masters/brand-series?brand_id=' + id, here)} onClick={guard.leave}>
                  Brand series
                </a>)}
                {resource === 'category-schemes' &&
                  access['item-categories'] && (<a className="janso-link" href={catalogLink('/masters/item-categories?scheme_id=' + id, here)} onClick={guard.leave}>
                    Categories in this scheme
                  </a>)}

              </nav>
            </div>
          </CardBody>
        </Card>
      </div>}
      {resource === 'product-types' && (<ProductTypeHistory company={company} parentId={id} active={row.is_active === true} here={here} canManage={canManage} blocked={!!action || command.blocked} onLeave={guard.leave} />)}

    </div>) : null}
    {row && !failure && <SubjectHistory company={company} entity={config.entity} id={id} />}
    <ConfirmDialog open={dialogOpen && !!action} title={action === 'transition'
      ? 'Review category scheme rules'
      : action === 'reparent'
        ? 'Change parent?'
        :
        `${action === 'activate' ? 'Activate' : 'Deactivate'} record?`} confirmLabel={command.uncertain
          ? frozen?.path.endsWith('-preview')
            ? 'Retry same review'
            : 'Retry same action'
          : preview && !preview.eligible
            ? 'Review again'
            : ['transition', 'activate'].includes(action ?? '') &&
              (action === 'transition') &&
              !preview
              ? 'Prepare review'
              : action === 'reparent'
                ? 'Save parent change'
                : 'Confirm change'} busy={command.pending} error={command.failure?.message} onCancel={() => {
                  setDialogOpen(false);
                  if (!command.uncertain) {
                    setAction(null);
                    setPreview(null);
                    setFrozen(null);
                    command.clear();
                  }
                }} onConfirm={() => {
                  if (preview && !preview.eligible) {
                    setPreview(null);
                    return;
                  }
                  if ((action === 'transition') &&
                    !preview)
                    void prepare();
                  else
                    void run();
                }}>
      {action === 'reparent' ? (<ProductCatalogReference company={company} source={resource === 'brands' ? 'brands' : 'item-categories'} label="New parent" value={parent} exclude={id} access={access} values={row ?? {}} disabled={command.blocked} error={parent === id ? 'A record cannot be its own parent.' : undefined} onChange={setParent} />) : action === 'transition' ? (<div className="janso-flow">
        <Select label="Membership rule" value={String(scheme.membership_mode ?? '')} options={[
          { value: 'SINGLE', label: 'One category per product' },
          { value: 'MULTIPLE', label: 'Multiple categories per product' },
        ]} disabled={command.blocked || !!preview} onChange={(value) => setScheme((current) => ({ ...current, membership_mode: value }))} />
        <Checkbox checked={scheme.is_required === true} disabled={command.blocked || !!preview} onChange={(event) => setScheme((current) => ({
          ...current,
          is_required: event.target.checked,
        }))}>
          Required for active products
        </Checkbox>
        <Checkbox checked={scheme.is_active === true} disabled={command.blocked || !!preview} onChange={(event) => setScheme((current) => ({
          ...current,
          is_active: event.target.checked,
        }))}>
          Scheme available for new selections
        </Checkbox>
      </div>) : (<p>
        {action === 'deactivate'
          ? 'This record will be unavailable for new selections. The service checks dependent records before accepting the change.'
          : 'This record will become available for new selections.'}
      </p>)}
      {preview && (<div className="janso-flow">
        <Notice tone={preview.eligible ? 'success' : 'warning'}>
          {preview.eligible
            ? 'Review passed. Confirm to apply this change.'
            : 'The service found requirements that block this change.'}
        </Notice>
        {'scheme_id' in preview && (<ReviewList items={[
          {
            label: 'Categories',
            value: String(preview.category_count),
          },
          {
            label: 'Memberships',
            value: String(preview.membership_count),
          },
          {
            label: 'Affected families',
            value: String(preview.affected_family_count),
          },
        ]} />)}
        {preview.blockers
          .length > 0 && (<ul>
            {preview.blockers.map((reason) => (<li key={reason}>
              {reason.replaceAll('_', ' ').split(':')[0]}
            </li>))}
          </ul>)}
        {!command.blocked && (<Button variant="ghost" onClick={() => setPreview(null)}>
          Adjust and review again
        </Button>)}
      </div>)}
    </ConfirmDialog>
    <ConfirmDialog open={reload && !command.uncertain} title="Reload and review?" confirmLabel="Reload record" onCancel={() => setReload(false)} onConfirm={() => {
      command.clear();
      setAction(null);
      setPreview(null);
      setFrozen(null);
      setReload(false);
      refresh();
    }}>
      The latest record replaces this action’s selections.
    </ConfirmDialog>
    {guard.confirmation}
  </div>);
}
