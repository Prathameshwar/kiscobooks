import { classificationResources, type ClassificationAccess } from './product-classification-resources';
import type { MasterRow } from './catalog-masters';
import { identifierResources } from './units-identifiers-resources';
import { attributeResources } from './attribute-resources';
import { pricingResources } from './pricing-resources';
import { productProfileResources } from './product-profile-resources';
import { inventoryGroupForPath, inventoryOverviewPath } from './inventory-navigation';
import { configurationLink, configurationReturn, configurationTrail } from './configuration-navigation';

const uuid = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
const resources: readonly string[] = [
  'boms',
  'promotion-stack-policies',
  'promotion-limits',
  ...classificationResources,
  ...identifierResources,
  ...attributeResources,
  ...pricingResources,
  ...productProfileResources,
  'units',
  'manufacturers',
  'item-groups',
  'warehouses',
  'warehouse-groups',
  'warehouse-bins',
];
const revised: readonly string[] = [
  'promotion-limits',
  'product-types',
  'attribute-sets',
  ...productProfileResources,
];
const ids = new Set([
  'family_id',
  'product_type_id',
  'product_type_revision_id',
  'brand_id',
  'parent_brand_id',
  'scheme_id',
  'parent_id',
  'manufacturer_id',
  'definition_id',
  'unit_id',
  'base_unit_id',
  'source_unit_id',
  'target_unit_id',
  'price_level_id',
  'warehouse_id',
  'group_id',
  'item_id',
  'itemId',
  'from_unit_id',
  'canonical_unit_id',
]);
const enums: Record<string, readonly string[]> = {
  status: ['DRAFT', 'ACTIVE', 'DISCONTINUED'],
  kind: ['GOODS', 'SERVICE', 'BOTH'],
  allowed_kind: ['GOODS', 'SERVICE', 'BOTH'],
  scope_kind: ['COMPANY', 'TYPE', 'GROUP', 'FAMILY', 'SKU'],
  dimension: ['COUNT', 'MASS', 'VOLUME', 'LENGTH', 'AREA', 'TIME', 'JOB'],
  measurement_dimension: [
    'COUNT',
    'MASS',
    'VOLUME',
    'LENGTH',
    'AREA',
    'TIME',
    'JOB',
  ],
  membership_mode: ['SINGLE', 'MULTIPLE'],
  purpose: ['SALE', 'PURCHASE', 'BOTH', 'REFERENCE_RETAIL'],
  value_type: ['TEXT', 'DECIMAL', 'INTEGER', 'BOOLEAN', 'DATE', 'MEASURE'],
};
/** Existing console pages only; query values do not grant access to their target. */
export function masterReturnQuery(url: URL): URLSearchParams | null {
  const parts = url.pathname.split('/').filter(Boolean);
  let supported = false;
  if (url.pathname === '/masters' || inventoryOverviewPath(url.pathname))
    return url.search ? null : new URLSearchParams();
  if (parts[0] === 'masters' && resources.includes(parts[1] ?? '')) {
    supported =
      (parts.length === 4 &&
        parts[1] === 'promotion-stack-policies' &&
        ['drafts', 'revisions'].includes(parts[2]!) &&
        (uuid.test(parts[3]!) ||
          (parts[2] === 'drafts' && parts[3] === 'new'))) ||
      parts.length === 2 ||
      (parts.length === 3 && parts[1] === 'items' && parts[2] === 'import') ||
      (parts.length === 3 &&
        (parts[2] === 'new' ||
          uuid.test(parts[2]!) ||
          (parts[1] === 'warehouses' && parts[2] === 'settings'))) ||
      (parts.length === 4 &&
        uuid.test(parts[2]!) &&
        (parts[3] === 'edit' || (['items', 'product-families'].includes(parts[1]!) && parts[3] === 'created')) &&
        parts[1] !== 'unit-conversions') ||
      (parts.length === 4 &&
        uuid.test(parts[2]!) &&
        ((parts[1] === 'warehouses' && parts[3] === 'group') ||
          (parts[1] === 'warehouse-groups' && parts[3] === 'reparent'))) ||
      (parts.length === 5 &&
        parts[1] === 'boms' &&
        uuid.test(parts[2]!) &&
        ['drafts', 'revisions', 'assignments'].includes(parts[3]!) &&
        (parts[4] === 'new' || uuid.test(parts[4]!))) ||
      (parts.length === 5 &&
        revised.includes(parts[1]!) &&
        uuid.test(parts[2]!) &&
        parts[3] === 'revisions' &&
        (parts[4] === 'new' || uuid.test(parts[4]!)));
  } else if (
    url.pathname === '/products/custom-fields' || url.pathname === '/products/attributes'
  )
    supported = true;
  else if (parts[0] === 'products' && parts[1] === 'configuration') {
    supported =
      parts.length === 2 ||
      (parts.length === 3 &&
        ['effective', 'adopt', 'new'].includes(parts[2]!)) ||
      (parts.length === 4 &&
        ['scopes', 'drafts', 'revisions'].includes(parts[2]!) &&
        uuid.test(parts[3]!));
  } else if (parts[0] === 'inventory' && ['batches', 'serials'].includes(parts[1] ?? '')) {
    supported = parts.length === 2 || parts.length === 3 && (parts[2] === 'new' || uuid.test(parts[2]!)) || parts.length === 4 && uuid.test(parts[2]!) && ['edit', 'history'].includes(parts[3]!) || parts.length === 5 && uuid.test(parts[2]!) && parts[3] === 'history' && uuid.test(parts[4]!);
  } else if (parts[0] === 'accounting' && parts[1] === 'parties') {
    supported =
      parts.length === 2 || (parts.length === 3 && uuid.test(parts[2]!));
  }
  if (!supported) return null;
  const query = new URLSearchParams();
  for (const [key, value] of url.searchParams) {
    if (
      url.searchParams.getAll(key).length !== 1 ||
      /[\x00-\x1f\x7f]/.test(value)
    )
      continue;
    if (
      (parts[1] === 'items' &&
        parts[2] === 'import' &&
        ((key === 'job' && uuid.test(value)) ||
          (key === 'view' && value === 'history'))) ||
      (ids.has(key) && uuid.test(value)) ||
      (key === 'q' && value.trim().length >= 2 && value.length <= 200) ||
      (key === 'sort' && /^-?(?:id|code|name|sku|revision)$/.test(value)) ||
      (key === 'limit' &&
        /^\d+$/.test(value) &&
        +value >= 1 &&
        +value <= 200) ||
      ([
        'is_active',
        'is_barcode',
        'is_variant_capable',
        'published',
        'sellable',
        'purchasable',
      ].includes(key) &&
        ['true', 'false'].includes(value)) ||
      (Object.hasOwn(enums, key) && enums[key]!.includes(value)) ||
      (key === 'country_code' && /^[A-Z]{2}$/.test(value)) ||
      (key === 'state_code' && /^[A-Z]{2}-[A-Z0-9]{1,3}$/.test(value)) ||
      (['code', 'sku', 'currency', 'role'].includes(key) &&
        /^[A-Z0-9_.-]{1,40}$/.test(value))
    )
      query.set(key, value);
  }
  return query;
}
export function masterReturn(
  value: string | undefined,
  fallback = '/settings',
  depth = 0,
): string {
  if (
    !value ||
    value.startsWith('//') ||
    value.split('?').length > 2 ||
    /[%\\#]/.test(value.split('?')[0]!)
  )
    return fallback;
  return configurationReturn(value, fallback, masterReturnQuery, depth);
}
export const masterLink = (path: string, back: string) =>
  configurationLink(path, masterReturn(back));

/** A record's contextual Back link and its directory breadcrumb have different purposes. */
export function masterDirectoryReturn(resource: string, back?: string): string {
  const root = '/masters/' + resource;
  const directory = configurationTrail(masterReturn(back, root)).find(
    (value) => new URL(value, 'https://console.invalid').pathname === root,
  );
  return (
    directory ??
    masterLink(root, inventoryGroupForPath(root)?.href ?? '/inventory')
  );
}
const direct: Record<string, string> = {
  units: 'units',
  manufacturers: 'manufacturers',
  'item-groups': 'item-groups',
  groups: 'item-groups',
  families: 'product-families',
  'product-families': 'product-families',
  items: 'items',
  'product-types': 'product-types',
  brands: 'brands',
  'brand-series': 'brand-series',
  'category-schemes': 'category-schemes',
  'item-categories': 'item-categories',
  'manufacturer-sites': 'manufacturer-sites',
  'pack-types': 'pack-types',
  'identifier-profiles': 'identifier-profiles',
  'attribute-definitions': 'attribute-definitions',
  'attribute-options': 'attribute-options',
  'price-levels': 'price-levels',
};
const revisions: Record<string, string> = {
  'product-type-revisions': 'product-types',
  'attribute-set-revisions': 'attribute-sets',
  'inventory-template-revisions': 'inventory-templates',
  'warranty-revisions': 'warranty-policies',
  'return-policy-revisions': 'return-policies',
  'handling-revisions': 'handling-profiles',
};
/** Revision targets require a parent from the protected native option projection. */
export function masterReferencePath(
  source: string,
  id: string,
  parentId?: string | null,
): string | null {
  if (!uuid.test(id)) return null;
  if (['items', 'product-families'].includes(source)) return '/masters/' + source + '/' + id;
  if (source === 'parties') return '/accounting/parties/' + id;
  if (Object.hasOwn(direct, source))
    return '/masters/' + direct[source] + '/' + id;
  if (Object.hasOwn(revisions, source) && parentId && uuid.test(parentId))
    return (
      '/masters/' + revisions[source] + '/' + parentId + '/revisions/' + id
    );
  return null;
}

/** The revision page handles both immutable viewing and authorized draft editing. */
export function masterRevisionActions(
  root: string,
  row: MasterRow,
  back: string,
  canEdit: boolean,
  blocked: boolean,
) {
  if (
    !uuid.test(row.id) ||
    !masterReturnQuery(new URL(root + '/' + row.id, 'https://console.invalid'))
  )
    return [];
  const href = masterLink(root + '/' + row.id, back);
  const disabledReason = blocked
    ? 'Complete the current action first.'
    : undefined;
  return [
    { id: 'view', label: 'View revision', href, disabledReason },
    ...(canEdit && row.published_at === null
      ? [{ id: 'draft', label: 'Open draft', href, disabledReason }]
      : []),
  ];
}

export function catalogRelatedLinks(
  resource: string,
  row: MasterRow,
  visible: (key: string) => boolean,
  access: ClassificationAccess,
  back: string,
): { id: string; label: string; href: string }[] {
  const links: { id: string; label: string; href: string }[] = [];
  const add = (id: string, label: string, path: string, permitted: boolean) => {
    if (permitted) links.push({ id, label, href: masterLink(path, back) });
  };
  const reference = (
    key: string,
    source: string,
    label: string,
    permitted: boolean,
  ) => {
    const path =
      typeof row[key] === 'string' && visible(key)
        ? masterReferencePath(source, row[key] as string)
        : null;
    if (path) add('related-' + key, label, path, permitted);
  };
  if (!uuid.test(row.id)) return links;
  if (resource === 'items') {
    reference(
      'family_id',
      'product-families',
      'Open product family',
      access['product-families'],
    );
    reference('base_unit_id', 'units', 'Open base unit', access.units);
  } else if (resource === 'product-families') {
    add(
      'related-skus',
      'SKUs in this family',
      '/masters/items?family_id=' + row.id,
      access.items,
    );
    reference('brand_id', 'brands', 'Open brand', access.brands);
    reference(
      'series_id',
      'brand-series',
      'Open brand series',
      access['brand-series'],
    );
  } else if (resource === 'category-schemes') {
    add(
      'related-categories',
      'Categories in this scheme',
      '/masters/item-categories?scheme_id=' + row.id,
      access['item-categories'],
    );
  } else if (resource === 'item-categories') {
    reference(
      'scheme_id',
      'category-schemes',
      'Open category scheme',
      access['category-schemes'],
    );
    reference(
      'parent_id',
      'item-categories',
      'Open parent category',
      access['item-categories'],
    );
    add(
      'related-children',
      'Child categories',
      '/masters/item-categories?parent_id=' + row.id,
      access['item-categories'] && visible('parent_id'),
    );
  } else if (resource === 'brands') {
    reference('parent_brand_id', 'brands', 'Open parent brand', access.brands);
    reference('owner_party_id', 'parties', 'Open owner party', access.parties);
    add(
      'related-series',
      'Brand series',
      '/masters/brand-series?brand_id=' + row.id,
      access['brand-series'],
    );
    add(
      'related-children',
      'Child brands',
      '/masters/brands?parent_brand_id=' + row.id,
      access.brands && visible('parent_brand_id'),
    );
  } else if (resource === 'brand-series')
    reference('brand_id', 'brands', 'Open brand', access.brands);
  else if (resource === 'manufacturer-sites')
    reference(
      'manufacturer_id',
      'manufacturers',
      'Open manufacturer',
      access.manufacturers,
    );
  return links;
}
