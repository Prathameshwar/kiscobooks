/** Server-safe native resource identities and bounded authoring contracts. */
export const classificationResources = [
  'items',
  'product-families',
  'product-types',
  'category-schemes',
  'item-categories',
  'brands',
  'brand-series',
  'manufacturer-sites',
] as const;
export type ClassificationResource = (typeof classificationResources)[number];
export const isClassificationResource = (
  value: string,
): value is ClassificationResource =>
  (classificationResources as readonly string[]).includes(value);
export const classificationDefinitions = {
  items: {
    title: 'Products / SKUs',
    singular: 'product / SKU',
    entity: 'catalog.item',
    permission: 'item',
    description:
      'Products and services you sell or purchase. Each SKU belongs to a product family.',
    initial: {
      sku: '',
      name: '',
      base_unit_id: null,
      sellable: true,
      purchasable: true,
      min_sale_quantity: null,
      custom_fields: {},
    },
    create: [
      'sku',
      'name',
      'base_unit_id',
      'sellable',
      'purchasable',
      'min_sale_quantity',
    ],
    update: ['sku', 'name', 'sellable', 'purchasable', 'min_sale_quantity'],
    filters: [
      'sku',
      'family_id',
      'base_unit_id',
      'status',
      'sellable',
      'purchasable',
    ],
  },
  'product-families': {
    title: 'Product families',
    singular: 'product family',
    entity: 'catalog.product_family',
    permission: 'item',
    description:
      'Group related SKUs under one definition. A new family includes its first, default SKU.',
    initial: {
      code: '',
      name: '',
      kind: 'GOODS',
      product_type_revision_id: null,
      brand_id: null,
      series_id: null,
      model_code: null,
      description: null,
      custom_fields: {},
    },
    create: [
      'code',
      'name',
      'kind',
      'product_type_revision_id',
      'brand_id',
      'series_id',
      'model_code',
      'description',
    ],
    update: [
      'code',
      'name',
      'brand_id',
      'series_id',
      'model_code',
      'description',
    ],
    filters: ['code', 'kind', 'status', 'product_type_revision_id', 'brand_id'],
  },
  'product-types': {
    title: 'Product types',
    singular: 'product type',
    entity: 'catalog.product_type',
    permission: 'product_type',
    description:
      'Define goods, services or both. Publish requirements before assigning a type to new products.',
    initial: { code: '', name: '', kind: 'GOODS', custom_fields: {} },
    create: ['code', 'name', 'kind'],
    update: ['code', 'name', 'kind'],
    filters: ['code', 'kind', 'is_active'],
  },
  'category-schemes': {
    title: 'Category schemes',
    singular: 'category scheme',
    entity: 'catalog.category_scheme',
    permission: 'category_scheme',
    description:
      'Organize independent category hierarchies. Preview the impact before changing membership rules or requiredness.',
    initial: { code: '', name: '', membership_mode: 'SINGLE' },
    create: ['code', 'name', 'membership_mode'],
    update: ['code', 'name'],
    filters: ['code', 'membership_mode', 'is_active'],
  },
  'item-categories': {
    title: 'Categories',
    singular: 'category',
    entity: 'catalog.item_category',
    permission: 'item_category',
    description:
      'Build a hierarchy within each scheme. Codes are unique inside their scheme.',
    initial: {
      code: '',
      name: '',
      scheme_id: null,
      parent_id: null,
      custom_fields: {},
    },
    create: ['code', 'name', 'scheme_id', 'parent_id'],
    update: ['code', 'name'],
    filters: ['code', 'scheme_id', 'parent_id', 'is_active'],
  },
  brands: {
    title: 'Brands',
    singular: 'brand',
    entity: 'catalog.brand',
    permission: 'brand',
    description:
      'Maintain brand identities, optional ownership and a clear parent hierarchy.',
    initial: {
      code: '',
      name: '',
      parent_brand_id: null,
      owner_party_id: null,
      custom_fields: {},
    },
    create: ['code', 'name', 'parent_brand_id', 'owner_party_id'],
    update: ['code', 'name', 'owner_party_id'],
    filters: ['code', 'parent_brand_id', 'is_active'],
  },
  'brand-series': {
    title: 'Brand series',
    singular: 'brand series',
    entity: 'catalog.brand_series',
    permission: 'brand_series',
    description:
      'Organize model lines under a brand. The brand is fixed after creation.',
    initial: { code: '', name: '', brand_id: null },
    create: ['code', 'name', 'brand_id'],
    update: ['code', 'name'],
    filters: ['code', 'brand_id', 'is_active'],
  },
  'manufacturer-sites': {
    title: 'Manufacturer sites',
    singular: 'manufacturer site',
    entity: 'catalog.manufacturer_site',
    permission: 'manufacturer_site',
    description:
      'Record production sites with a manufacturer and country. Select the state from the chosen country.',
    initial: {
      code: '',
      name: '',
      manufacturer_id: null,
      country_code: null,
      state_code: null,
    },
    create: ['code', 'name', 'manufacturer_id', 'country_code', 'state_code'],
    update: ['code', 'name', 'country_code', 'state_code'],
    filters: [
      'code',
      'manufacturer_id',
      'country_code',
      'state_code',
      'is_active',
    ],
  },
} as const;
export type ClassificationAccess = Record<ClassificationResource, boolean> & {
  units: boolean;
  manufacturers: boolean;
  groups: boolean;
  parties: boolean;
  configuration: boolean;
  attributes: boolean;
  packTypes: boolean;
  publish: boolean;
  move: boolean;
  createProduct: boolean;
  activate: boolean;
  initialSetup?: boolean;
  initialTax?: boolean;
  initialPricing?: boolean;
  inventoryProfiles?: boolean;
  batches?: boolean;
  serials?: boolean;
  stock?: boolean;
  openingStock?: boolean;
  warehouses?: boolean;
  companyConfiguration?: boolean;
  attributeSets?: boolean;
  manageGroups?: boolean;
  manageTypes?: boolean;
  manageUnits?: boolean;
  prepareBatches?: boolean;
  prepareSerials?: boolean;
  identifiers?: boolean;
};
export const typeRevisionDefaults: Record<string, unknown> = {
  inventory_modes: ['NON_STOCK'],
  tracking_modes: ['NONE'],
  unit_dimensions: ['COUNT'],
  allow_variants: true,
  require_brand: false,
  require_manufacturer: false,
  require_expiry: false,
  attribute_set_revision_id: null,
  inventory_template_revision_id: null,
  warranty_revision_id: null,
  return_policy_revision_id: null,
  handling_revision_id: null,
};
export const typeSets = [
  'inventory_modes',
  'tracking_modes',
  'unit_dimensions',
];
