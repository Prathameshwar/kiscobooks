'use client';
import { SubjectHistory } from './SubjectHistory';
import { useEffect, useRef, useState } from 'react';
import { Button, Card, CardBody, ConfirmDialog, CustomFields, DataTable, Menu, Notice, PageHeader, PageNavigation, Pager, ReviewList, SearchSelect, SectionHeader, TextField, asErrorStatus, businessToday, useDisplayConfig, useFormatters, useListQuery, type Column } from '@janso/ui';
import { assertMaster, assertMasterFields, masterBase, masterRequest, useMasterLookup, useMasterRecord, type MasterPage } from '../lib/catalog-master-api';
import { masterCustomFields, masterLabel, validMasterDate, type MasterConfig, type MasterRow } from '../lib/catalog-masters';
import { requestFailure, type RequestFailure } from '../lib/service-call';
import { CatalogMasterError, masterReturnTo } from './CatalogMasterDirectory';
import { useUnsavedChanges } from '../lib/use-unsaved-changes';
import { WarehouseOperationPolicy } from './WarehouseOperationPolicy';
import { WarehouseCompanyField } from './WarehouseCompanyField';
import { structureLink, structureReturn } from '../lib/warehouse-structure';
import { identifierLink } from '../lib/units-identifiers';
import { masterDirectoryReturn, masterLink } from '../lib/master-navigation';
import { IdentifierNavigation, type IdentifierAccess } from './UnitsIdentifiersCommon';
import { inventoryBreadcrumbs, inventoryGroupForPath } from '../lib/inventory-navigation';

