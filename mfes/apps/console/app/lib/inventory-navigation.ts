import type { Session } from '../session';
import { companyPermission } from './company-permissions';

export type InventoryDestination = {
  label: string;
  href: string;
  permission: string;
  description: string;
};
export type InventoryGroup = {
  key: string;
  label: string;
  href: string;
  description: string;
  items: InventoryDestination[];
};
const master = (
  resource: string,
  label: string,
  permission: string,
  description: string,
): InventoryDestination => ({
  label,
  href: '/masters/' + resource,
  permission: permission + '.read',
  description,
});

/** Real, company-scoped destinations shared by the menu and its overview cards. */
export const inventoryGroups: InventoryGroup[] = [
  {
    key: 'products',
    label: 'Products and classification',
    href: '/inventory/products',
    description: 'Products, families, categories, brands and manufacturers.',
    items: [
      master(
        'items',
        'Products / SKUs',
        'item',
        'Find products and SKUs, review details and manage product relationships.',
      ),
      master(
        'product-families',
        'Product families',
        'item',
        'Organize related SKUs into product families.',
      ),
      master(
        'product-types',
        'Product types',
        'product_type',
        'Manage product types and their published revisions.',
      ),
      master(
        'category-schemes',
        'Category schemes',
        'category_scheme',
        'Define classification schemes and membership rules.',
      ),
      master(
        'item-categories',
        'Categories',
        'item_category',
        'Maintain categories and their parent relationships.',
      ),
      master(
        'brands',
        'Brands',
        'brand',
        'Manage brands, ownership and related series.',
      ),
      master(
        'brand-series',
        'Brand series',
        'brand_series',
        'Group products into series within a brand.',
      ),
      master(
        'manufacturers',
        'Manufacturers',
        'manufacturer',
        'Maintain manufacturers and their accounting party links.',
      ),
      master(
        'manufacturer-sites',
        'Manufacturer sites',
        'manufacturer_site',
        'Maintain production sites and regional details.',
      ),
      master(
        'item-groups',
        'Item groups',
        'item_group',
        'Organize products into groups and hierarchies.',
      ),
      {
        label: 'Product fields',
        href: '/products/custom-fields',
        permission: 'item.read',
        description:
          'Review custom product fields and manage definitions with the required access.',
      },
      {
        label: 'Product configuration',
        href: '/products/configuration',
        permission: 'product_configuration.read',
        description:
          'Review dated product defaults, inheritance and publication.',
      },
    ],
  },
  {
    key: 'units-identifiers',
    label: 'Units and identifiers',
    href: '/inventory/units-identifiers',
    description: 'Units, conversions, packaging and product identifiers.',
    items: [
      master(
        'units',
        'Units',
        'unit',
        'Manage measurement units, precision and quantity increments.',
      ),
      master(
        'unit-conversions',
        'Unit conversions',
        'unit',
        'Define conversions between compatible measurement units.',
      ),
      master(
        'pack-types',
        'Pack types',
        'pack_type',
        'Maintain reusable packaging types.',
      ),
      master(
        'identifier-types',
        'Identifier types',
        'identifier_type',
        'Define barcode and other identifier types.',
      ),
      master(
        'identifier-namespaces',
        'Identifier namespaces',
        'identifier_namespace',
        'Manage identifier namespaces and ownership.',
      ),
      master(
        'identifier-profiles',
        'Identifier profiles',
        'identifier_profile',
        'Define reusable identifier policies.',
      ),
    ],
  },
  {
    key: 'attributes',
    label: 'Attributes',
    href: '/inventory/attributes',
    description: 'Attribute definitions, options and sets or templates.',
    items: [
      master(
        'attribute-definitions',
        'Attribute definitions',
        'attribute_definition',
        'Define typed attributes and validation rules.',
      ),
      master(
        'attribute-options',
        'Attribute options',
        'attribute_option',
        'Maintain selectable options for attribute definitions.',
      ),
      master(
        'attribute-sets',
        'Attribute sets / templates',
        'attribute_set',
        'Compose reusable attribute sets and published revisions.',
      ),
    ],
  },
  {
    key: 'product-profiles',
    label: 'Reusable product profiles',
    href: '/inventory/product-profiles',
    description: 'Tracking, warranty, returns and handling policies.',
    items: [
      master(
        'inventory-templates',
        'Inventory / tracking profiles',
        'inventory_profile_template',
        'Define reusable batch, serial, expiry and valuation rules.',
      ),
      master(
        'warranty-policies',
        'Warranty profiles',
        'warranty_policy',
        'Manage warranty terms and their published revisions.',
      ),
      master(
        'return-policies',
        'Return profiles',
        'return_policy',
        'Define return windows and reusable return conditions.',
      ),
      master(
        'handling-profiles',
        'Handling profiles',
        'handling_profile',
        'Maintain handling instructions and temperature limits.',
      ),
    ],
  },
  {
    key: 'pricing',
    label: 'Pricing',
    href: '/inventory/pricing',
    description: 'Sales channels, price levels and price plans.',
    items: [
      master(
        'sales-channels',
        'Sales channels',
        'sales_channel',
        'Maintain the channels through which products are sold.',
      ),
      master(
        'price-levels',
        'Price levels',
        'price_plan',
        'Organize reusable pricing levels.',
      ),
      master(
        'price-plans',
        'Price plans',
        'price_plan',
        'Manage dated product pricing and currencies.',
      ),
    ],
  },
  {
    key: 'warehouses',
    label: 'Warehouses and structure',
    href: '/inventory/warehouses',
    description: 'Locations, warehouse groups and bins or racks.',
    items: [
      master(
        'warehouses',
        'Warehouses',
        'warehouse',
        'Maintain physical locations and regional details.',
      ),
      master(
        'warehouse-groups',
        'Warehouse groups',
        'warehouse_group',
        'Organize warehouses into dated reporting hierarchies.',
      ),
      master(
        'warehouse-bins',
        'Bins / racks',
        'warehouse_bin',
        'Maintain bins, racks and shelves within each warehouse.',
      ),
    ],
  },
];

