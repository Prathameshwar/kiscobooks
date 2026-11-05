export const productProfileResources = [
  'inventory-templates',
  'warranty-policies',
  'return-policies',
  'handling-profiles',
] as const;
export const revisionedDefinitionResources = [
  ...productProfileResources,
  'manufacturing-operations',
  'manufacturing-routes',
] as const;
export type ProductProfileResource =
  (typeof revisionedDefinitionResources)[number];
export const isProductProfileResource = (
  resource: string,
): resource is ProductProfileResource =>
  (revisionedDefinitionResources as readonly string[]).includes(resource);
export type ProductProfileAccess = Record<
  (typeof productProfileResources)[number],
  boolean
> & {
  'manufacturing-operations'?: boolean;
  'manufacturing-routes'?: boolean;
  serviceItems?: boolean;
  publish: boolean;
  identifiers: boolean;
};
export const profileDefinitions = {
  'manufacturing-routes': {
    title: 'Manufacturing routes',
    singular: 'manufacturing route',
    entity: 'catalog.manufacturing_route',
    permission: 'manufacturing_route',
    parent: 'route_id',
  },
  'manufacturing-operations': {
    title: 'Manufacturing operations',
    singular: 'manufacturing operation',
    entity: 'catalog.manufacturing_operation',
    permission: 'manufacturing_operation',
    parent: 'operation_id',
  },
  'inventory-templates': {
    title: 'Inventory / tracking profiles',
    singular: 'inventory profile',
    entity: 'catalog.inventory_profile_template',
    permission: 'inventory_profile_template',
    parent: 'template_id',
  },
  'warranty-policies': {
    title: 'Warranty profiles',
    singular: 'warranty profile',
    entity: 'catalog.warranty_policy',
    permission: 'warranty_policy',
    parent: 'policy_id',
  },
  'return-policies': {
    title: 'Return profiles',
    singular: 'return profile',
    entity: 'catalog.return_policy',
    permission: 'return_policy',
    parent: 'policy_id',
  },
  'handling-profiles': {
    title: 'Handling profiles',
    singular: 'handling profile',
    entity: 'catalog.handling_profile',
    permission: 'handling_profile',
    parent: 'profile_id',
  },
} as const;

export const conditionCodes = [
  'ORIGINAL_PACKAGING',
  'PROOF_OF_PURCHASE',
  'COMPLETE_ACCESSORIES',
  'UNUSED',
  'UNDAMAGED',
] as const;
export const profileDefaults: Record<
  ProductProfileResource,
  Record<string, unknown>
> = {
  'manufacturing-routes': { specification: '', change_reason: '', steps: [] },
  'manufacturing-operations': {
    specification: '',
    change_reason: '',
    service_item_id: null,
  },
  'inventory-templates': {
    identifier_profile_id: null,
    lot_tracking: false,
    serial_tracking: false,
    expiry_required: false,
    manufacture_date_required: false,
    shelf_life_days: null,
    minimum_remaining_life_days: null,
    issue_strategy: 'FIFO',
    valuation_method: 'FIFO',
    negative_stock_policy: 'BLOCK',
  },
  'warranty-policies': {
    duration: '',
    duration_unit: 'MONTHS',
    start_trigger: 'SALE',
    coverage_description: null,
  },
  'return-policies': {
    returns_allowed: false,
    window_days: null,
    condition_codes: [],
  },
  'handling-profiles': {
    temperature_min: null,
    temperature_max: null,
    temperature_unit: null,
    fragile: false,
    keep_dry: false,
    keep_upright: false,
    instructions: null,
  },
};