export function CatalogMasterDetail({ company, config, id, returnTo, canManage, canMove = false, canDeactivate = canManage, canPublish = false, canReadDepartments = false, canReadCompany = false, canReadWarehouseGroups = false, canReadWarehouseBins = false, identifierAccess, canReadManufacturerSites = false }: { company: string; config: MasterConfig; id: string; returnTo?: string; canManage: boolean; canMove?: boolean; canDeactivate?: boolean; canPublish?: boolean; canReadDepartments?: boolean; canReadCompany?: boolean; canReadWarehouseGroups?: boolean; canReadWarehouseBins?: boolean; identifierAccess?: IdentifierAccess; canReadManufacturerSites?: boolean }) {
  const record = useMasterRecord(company, config, id, false), display = useDisplayConfig(), format = useFormatters();
  const [action, setAction] = useState<'activate' | 'deactivate' | 'reparent' | null>(null), [pending, setPending] = useState(false), [failure, setFailure] = useState<RequestFailure | null>(null), [message, setMessage] = useState('');
  const [parent, setParent] = useState<string | null>(null), [date, setDate] = useState(() => businessToday(display.timezone));
  const busy = useRef(false), retry = useRef<{ payload: string; key: string } | null>(null), parents = useMasterLookup(company, 'item-groups');
  const moveFields = useRef<HTMLDivElement>(null);
  useUnsavedChanges(() => busy.current || !!action);
  const focusMoveError = () => requestAnimationFrame(() => moveFields.current?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus());
  const back = masterReturnTo(config, returnTo), root = '/masters/' + config.resource, row = record.row;
  const structureBack = config.resource === 'warehouses' && (returnTo?.startsWith('/masters/warehouse-groups') || returnTo?.startsWith('/masters/warehouse-bins')) ? structureReturn(returnTo, back) : null;
  const warehouseHere = root + '/' + id + (structureBack ? '?returnTo=' + encodeURIComponent(structureBack) : '');
  const here = masterLink(root + '/' + id, back);
  const sites = '/masters/manufacturer-sites?manufacturer_id=' + id;
  const versioned = Number.isSafeInteger(row?.row_version) && Number(row?.row_version) > 0;
  const open = (next: typeof action) => { setAction(next); setFailure(null); setParent(null); setDate(businessToday(display.timezone)); };
  async function execute() {
    if (!row || !action || busy.current || !versioned || (action === 'reparent' ? !canMove : action === 'deactivate' ? !canDeactivate : !canManage) || config.resource === 'warehouses' && row.is_system === true) return;
    if (action === 'reparent' && (!validMasterDate(date) || parent === id || !Number.isSafeInteger(row.policy_generation) || Number(row.policy_generation) < 1)) {
      setFailure({ status: 422, message: 'Check the parent change.', fields: { ...(!validMasterDate(date) ? { effective_from: 'Choose a valid effective date.' } : {}), ...(parent === id ? { parent_group_id: 'A group cannot be its own parent.' } : {}) } }); focusMoveError(); return;
    }
    const path = masterBase(company, config) + '/' + id + '/' + action;
    const body = { expected_version: row.row_version, ...(action === 'reparent' ? { expected_generation: row.policy_generation, parent_group_id: parent, effective_from: date } : {}) };
    const payload = JSON.stringify({ path, body }); if (retry.current?.payload !== payload) retry.current = { payload, key: crypto.randomUUID() };
    busy.current = true; setPending(true); setFailure(null);
    try { const updated = assertMaster(await masterRequest<MasterRow>({ path, method: 'POST', body, key: retry.current!.key }), company, id);
      record.setRow(updated); setMessage(action === 'reparent' ? 'Group parent updated. Previous hierarchy dates are retained.' : config.singular.charAt(0).toUpperCase() + config.singular.slice(1) + (action === 'activate' ? ' activated.' : ' deactivated. Existing records are retained.')); retry.current = null; setAction(null);
    } catch (error) { setFailure(requestFailure(error, 'master service')); focusMoveError(); }
    finally { busy.current = false; setPending(false); }
  }
  return <div className="janso-page">
    {config.resource === 'units' && identifierAccess ? <IdentifierNavigation title={row?.name ?? 'Unit details'} back={back} access={identifierAccess} onLeave={event => { if (pending) event.preventDefault(); }} /> : <PageNavigation back={{ href: structureBack ?? back, label: structureBack ? structureBack.includes('/warehouse-bins') ? 'bin / rack' : 'warehouse group' : config.title.toLowerCase() }} onNavigate={event => { if (pending) event.preventDefault(); }} breadcrumbs={[...inventoryBreadcrumbs(inventoryGroupForPath(root)!.key, '').slice(0, -1), { label: config.title, href: masterDirectoryReturn(config.resource, back) }, { label: row?.name ?? 'Details' }]} />}
    {config.resource === 'units' && identifierAccess?.['unit-conversions'] && <a className="janso-link" href={identifierLink('/masters/unit-conversions?from_unit_id=' + id, identifierLink(root + '/' + id, back))}>Conversions from this unit</a>}
    <PageHeader title={row?.name ?? `${config.singular.charAt(0).toUpperCase() + config.singular.slice(1)} details`} actions={row && (canManage || config.resource === 'manufacturers' && canReadManufacturerSites) ? <Menu label="Record actions" onSelect={() => {}} items={[...(canManage ? [{ id: 'edit', label: 'Edit ' + config.singular, href: masterLink(root + '/' + id + '/edit', here), disabledReason: pending || action ? 'Complete the current action first.' : undefined }] : []), ...(config.resource === 'manufacturers' && canReadManufacturerSites ? [{ id: 'sites', label: 'Manufacturer sites', href: masterLink(sites, here), disabledReason: pending || action ? 'Complete the current action first.' : undefined }] : [])]} /> : undefined} />
    {config.resource === 'manufacturers' && row && canReadManufacturerSites && <a className="janso-link" href={masterLink(sites, here)} onClick={event => { if (pending || action) event.preventDefault(); }}>Sites for this manufacturer</a>}
    <CatalogMasterError failure={record.failure ?? (!action ? failure : null)} retry={record.refresh} />
    {message ? <Notice tone="success">{message}</Notice> : null}
    {config.resource === 'warehouses' && row && <nav className="janso-page-navigation" aria-label="Warehouse structure">{canReadWarehouseGroups && <a className="janso-link" href={structureLink(root + '/' + id + '/group', warehouseHere)}>Primary warehouse group</a>}{canReadWarehouseBins && <a className="janso-link" href={structureLink('/masters/warehouse-bins?warehouse_id=' + id, warehouseHere)}>Bins / racks in this warehouse</a>}</nav>}
    {record.loading ? <p role="status">Loading {config.singular}…</p> : row ? <>
      {row.is_active === false ? <Notice tone="warning">This {config.singular} is inactive. Its existing records remain available.</Notice> : null}
      <Card><CardBody><div className="janso-flow"><SectionHeader title="Details" /><ReviewList items={record.fields.filter(field => field.visible && field.source === 'native' && field.key in row && !['row_version', ...(config.resource === 'warehouses' ? ['department_id', 'tax_registration_id'] : [])].includes(field.key)).map(field => {
          const value = row[field.key];
          const shown = value == null ? 'Not set' : field.key === 'quantity_increment' ? format.quantity(String(value), { precision: Number(row.decimal_places ?? 4) }) : typeof value === 'boolean' ? value ? 'Yes' : 'No' : String(value);
          return { label: masterLabel(config, field), value: shown };
        })} />
        {config.resource === 'warehouses' ? record.fields.filter(field => field.visible && ['department_id', 'tax_registration_id'].includes(field.key) && field.key in row).map(field => <WarehouseCompanyField key={field.key} company={company} type={field.key === 'department_id' ? 'department' : 'tax-registration'} name={field.key} label={masterLabel(config, field)} value={typeof row[field.key] === 'string' ? row[field.key] as string : null} canRead={field.key === 'department_id' ? canReadDepartments : canReadCompany} disabled onChange={() => undefined} />) : null}
        <CustomFields fields={masterCustomFields(record.fields)} values={row.custom_fields ?? {}} nativeValues={row} disabled currencies={display.currency ? [display.currency] : []} onChange={() => undefined} />
        {config.resource === 'warehouses' && row.is_system ? <Notice>Main and internal transit are system locations. Their identities and availability are protected.</Notice> : null}
        <div className="janso-form-actions">{(row.is_active ? canDeactivate : canManage) && typeof row.is_active === 'boolean' && !(config.resource === 'warehouses' && row.is_system !== false) ? <Button variant="ghost" disabled={!versioned || pending} onClick={() => open(row.is_active ? 'deactivate' : 'activate')}>{row.is_active ? 'Deactivate' : 'Activate'} {config.singular}</Button> : null}
          {config.resource === 'item-groups' && canMove ? <Button variant="ghost" disabled={!versioned || !Number.isSafeInteger(row.policy_generation) || Number(row.policy_generation) < 1 || pending} onClick={() => open('reparent')}>Change parent group</Button> : null}
          <Button variant="ghost" disabled={pending} onClick={() => { setMessage(''); record.refresh(); }}>Reload record</Button>
        </div>
      </div></CardBody></Card>
      {config.resource === 'item-groups' ? <GroupParentHistory key={String(row.policy_generation)} company={company} id={id} here={here} /> : null}
      {config.resource === 'warehouses' && row.kind !== 'INTERNAL_TRANSIT' ? <WarehouseOperationPolicy company={company} id={id} canPublish={canPublish} /> : null}
    </> : null}
    {row && !record.failure && <SubjectHistory company={company} entity={config.entity} id={id} />}
    <ConfirmDialog open={!!action} title={action === 'reparent' ? 'Change parent group?' : `${action === 'activate' ? 'Activate' : 'Deactivate'} ${config.singular}?`} confirmLabel={action === 'reparent' ? 'Save parent change' : action === 'activate' ? 'Activate' : 'Deactivate'} busy={pending} error={failure ? failure.message + (failure.status === 409 ? ' Cancel, reload the record and review its latest values before retrying.' : failure.status >= 500 ? ' The change could not be confirmed. Retry without changing the selection or date to recover the same request.' : '') : null}
      tone={action === 'deactivate' ? 'danger' : 'default'} onCancel={() => { setAction(null); setFailure(null); }} onConfirm={() => void execute()}>
      {action === 'reparent' ? <div className="janso-flow" ref={moveFields}><p>Select a parent or leave it empty to make this a top-level group. This appends a dated change; existing history is preserved.</p>
        <SearchSelect label="New parent group" name="parent_group_id" error={failure?.fields?.parent_group_id} value={parent} loadOptions={async args => { const page = await parents(args); return { ...page, items: page.items.map(option => ({ ...option, disabled: option.id === id })) }; }} minQueryLength={0} disabled={pending} onChange={value => { setParent(value); setFailure(null); }} />
        <TextField label="Effective from" name="effective_from" type="date" min="1000-01-01" value={date} disabled={pending} required error={failure?.fields?.effective_from} onChange={event => { setDate(event.target.value); setFailure(null); }} />
      </div> : <p>{action === 'deactivate' ? 'The record will be unavailable for new selections. Existing records are retained, and the service checks dependent records before accepting this change.' : 'The record will become available for new selections.'}</p>}
    </ConfirmDialog>
  </div>;
}

