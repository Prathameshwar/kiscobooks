import { ErrorState } from '@janso/ui';
import { Providers } from '../providers';
import { ConsoleShell } from './ConsoleShell';
import { NoCompany } from './NoCompany';
import { CatalogMasterDirectory } from './CatalogMasterDirectory';
import { CatalogMasterEditor } from './CatalogMasterEditor';
import { CatalogMasterDetail } from './CatalogMasterDetail';
import { masterConfig } from '../lib/catalog-masters';
import { pageContext } from '../lib/page-context';
import { companyPermission } from '../lib/company-permissions';
import { notFound } from 'next/navigation';
import { WarehouseSettings } from './WarehouseSettings';
import { WarehouseStructureDirectory } from './WarehouseStructureDirectory';
import { WarehouseStructureEditor } from './WarehouseStructureEditor';
import { WarehouseStructureDetail } from './WarehouseStructureDetail';
import { WarehouseStructureChange } from './WarehouseStructureChange';
import { isUnitsIdentifier } from '../lib/units-identifiers-resources';
import { UnitsIdentifiersDirectory } from './UnitsIdentifiersDirectory';
import { UnitsIdentifiersEditor } from './UnitsIdentifiersEditor';
import { UnitsIdentifiersDetail } from './UnitsIdentifiersDetail';
import type { IdentifierAccess } from './UnitsIdentifiersCommon';
import { isAttributeResource, type AttributeAccess } from '../lib/attribute-resources';
import { AttributeMasterDirectory } from './AttributeMasterDirectory';
import { AttributeMasterEditor } from './AttributeMasterEditor';
import { AttributeMasterDetail } from './AttributeMasterDetail';
import { AttributeSetRevision } from './AttributeSetRevision';
import { isPricingResource, type PricingAccess } from '../lib/pricing-resources';
import { PricingMasterDirectory } from './PricingMasterDirectory';
import { PricingMasterEditor } from './PricingMasterEditor';
import { PricingMasterDetail } from './PricingMasterDetail';

import { isProductProfileResource, profileDefinitions, type ProductProfileAccess } from '../lib/product-profile-resources';
import { ProductProfileDirectory } from './ProductProfileDirectory';
import { ProductProfileEditor } from './ProductProfileEditor';
import { ProductProfileDetail } from './ProductProfileDetail';
import { ProductProfileRevision } from './ProductProfileRevision';
import { isClassificationResource } from '../lib/product-classification-resources';
import { ProductCatalogPage } from './ProductCatalogPage';
import { PromotionStacksRoute } from './PromotionStacksRoute';
import { BomMasterPage } from './BomMasterPage';
import { VoucherTypesRoute } from './VoucherTypesRoute';

