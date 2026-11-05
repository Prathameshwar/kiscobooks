import native from './attribute-master-fields.json';
import type { MasterField, MasterRow } from '../app/lib/catalog-masters';
import type { ServiceRequest } from '../app/lib/service-call';
export {
  COMPANY,
  RECORD,
  SOURCE,
  ROOT,
  FRESH,
  page,
} from './units-identifiers-fixtures';
import {
  COMPANY,
  RECORD,
  SOURCE,
  FRESH,
  page,
} from './units-identifiers-fixtures';
export const access = {
  'attribute-definitions': true,
  'attribute-options': true,
  'attribute-sets': true,
  units: true,
  products: true,
  publish: true,
};
export const fields = (entity: string, operation = 'create'): MasterField[] =>
  structuredClone(
    (native as Record<string, MasterField[]>)[
      entity.replace('catalog.', '') + ':' + operation
    ] ?? [],
  );
export const definition = (type = 'TEXT'): MasterRow => ({
  id: SOURCE,
  company_id: COMPANY,
  code: 'COLOUR',
  name: 'Colour',
  value_type: type,
  measurement_dimension: null,
  is_variant_capable: true,
  is_active: true,
  row_version: 4,
});
export const row = (resource: string): MasterRow => ({
  id: RECORD,
  company_id: COMPANY,
  code: 'TEST',
  name: 'Test attribute',
  is_active: true,
  row_version: 4,
  ...(resource === 'attribute-definitions'
    ? {
        value_type: 'TEXT',
        measurement_dimension: null,
        is_variant_capable: true,
      }
    : resource === 'attribute-options'
      ? {
          definition_id: SOURCE,
          value_type: 'TEXT',
          value_text: 'Blue',
          unit_id: null,
        }
      : {}),
});
export const revisionRow = (id = FRESH): MasterRow => ({
  id,
  company_id: COMPANY,
  attribute_set_id: RECORD,
  revision: 1,
  row_version: 4,
  published_at: null,
});
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
  if (resource === 'attribute-definitions' && id === SOURCE)
    return definition();
  if (action === 'revisions') {
    if (parts[8] === 'members' && (request.method ?? 'GET') === 'GET')
      return {
        items: [
          {
            id: SOURCE,
            revision_id: FRESH,
            definition_id: SOURCE,
            position: 0,
            is_required: true,
            allow_variant_axis: true,
          },
        ],
        page,
      };
    if (request.method && request.method !== 'GET')
      return {
        ...revisionRow(parts[7] ?? FRESH),
        row_version:
          Number(
            (request.body as { expected_version?: number }).expected_version ??
              0,
          ) + 1,
        ...(parts[8] === 'publish'
          ? { published_at: '2026-10-25T01:00:00Z' }
          : {}),
      };
    return parts[7] ? revisionRow(parts[7]) : { items: [revisionRow()], page };
  }
  if (['POST', 'PATCH'].includes(request.method ?? 'GET'))
    return {
      ...row(resource),
      ...(request.body as object),
      id: id ?? FRESH,
      row_version:
        Number(
          (request.body as { expected_version?: number }).expected_version ?? 0,
        ) + 1,
      is_active: action === 'deactivate' ? false : true,
    };
  return id
    ? row(resource)
    : {
        items:
          resource === 'attribute-definitions'
            ? [definition()]
            : [row(resource)],
        page,
      };
}
