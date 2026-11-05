import native from './product-classification-fields.json';
import { entryConfiguration, entryDefaults } from './product-entry-fixtures';
import type { MasterField, MasterRow } from '../app/lib/catalog-masters';
import type { ServiceRequest } from '../app/lib/service-call';
import {
  classificationDefinitions,
  classificationResources,
  typeRevisionDefaults,
  type ClassificationResource,
} from '../app/lib/product-classification-resources';
import {
  COMPANY,
  RECORD,
  SOURCE,
  ROOT,
  FRESH,
  page,
} from './units-identifiers-fixtures';
export { COMPANY, RECORD, SOURCE, ROOT, FRESH, page };
export const EXTRA = '01990000-0000-7000-8000-000000000006';
export const access = {
  ...Object.fromEntries(
    classificationResources.map((resource) => [resource, true]),
  ),
  units: true,
  manufacturers: true,
  groups: true,
  parties: true,
  configuration: true,
  attributes: true,
  packTypes: true,
  publish: true,
  move: true,
  createProduct: true,
  activate: true,
} as import('../app/lib/product-classification-resources').ClassificationAccess;
export function fields(entity: string, operation = 'read'): MasterField[] {
  return structuredClone(
    (native as Record<string, MasterField[]>)[
      entity.replace('catalog.', '') + ':' + operation
    ] ?? [],
  );
}
export function record(
  resource: ClassificationResource,
  id = RECORD,
): MasterRow {
  return {
    ...classificationDefinitions[resource].initial,
    id,
    company_id: COMPANY,
    row_version: 4,
    policy_generation: 8,
    code: 'STANDARD',
    name:
      classificationDefinitions[resource].singular === 'product / SKU'
        ? 'Standard SKU'
        : 'Standard ' + classificationDefinitions[resource].singular,
    is_active: true,
    ...(resource === 'items'
      ? {
          sku: 'STANDARD',
          status: 'DRAFT',
          family_id: SOURCE,
          base_unit_id: SOURCE,
        }
      : resource === 'product-families'
        ? {
            status: 'DRAFT',
            structure_mode: 'SIMPLE',
            product_type_revision_id: SOURCE,
          }
        : resource === 'category-schemes'
          ? { membership_mode: 'SINGLE', is_required: false }
          : resource === 'item-categories'
            ? { scheme_id: SOURCE }
            : resource === 'brand-series'
              ? { brand_id: SOURCE }
              : resource === 'manufacturer-sites'
                ? {
                    manufacturer_id: SOURCE,
                    country_code: 'IN',
                    state_code: 'IN-MH',
                  }
                : {}),
  };
}
export const typeRevision = (id = SOURCE, parentId = RECORD): MasterRow => ({
  id,
  company_id: COMPANY,
  product_type_id: parentId,
  row_version: 4,
  revision: 1,
  kind: 'GOODS',
  published_at: null,
  ...structuredClone(typeRevisionDefaults),
});
const records = new Map<string, MasterRow>();
export function resetFixtures() {
  records.clear();
}
export function response(request: ServiceRequest): unknown {
  const url = new URL(request.path, 'https://api.invalid'),
    parts = url.pathname.split('/'),
    resource = parts[4] as ClassificationResource,
    id = parts[5],
    area = parts[6],
    revisionId = parts[7],
    action = parts[8],
    body = (request.body as Record<string, unknown>) ?? {},
    method = request.method ?? 'GET';
  if (url.pathname.endsWith('/field-set'))
    return {
      company_id: COMPANY,
      entity_type: parts[5],
      source_version: 8,
      fields: fields(parts[5]!, url.searchParams.get('operation') ?? 'read'),
    };
  if (request.service === 'identity')
    return url.pathname.endsWith('/states')
      ? [{ code: 'IN-MH', name: 'Maharashtra' }]
      : [{ code: 'IN', name: 'India' }];
  if (url.pathname.endsWith('/authoring-defaults')) return entryDefaults(url.searchParams);
  if (url.pathname.endsWith('/configuration') || url.pathname.endsWith('/product-configuration/effective')) return entryConfiguration(url.searchParams.get('as_of')!, url.searchParams.get('kind') === 'SERVICE' ? 'SERVICE' : 'GOODS');
  if (parts[4] === 'product-configuration')
    return {
      items: [
        {
          value: url.searchParams.get('value') ?? SOURCE,
          label: 'General type · revision 1',
          code: 'GENERAL',
        },
      ],
      page,
    };
  if (area === 'requirements')
    return {
      item_id: id,
      family_id: SOURCE,
      item_version: 4,
      family_version: 4,
      as_of: url.searchParams.get('as_of'),
      missing: [],
      product_definition_complete: true,
      activation_available: true,
      policy_generation: 8,
    };
  if (area === 'transition-preview')
    return {
      scheme_id: id,
      expected_version: body.expected_version,
      eligible: true,
      blockers: [],
      category_count: 3,
      membership_count: 5,
      affected_family_count: 2,
      preview_token: 'review-proof',
      policy_generation: 8,
      source_version: 8,
    };
  if (area === 'activation-preview')
    return {
      item_id: id,
      expected_version: 4,
      expected_family_version: 4,
      as_of: body.as_of,
      eligible: true,
      missing: [],
      sources: [],
      preview_token: 'activation-proof',
      policy_generation: 8,
      source_version: 8,
    };
  if (area === 'category-preview')
    return {
      family_id: id,
      expected_version: body.expected_version,
      valid_from: body.valid_from,
      membership_count: (body.categories as unknown[]).length,
      closing_count: 1,
      preview_token: 'category-proof',
      policy_generation: 8,
      source_version: 8,
    };
  if (
    [
      'groups',
      'categories',
      'manufacturers',
      'unit-bindings',
      'barcodes',
    ].includes(area ?? '')
  ) {
    if (method === 'GET')
      return {
        items: [],
        page: { ...page, limit: Number(url.searchParams.get('limit') ?? 25) },
      };
    return {
      family_id: resource === 'product-families' ? id : SOURCE,
      family_version: 5,
      item_id: resource === 'items' ? id : null,
      item_version: resource === 'items' ? 5 : null,
      changed_ids: [FRESH],
      policy_generation: 9,
    };
  }
  if (area === 'revisions') {
    if (method === 'GET' && !revisionId)
      return {
        items: [
          records.get(url.pathname + '/' + SOURCE) ?? typeRevision(SOURCE, id),
        ],
        page,
      };
    if (method === 'GET')
      return records.get(url.pathname) ?? typeRevision(revisionId, id);
    const row = {
      ...typeRevision(revisionId ?? FRESH, id),
      ...(records.get(url.pathname) ?? {}),
      ...body,
      row_version:
        method === 'POST' && !revisionId
          ? 1
          : Number(body.expected_version) + 1,
      ...(action === 'publish' ? { published_at: '2026-10-25T10:00:00Z' } : {}),
    };
    records.set(
      action
        ? url.pathname.replace('/publish', '')
        : revisionId
          ? url.pathname
          : url.pathname + '/' + FRESH,
      row,
    );
    return row;
  }
  if (method !== 'GET') {
    if (!id && resource === 'product-families')
      return {
        family: { ...record(resource, FRESH), ...body, row_version: 1 },
        default_item: {
          ...record('items', EXTRA),
          ...(body.default_item as object),
          family_id: FRESH,
          row_version: 1,
        },
      };
    if (area === 'activate' && resource === 'items')
      return {
        family_id: SOURCE,
        family_version: 5,
        item_id: id,
        item_version: 5,
        changed_ids: [id],
        policy_generation: 9,
      };
    const row = {
      ...record(resource, id ?? FRESH),
      ...records.get(url.pathname.replace('/' + area, '')),
      ...body,
      row_version: id ? Number(body.expected_version) + 1 : 1,
      ...(area === 'activate'
        ? { is_active: true }
        : area === 'deactivate'
          ? { is_active: false }
          : {}),
    };
    records.set(
      area
        ? url.pathname.replace('/' + area, '')
        : id
          ? url.pathname
          : url.pathname + '/' + FRESH,
      row,
    );
    return row;
  }
  if (id) {
    if (classificationResources.includes(resource))
      return records.get(url.pathname) ?? record(resource, id);
    return {
      id,
      company_id: COMPANY,
      code: 'GENERAL',
      name: 'General reference',
      is_active: true,
      row_version: 4,
      dimension: 'COUNT',
      symbol: 'pc',
    };
  }
  if (classificationResources.includes(resource)) {
    const row = record(resource);
    if (url.searchParams.has('brand_id'))
      row.brand_id = url.searchParams.get('brand_id');
    if (url.searchParams.has('scheme_id'))
      row.scheme_id = url.searchParams.get('scheme_id');
    if (url.searchParams.has('manufacturer_id'))
      row.manufacturer_id = url.searchParams.get('manufacturer_id');
    return { items: [row], page };
  }
  return {
    items: [
      {
        id: SOURCE,
        company_id: COMPANY,
        code: 'GENERAL',
        name: 'General reference',
        is_active: true,
        row_version: 4,
      },
    ],
    page,
  };
}
