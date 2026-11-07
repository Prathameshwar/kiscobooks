import { notFound } from 'next/navigation';
import { ErrorState } from '@janso/ui';
import { Providers } from '../providers';
import { ConsoleShell } from './ConsoleShell';
import { NoCompany } from './NoCompany';
import { pageContext } from '../lib/page-context';
import { companyPermission } from '../lib/company-permissions';
import { masterConfig } from '../lib/catalog-masters';
import { classificationResources, classificationDefinitions, type ClassificationResource, type ClassificationAccess } from '../lib/product-classification-resources';
import { ProductCatalogDirectory } from './ProductCatalogDirectory';
import { ProductExperience } from './ProductExperience';
import { ProductCreationExperience } from './ProductCreationExperience';
import { ProductCatalogEditor } from './ProductCatalogEditor';
import { ProductCatalogDetail } from './ProductCatalogDetail';
import { ProductTypeRevision } from './ProductTypeRevision';
import { ProductRecordExperience } from './ProductRecordExperience';
export async function ProductCatalogPage({
  resource,
  record = [],
  query = {},
}: {
  resource: ClassificationResource;
  record?: string[];
  query?: Record<string, string | string[] | undefined>;
}) {
  const uuid = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i,
    creating = record.length === 1 && record[0] === 'new',
    editing = creating || (record.length === 2 && record[1] === 'edit');
  const product = resource === 'items' || resource === 'product-families';
  const completed = product && record.length === 2 && record[1] === 'created';
  const revision =
    resource === 'product-types' &&
    record.length === 3 &&
    record[1] === 'revisions' &&
    (record[2] === 'new' || uuid.test(record[2]!));
  if (
    (record.length > 2 && !revision) ||
    (record.length === 2 && !editing && !completed) ||
    (record.length && !creating && !uuid.test(record[0]!))
  )
    notFound();
  const { session, context } = await pageContext(),
    company = session.company.id,
    permission = classificationDefinitions[resource].permission;
  const allows = (key: string) =>
    !!company && companyPermission(session, key, company);
  const canRead = allows(permission + '.read'),
    canManage = allows(permission + (product ? '.update' : '.manage')),
    canCreate = allows(product ? 'item.create' : permission + '.manage');
  const access: ClassificationAccess = {
    ...(Object.fromEntries(
      classificationResources.map((value) => [
        value,
        allows(classificationDefinitions[value].permission + '.read'),
      ]),
    ) as Record<ClassificationResource, boolean>),
    units: allows('unit.read'),
    manufacturers: allows('manufacturer.read'),
    groups: allows('item_group.read'),
    parties: allows('accounting.party.read'),
    configuration: allows('product_configuration.read'),
    attributes: allows('item.read') && allows('attribute_definition.read'),
    packTypes: allows('pack_type.read'),
    publish: allows('product_type.publish'),
    move: allows(permission + '.move'),
    createProduct: allows('item.create'),
    initialSetup: allows('item.update') && allows('product_configuration.read'),
    initialTax:
      allows('tax_rule.read') &&
      allows('tax_rule.manage') &&
      allows('tax_rule.publish'),
    initialPricing: allows('price_plan.read') && allows('price_plan.manage'),
    inventoryProfiles: allows('inventory_profile_template.read'),
    batches: allows('accounting.batch.read'),
    serials: allows('accounting.serial.read'),
    prepareBatches: allows('accounting.batch.read') && allows('accounting.batch.manage'),
    prepareSerials: allows('accounting.serial.read') && allows('accounting.serial.manage'),
    identifiers: allows('identifier_profile.read'),
    stock: allows('accounting.stock.read'),
    openingStock: allows('accounting.stock.read'),
    warehouses: allows('warehouse.read'),
    warehousePolicies: allows('item_warehouse_policy.read'),
    companyConfiguration: allows('company.read'),
    attributeSets: allows('attribute_set.read'),
    manageGroups: allows('item_group.manage'),
    manageTypes: allows('product_type.manage'),
    manageUnits: allows('unit.manage'),
    activate: allows('item.activate'),
  };
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query))
    if (typeof value === 'string') params.set(key, value);
  const returnTo =
      typeof query.returnTo === 'string' ? query.returnTo : undefined,
    id = !creating ? record[0]?.toLowerCase() : undefined;
  const config = masterConfig(resource)!;
  return (
    <Providers session={session}>
      <ConsoleShell
        session={session}
        context={context}
        activeHref={'/masters/' + resource}
      >
        {!company ? (
          <NoCompany
            action="configure"
            context={context}
            canCreate={companyPermission(session, 'company.create')}
          />
        ) : !canRead ||
          (creating && !canCreate) ||
          (editing && !creating && !canManage) ||
          (revision && record[2] === 'new' && !canManage) ? (
          <ErrorState
            status={403}
            detail="You need the product or classification permissions for this company to use this page."
          />
        ) : product && creating ? <ProductCreationExperience key={company} company={company} returnTo={returnTo} advancedOnly={resource === 'product-families'} /> : product && id ? <ProductRecordExperience key={company + ':' + resource + ':' + id} company={company} config={config} id={id} returnTo={returnTo} canManage={canManage} access={access} editing={editing} completed={completed} /> : product ? <ProductExperience company={company} access={access} initialQuery={params.toString()} canImport={allows('catalog.bulk.read')}>
          <ProductCatalogDirectory company={company} config={config} canManage={canManage} access={access} initialQuery={params.toString()} canImport={allows('catalog.bulk.read')} />
        </ProductExperience> : revision ? (
          <ProductTypeRevision
            key={company + ':' + id + ':' + record[2]}
            company={company}
            parentId={id!}
            id={record[2] === 'new' ? undefined : record[2]!.toLowerCase()}
            returnTo={returnTo}
            canManage={canManage}
            access={access}
          />
        ) : editing ? (
          <ProductCatalogEditor
            key={company + ':' + resource + ':' + (id ?? 'new')}
            company={company}
            config={config}
            id={id}
            returnTo={returnTo}
            access={access}
          />
        ) : id ? (
          <ProductCatalogDetail
            key={company + ':' + resource + ':' + id}
            company={company}
            config={config}
            id={id}
            returnTo={returnTo}
            canManage={canManage}
            access={access}
          />
        ) : (
          <ProductCatalogDirectory
            key={company + ':' + resource}
            company={company}
            config={config}
            canManage={canManage}
            access={access}
            initialQuery={params.toString()}
            canImport={allows('catalog.bulk.read')}
          />
        )}
      </ConsoleShell>
    </Providers>
  );
}