/** Apply verified product structure consistently to master and inventory cards. */
export function productStructureGroup<
  T extends { key: string; description: string; items: InventoryDestination[] },
>(group: T, advanced?: boolean | null): T {
  if (advanced === undefined || advanced === true) return group;
  return {
    ...group,
    ...(group.key === 'products'
      ? { description: 'Products, categories, brands and manufacturers.' }
      : {}),
    items: group.items
      .filter((item) => item.href !== '/masters/product-families')
      .map((item) => item.href === '/masters/items'
        ? { ...item, label: 'Products', description: 'Browse the products and services you buy or sell.' }
        : item),
  };
}

export function inventoryNavigationFor(session: Session, advanced?: boolean | null): InventoryGroup[] {
  if (!session.company.id) return [];
  return inventoryGroups
    .map((group) => productStructureGroup(group, advanced))
    .map((group) => ({
      ...group,
      items: group.items.filter((item) =>
        companyPermission(session, item.permission, session.company.id),
      ),
    }))
    .filter((group) => group.items.length > 0);
}
export function inventoryGroupForPath(
  path: string,
): InventoryGroup | undefined {
  return (
    inventoryGroups.find(
      (group) =>
        path === group.href ||
        group.items.some(
          (item) => path === item.href || path.startsWith(item.href + '/'),
        ),
    )
  );
}
export function inventoryOverviewPath(path: string): boolean {
  return (
    path === '/inventory' ||
    inventoryGroups.some((group) => group.href === path)
  );
}
export function inventoryBreadcrumbs(key: string, title: string) {
  const group = inventoryGroups.find((item) => item.key === key)!;
  return [
    { label: 'Business overview', href: '/' },
    { label: 'Inventory masters', href: '/inventory' },
    { label: group.label, href: group.href },
    { label: title },
  ];
}