export async function CatalogMasterPage({ resource, record = [], query = {} }: { resource: string; record?: string[]; query?: Record<string, string | string[] | undefined> }) {
  if (resource === 'promotion-stack-policies') return PromotionStacksRoute({ record, query });
  if (resource === 'voucher-types') return VoucherTypesRoute({ record, query });
  if (isClassificationResource(resource)) return ProductCatalogPage({ resource, record, query });
  const config = masterConfig(resource), uuid = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
  const settings = resource === 'warehouses' && record.length === 1 && record[0] === 'settings';
  const structure = resource === 'warehouse-groups' || resource === 'warehouse-bins';
  const identifiers = isUnitsIdentifier(resource);
  const attributes = isAttributeResource(resource);
  const pricing = isPricingResource(resource);
  const profiles = isProductProfileResource(resource);
  const bomDefinition = resource === 'boms' && record.length === 3 && ['drafts', 'revisions', 'assignments'].includes(record[1]!) && (uuid.test(record[2]!) || record[2] === 'new' && record[1] !== 'revisions');
  const profileRevision = profiles && record.length === 3 && record[1] === 'revisions' && (record[2] === 'new' || uuid.test(record[2]!));
  const templateRevision = resource === 'attribute-sets' && record.length === 3 && record[1] === 'revisions' && (record[2] === 'new' || uuid.test(record[2]!));
  const membership = resource === 'warehouses' && record.length === 2 && record[1] === 'group';
  const reparent = resource === 'warehouse-groups' && record.length === 2 && record[1] === 'reparent';
  const creating = record.length === 1 && record[0] === 'new', editing = creating || record.length === 2 && record[1] === 'edit';
  if (!config || record.length > 2 && !templateRevision && !profileRevision && !bomDefinition || record.length === 2 && record[1] !== 'edit' && !membership && !reparent || record.length && !creating && !settings && !uuid.test(record[0]!)) notFound();
  if (resource === 'unit-conversions' && record.length === 2) notFound();
  const { session, context } = await pageContext(), company = session.company.id;
  const canRead = !!company && companyPermission(session, config.permission + '.read', company), canManage = !!company && companyPermission(session, config.permission + '.manage', company);
  const returnTo = typeof query.returnTo === 'string' ? query.returnTo : undefined, params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) if (typeof value === 'string') params.set(key, value);
  const id = !creating ? record[0]?.toLowerCase() : undefined;
  const access = { groups: !!company && companyPermission(session, 'warehouse_group.read', company), bins: !!company && companyPermission(session, 'warehouse_bin.read', company), warehouses: !!company && companyPermission(session, 'warehouse.read', company) };
  const warehouseId = typeof query.warehouse_id === 'string' && uuid.test(query.warehouse_id) ? query.warehouse_id.toLowerCase() : undefined;
  const definitionId = typeof query.definition_id === 'string' && uuid.test(query.definition_id) ? query.definition_id.toLowerCase() : undefined;
  const attributeAccess: AttributeAccess = {
    'attribute-definitions': !!company && companyPermission(session, 'attribute_definition.read', company),
    'attribute-options': !!company && companyPermission(session, 'attribute_option.read', company),
    'attribute-sets': !!company && companyPermission(session, 'attribute_set.read', company),
    units: !!company && companyPermission(session, 'unit.read', company),
    products: !!company && companyPermission(session, 'item.read', company) && companyPermission(session, 'attribute_definition.read', company),
    publish: !!company && companyPermission(session, 'attribute_set.publish', company),
  };
  const unitsAccess: IdentifierAccess = {
    units: !!company && companyPermission(session, 'unit.read', company),
    'unit-conversions': !!company && companyPermission(session, 'unit.read', company),
    'pack-types': !!company && companyPermission(session, 'pack_type.read', company),
    'identifier-types': !!company && companyPermission(session, 'identifier_type.read', company),
    'identifier-namespaces': !!company && companyPermission(session, 'identifier_namespace.read', company),
    'identifier-profiles': !!company && companyPermission(session, 'identifier_profile.read', company),
  };
  const pricingAccess: PricingAccess = {
    'sales-channels': !!company && companyPermission(session, 'sales_channel.read', company),
    'price-levels': !!company && companyPermission(session, 'price_plan.read', company),
    'price-plans': !!company && companyPermission(session, 'price_plan.read', company),
    purchaseRead: !!company && companyPermission(session, 'purchase_price.read', company),
    purchaseManage: !!company && companyPermission(session, 'purchase_price.manage', company),
  };
  const profileAccess: ProductProfileAccess = {
    'manufacturing-operations': !!company && companyPermission(session, 'manufacturing_operation.read', company),
    serviceItems: !!company && companyPermission(session, 'item.read', company),
    'inventory-templates': !!company && companyPermission(session, 'inventory_profile_template.read', company),
    'warranty-policies': !!company && companyPermission(session, 'warranty_policy.read', company),
    'return-policies': !!company && companyPermission(session, 'return_policy.read', company),
    'handling-profiles': !!company && companyPermission(session, 'handling_profile.read', company),
    publish: !!company && profiles && companyPermission(session, profileDefinitions[resource].permission + '.publish', company),
    identifiers: !!company && companyPermission(session, 'identifier_profile.read', company),
  };
  return <Providers session={session}><ConsoleShell session={session} context={context} activeHref={'/masters/' + resource}>
    {!company ? <NoCompany action="configure" context={context} canCreate={companyPermission(session, 'company.create')} /> : !canRead || (editing || (templateRevision || profileRevision || bomDefinition && record[1] === 'drafts') && record[2] === 'new') && !canManage || bomDefinition && record[1] === 'assignments' && record[2] === 'new' && !companyPermission(session, 'bom.assign', company) || membership && !access.groups || reparent && !companyPermission(session, 'warehouse_group.move', company) ? <ErrorState status={403} detail={structure || membership ? 'You need the warehouse structure permissions for this company to use this page.' : `You need ${config.permission}.read${editing ? ' and ' + config.permission + '.manage' : ''} for this company.`} />
      : settings ? <WarehouseSettings key={company} returnTo={returnTo} company={company} canManage={canManage} canPublish={companyPermission(session, 'warehouse.publish', company)} />
      : resource === 'boms' ? <BomMasterPage key={company + ':' + record.join(':')} company={company} config={config} record={record.map(part => uuid.test(part) ? part.toLowerCase() : part)} returnTo={returnTo} access={{ manage: canManage, publish: companyPermission(session, 'bom.publish', company), assign: companyPermission(session, 'bom.assign', company), goods: companyPermission(session, 'item.read', company), units: companyPermission(session, 'item.read', company) && companyPermission(session, 'unit.read', company), routes: companyPermission(session, 'manufacturing_route.read', company) && companyPermission(session, 'manufacturing_operation.read', company), warehouses: companyPermission(session, 'warehouse.read', company) }} />
      : profileRevision ? <ProductProfileRevision key={company + ':' + resource + ':' + id + ':' + record[2]} company={company} config={config} parentId={id!} id={record[2] === 'new' ? undefined : record[2]!.toLowerCase()} returnTo={returnTo} canManage={canManage} access={profileAccess} />
      : profiles ? editing ? <ProductProfileEditor key={company + ':' + resource + ':' + (id ?? 'new')} company={company} config={config} id={id} returnTo={returnTo} access={profileAccess} /> : id ? <ProductProfileDetail key={company + ':' + resource + ':' + id} company={company} config={config} id={id} returnTo={returnTo} canManage={canManage} access={profileAccess} /> : <ProductProfileDirectory key={company + ':' + resource} company={company} config={config} canManage={canManage} access={profileAccess} initialQuery={params.toString()} />
      : pricing ? editing ? <PricingMasterEditor key={company + ':' + resource + ':' + (id ?? 'new')} company={company} config={config} id={id} returnTo={returnTo} access={pricingAccess} /> : id ? <PricingMasterDetail key={company + ':' + resource + ':' + id} company={company} config={config} id={id} returnTo={returnTo} canManage={canManage} access={pricingAccess} /> : <PricingMasterDirectory key={company + ':' + resource} company={company} config={config} canManage={canManage} access={pricingAccess} initialQuery={params.toString()} />
      : templateRevision ? <AttributeSetRevision key={company + ':' + id + ':' + record[2]} company={company} setId={id!} id={record[2] === 'new' ? undefined : record[2]!.toLowerCase()} returnTo={returnTo} canManage={canManage} access={attributeAccess} />
      : attributes ? editing ? <AttributeMasterEditor key={company + ':' + resource + ':' + (id ?? 'new')} company={company} config={config} id={id} returnTo={returnTo} definitionId={definitionId} access={attributeAccess} /> : id ? <AttributeMasterDetail key={company + ':' + resource + ':' + id} company={company} config={config} id={id} returnTo={returnTo} canManage={canManage} access={attributeAccess} /> : <AttributeMasterDirectory key={company + ':' + resource} company={company} config={config} canManage={canManage} access={attributeAccess} initialQuery={params.toString()} />
      : identifiers ? editing ? <UnitsIdentifiersEditor key={company + ':' + resource + ':' + (id ?? 'new')} company={company} config={config} id={id} returnTo={returnTo} access={unitsAccess} /> : id ? <UnitsIdentifiersDetail key={company + ':' + resource + ':' + id} company={company} config={config} id={id} returnTo={returnTo} canManage={canManage} access={unitsAccess} /> : <UnitsIdentifiersDirectory key={company + ':' + resource} company={company} config={config} canManage={canManage} access={unitsAccess} initialQuery={params.toString()} />
      : membership || reparent ? <WarehouseStructureChange key={company + ':' + resource + ':' + id} company={company} id={id!} assignment={membership} canChange={membership ? canManage && companyPermission(session, 'warehouse_group.manage', company) : companyPermission(session, 'warehouse_group.move', company)} returnTo={returnTo} access={access} />
      : structure ? editing ? <WarehouseStructureEditor key={company + ':' + resource + ':' + (id ?? 'new')} company={company} config={config} id={id} returnTo={returnTo} warehouseId={warehouseId} access={access} /> : id ? <WarehouseStructureDetail key={company + ':' + resource + ':' + id} company={company} config={config} id={id} canManage={canManage} canMove={companyPermission(session, 'warehouse_group.move', company)} returnTo={returnTo} access={access} /> : <WarehouseStructureDirectory key={company + ':' + resource} company={company} config={config} canManage={canManage} initialQuery={params.toString()} access={access} />
      : editing ? <CatalogMasterEditor key={company + ':' + resource + ':' + (id ?? 'new')} company={company} config={config} id={id} returnTo={returnTo} canReadParty={companyPermission(session, 'accounting.party.read', company)} canReadDepartments={companyPermission(session, 'department.read', company)} canReadCompany={companyPermission(session, 'company.read', company)} />
      : id ? <CatalogMasterDetail key={company + ':' + resource + ':' + id} company={company} config={config} id={id} returnTo={returnTo} canManage={canManage} canMove={companyPermission(session, 'item_group.move', company)} canDeactivate={config.resource === 'warehouses' ? companyPermission(session, 'warehouse.deactivate', company) : canManage} canPublish={companyPermission(session, 'warehouse.publish', company)} canReadDepartments={companyPermission(session, 'department.read', company)} canReadCompany={companyPermission(session, 'company.read', company)} canReadWarehouseGroups={access.groups} canReadWarehouseBins={access.bins} identifierAccess={unitsAccess} canReadManufacturerSites={companyPermission(session, 'manufacturer_site.read', company)} />
      : <CatalogMasterDirectory key={company + ':' + resource} company={company} config={config} canManage={canManage} initialQuery={params.toString()} canReadWarehouseGroups={access.groups} canReadWarehouseBins={access.bins} identifierAccess={unitsAccess} />}
  </ConsoleShell></Providers>;
}