function GroupParentHistory({ company, id, here }: { company: string; id: string; here: string }) {
  const [data, setData] = useState<MasterPage>({ items: [], page: { limit: 50, has_more: false, next_cursor: null } }), [loading, setLoading] = useState(true), [failure, setFailure] = useState<RequestFailure | null>(null), [revision, setRevision] = useState(0);
  const [fields, setFields] = useState<import('../lib/catalog-masters').MasterField[]>([]);
  const query = useListQuery({ meta: loading || failure ? null : data.page }), params = query.params.toString();
  const refresh = () => { if (failure?.fields?.cursor) query.restart(); setRevision(value => value + 1); };
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setFailure(null);
    Promise.all([masterRequest<MasterPage>({ path: `/v1/companies/${company}/item-groups/${id}/parents?${params}`, signal: controller.signal }),
      masterRequest<import('../lib/catalog-masters').MasterFieldSet>({ path: `/v1/companies/${company}/entities/catalog.item_group_parent/field-set`, signal: controller.signal })])
      .then(([page, metadata]) => { if (!controller.signal.aborted) { setFields(assertMasterFields(metadata, company, 'catalog.item_group_parent')); setData(page); setLoading(false); } })
      .catch(error => { if (!controller.signal.aborted) { setFailure(requestFailure(error, 'master service')); setLoading(false); } });
    return () => controller.abort();
  }, [company, id, params, revision]);
  const definitions: Column<MasterRow>[] = [{ key: 'parent_group_id', header: 'Parent group', type: 'link', href: row => typeof row.parent_group_id === 'string' && /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(row.parent_group_id) ? masterLink('/masters/item-groups/' + row.parent_group_id, here) : null, value: row => 'parent_group_id' in row ? row.parent_group_id ?? 'Top-level group' : undefined }, { key: 'valid_from', header: 'Effective from', type: 'date' }, { key: 'valid_to', header: 'Effective to', type: 'date' }];
  return <Card><CardBody><SectionHeader title="Parent history" description="Dated assignments are retained when a group moves." /></CardBody>
    {failure?.fields?.cursor ? <CardBody><Notice tone="warning">Your history page position has expired. <Button variant="ghost" onClick={refresh}>Return to first history page</Button></Notice></CardBody> : null}
    <DataTable caption="Group parent history" rows={data.items} rowId={row => row.id} columns={definitions.filter(column => fields.some(field => field.visible && field.key === column.key))} loading={loading} error={failure ? asErrorStatus(failure.status) : null} errorDetail={failure?.message} onRetry={refresh} emptyTitle="No parent history" />
    <Pager count={loading || failure ? 0 : data.items.length} from={query.page.from} limit={query.limit} hasPrevious={query.page.hasPrevious} hasNext={query.page.hasNext} onPrevious={query.previousPage} onNext={query.nextPage} busy={loading} noun="assignment" />
  </Card>;
}
