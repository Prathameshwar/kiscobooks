import native from './warehouse-structure-fields.json';
import type { MasterField, MasterRow } from '../app/lib/catalog-masters';
import type { ServiceRequest } from '../app/lib/service-call';
export const COMPANY = '01990000-0000-7000-8000-000000000001', GROUP = '01990000-0000-7000-8000-000000000002', OTHER = '01990000-0000-7000-8000-000000000003', WAREHOUSE = '01990000-0000-7000-8000-000000000004', BIN = '01990000-0000-7000-8000-000000000005', FRESH = '01990000-0000-7000-8000-000000000006';
export const page = { limit: 25, has_more: false, next_cursor: null }, context = { company_id: COMPANY, timezone: 'Asia/Kolkata', business_date: '2026-10-25', policy_generation: 10, source_version: 50 };
const base = { company_id: COMPANY, row_version: 4, policy_generation: 10, created_at: '2026-10-25T00:00:00Z', updated_at: '2026-10-25T00:00:00Z', is_active: true };
export const group: MasterRow = { ...base, id: GROUP, code: 'NORTH', name: 'North region' }, other: MasterRow = { ...base, id: OTHER, code: 'SOUTH', name: 'South region' }, warehouse: MasterRow = { ...base, id: WAREHOUSE, code: 'MAIN', name: 'Main warehouse', kind: 'STORE', is_system: true }, bin: MasterRow = { ...base, id: BIN, code: 'RACK1', name: 'Rack one', warehouse_id: WAREHOUSE };
export const access = { groups: true, bins: true, warehouses: true };
export function structureFields(entity: string, operation?: string): MasterField[] {
  return (native as unknown as Record<string, MasterField[]>)[entity]!.map(field => ({ ...field, writable: field.writable && !(operation === 'update' && ['catalog.warehouse_bin', 'catalog.warehouse_group'].includes(entity) && (field.key === 'is_active' || entity === 'catalog.warehouse_bin' && field.key === 'warehouse_id')) }));
}
export function fixtureResponse(request: ServiceRequest): unknown {
  const path = new URL(request.path, 'https://api.invalid'), parts = path.pathname.split('/'), resource = parts[4], id = parts[5], action = parts[6];
  if (resource === 'entities') { const entity = id!; return { company_id: COMPANY, entity_type: entity, source_version: 50, fields: structureFields(entity, path.searchParams.get('operation') ?? undefined) }; }
  if (resource === 'warehouse-structure') return context;
  const row = resource === 'warehouse-groups' ? id === OTHER ? other : group : resource === 'warehouse-bins' ? bin : warehouse;
  if (['POST', 'PUT', 'PATCH'].includes(request.method ?? 'GET')) return { ...row, ...request.body as object, id: id ?? FRESH, row_version: 5, policy_generation: 11 };
  if (action === 'parents' || action === 'group-history') return { items: [{ id: FRESH, ...(action === 'parents' ? { group_id: GROUP, parent_group_id: null } : { warehouse_id: WAREHOUSE, group_id: GROUP }), valid_from: '2020-01-01', valid_to: null }], page };
  if (action === 'children') return { items: [other], page };
  if (action === 'members') return { items: [warehouse], page };
  if (id) return row;
  return { items: resource === 'warehouse-groups' ? [group, other] : [row], page };
}
