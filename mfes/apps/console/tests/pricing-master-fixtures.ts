import native from './pricing-master-fields.json';
import type { MasterField, MasterRow } from '../app/lib/catalog-masters';
import type { ServiceRequest } from '../app/lib/service-call';
export {
  COMPANY,
  RECORD,
  SOURCE,
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
  'sales-channels': true,
  'price-levels': true,
  'price-plans': true,
  purchaseRead: true,
  purchaseManage: true,
};
export const fields = (entity: string, operation = 'read'): MasterField[] =>
  structuredClone(
    (native as Record<string, MasterField[]>)[
      entity.replace('catalog.', '') + ':' + operation
    ] ?? [],
  );
export const row = (resource: string, id = RECORD): MasterRow => ({
  id,
  company_id: COMPANY,
  code: 'TEST',
  name: 'Test pricing',
  row_version: 4,
  ...(resource === 'price-plans'
    ? {
        purpose: 'SALE',
        price_level_id: SOURCE,
        currency: 'INR',
        tax_basis: 'EXCLUSIVE',
        custom_fields: {},
      }
    : {
        is_active: true,
        ...(resource === 'price-levels' ? { ordinal: 4 } : {}),
      }),
});
const records = new Map<string, MasterRow>();
export const resetFixtures = () => records.clear();
export function response(request: ServiceRequest): unknown {
  if (request.path === '/v1/reference/currencies')
    return [
      { code: 'INR', name: 'Indian Rupee' },
      { code: 'USD', name: 'US Dollar' },
    ];
  const url = new URL(request.path, 'https://api.invalid'),
    parts = url.pathname.split('/'),
    resource = parts[4]!,
    id = parts[5],
    method = request.method ?? 'GET',
    body = (request.body as Record<string, unknown>) ?? {};
  if (resource === 'entities')
    return {
      company_id: COMPANY,
      entity_type: id,
      fields: fields(id!, url.searchParams.get('operation') ?? 'read'),
    };
  const target = resource === 'pricing' ? 'price-levels' : resource,
    recordId = resource === 'pricing' ? SOURCE : (id ?? FRESH);
  if (method !== 'GET') {
    const original =
      records.get(target + ':' + recordId) ?? row(target, recordId);
    const updated = {
      ...original,
      ...body,
      row_version: id ? Number(body.expected_version ?? 4) + 1 : 1,
      ...(parts[6] ? { is_active: parts[6] === 'activate' } : {}),
      ...(resource === 'pricing'
        ? { code: 'PRICE1', name: 'Price 1', ordinal: 1 }
        : {}),
    };
    records.set(target + ':' + recordId, updated);
    return target === 'sales-channels'
      ? updated
      : {
          id: recordId,
          row_version: updated.row_version,
          policy_generation: 8,
          source_version: 3,
        };
  }
  if (id)
    return (
      records.get(resource + ':' + id) ??
      (resource === 'price-levels' && id === SOURCE
        ? { ...row(resource, id), code: 'PRICE1', name: 'Price 1', ordinal: 1 }
        : row(resource, id))
    );
  return { items: [row(resource)], page };
}
