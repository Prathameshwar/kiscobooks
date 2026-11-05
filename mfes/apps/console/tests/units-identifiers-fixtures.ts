import native from './units-identifiers-fields.json';
import type { MasterField, MasterRow } from '../app/lib/catalog-masters';
import type { ServiceRequest } from '../app/lib/service-call';

export const COMPANY = '01990000-0000-7000-8000-000000000001';
export const RECORD = '01990000-0000-7000-8000-000000000002';
export const SOURCE = '01990000-0000-7000-8000-000000000003';
export const ROOT = '01990000-0000-7000-8000-000000000004';
export const FRESH = '01990000-0000-7000-8000-000000000005';
export const page = { limit: 25, has_more: false, next_cursor: null };
export const access = {
  units: true,
  'unit-conversions': true,
  'pack-types': true,
  'identifier-types': true,
  'identifier-namespaces': true,
  'identifier-profiles': true,
};
export const units: MasterRow[] = [
  {
    id: SOURCE,
    company_id: COMPANY,
    code: 'BOX',
    name: 'Box',
    is_active: true,
    dimension: 'COUNT',
    symbol: 'box',
    row_version: 4,
  },
  {
    id: ROOT,
    company_id: COMPANY,
    code: 'EA',
    name: 'Each',
    is_active: true,
    dimension: 'COUNT',
    symbol: 'ea',
    row_version: 4,
  },
];
export function fields(entity: string, operation = 'create'): MasterField[] {
  return structuredClone(
    (native as unknown as Record<string, MasterField[]>)[
      entity.replace('catalog.', '') + ':' + operation
    ] ?? [],
  );
}
export function row(resource: string): MasterRow {
  return resource === 'unit-conversions'
    ? {
        id: RECORD,
        company_id: COMPANY,
        from_unit_id: SOURCE,
        canonical_unit_id: ROOT,
        numerator: '9007199254740993',
        denominator: '2',
      }
    : {
        id: RECORD,
        company_id: COMPANY,
        code: 'TEST',
        name: 'Test definition',
        is_active: true,
        row_version: 4,
        ...(resource === 'identifier-types' ? { is_barcode: false } : {}),
        ...(resource === 'identifier-profiles'
          ? { normalization_version: 1 }
          : {}),
      };
}
export function response(request: ServiceRequest): unknown {
  const url = new URL(request.path, 'https://api.invalid'),
    parts = url.pathname.split('/'),
    resource = parts[4]!,
    id = parts[5],
    action = parts[6];
  if (resource === 'entities')
    return {
      company_id: COMPANY,
      entity_type: id,
      fields: fields(id!, url.searchParams.get('operation') ?? 'create'),
    };
  if (resource === 'units' && id === 'convert')
    return {
      ...(request.body as object),
      input_quantity: (request.body as { quantity: string }).quantity,
      quantity: '12.0000',
    };
  if (resource === 'units')
    return id ? units.find((unit) => unit.id === id) : { items: units, page };
  if (action === 'requirements')
    return {
      items: [
        {
          id: FRESH,
          profile_id: RECORD,
          identifier_type: 'SERIAL',
          namespace_rule: 'COMPANY',
          min_count: 1,
          max_count: 1,
          requires_slot: false,
        },
      ],
      page,
    };
  if (['POST', 'PATCH'].includes(request.method ?? 'GET'))
    return {
      ...row(resource),
      ...(request.body as object),
      id: id ?? FRESH,
      row_version: 5,
      ...(action ? { is_active: action === 'activate' } : {}),
    };
  return id ? row(resource) : { items: [row(resource)], page };
}
