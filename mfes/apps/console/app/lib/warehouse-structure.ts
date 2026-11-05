'use client';
import type { components } from '@janso/api-client/catalog';
import { assertMaster, assertMasterFields, masterRequest } from './catalog-master-api';
import { masterBody, validMasterDate, type MasterConfig, type MasterField, type MasterFieldSet, type MasterRow } from './catalog-masters';
import { useServiceRead } from './service-resource';
import { inventoryOverviewPath } from './inventory-navigation';

export const structureId = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
export const structureBase = (company: string, resource: string) => '/v1/companies/' + company + '/' + resource;
export type StructureContext = components['schemas']['WarehouseStructureContext'];
export function structureReturn(value?: string, fallback = '/masters/warehouses', depth = 0): string {
  if (value === '/masters') return value;
  if (!value || value.length > 8192 || !value.startsWith('/') || /[%\\#]/.test(value.split('?')[0]!) || value.split('?').length > 2) return fallback;
  try {
    const url = new URL(value, 'https://console.invalid');
    if (url.origin === 'https://console.invalid' && !url.search && !url.hash && inventoryOverviewPath(url.pathname)) return url.pathname;
    if (url.origin !== 'https://console.invalid' || url.hash || !/^\/masters\/(?:warehouses|warehouse-groups|warehouse-bins)(?:\/[0-9a-f-]{36}(?:\/(?:edit|group|reparent))?)?$/.test(url.pathname)) return fallback;
    const out = new URLSearchParams();
    for (const [key, item] of url.searchParams) {
      if (key === 'returnTo' && depth < 3) out.set(key, structureReturn(item, fallback, depth + 1));
      if (key === 'q' && item.trim().length >= 2 && item.length <= 200 || key === 'is_active' && ['true', 'false'].includes(item) || key === 'sort' && ['id', '-id', 'code', '-code', 'name', '-name'].includes(item) || key === 'limit' && /^\d+$/.test(item) && +item >= 1 && +item <= 200 || key === 'warehouse_id' && structureId.test(item)) out.set(key, item);
    }
    return url.pathname + (out.size ? '?' + out : '');
  } catch { return fallback; }
}
export function structureLink(path: string, back: string) { return path + (path.includes('?') ? '&' : '?') + new URLSearchParams({ returnTo: structureReturn(back) }); }
export function structureTitle(row: MasterRow) { return row.name ?? row.code ?? 'Protected record'; }
export const structureVisible = (fields: readonly MasterField[], key: string) => fields.some(field => field.source === 'native' && field.key === key && field.visible && !field.conditional_access);
export const structureWritable = (fields: readonly MasterField[], keys: readonly string[]) => keys.every(key => fields.some(field => field.source === 'native' && field.key === key && field.visible && field.writable && !field.conditional_access));
export function useStructureFields(company: string, entity: string, operation?: 'create' | 'update', enabled = true) {
  return useServiceRead<MasterFieldSet>(enabled ? structureBase(company, 'entities/' + entity + '/field-set') + (operation ? '?operation=' + operation : '') : undefined, masterRequest, data => { assertMasterFields(data, company, entity); });
}
export function useStructureContext(company: string, groups = true) {
  return useServiceRead<StructureContext>(structureBase(company, 'warehouse-structure') + '?resource=' + (groups ? 'groups' : 'bins'), masterRequest, data => {
    if (data.company_id !== company || !validMasterDate(data.business_date) || !Number.isSafeInteger(data.policy_generation) || data.policy_generation < 1) throw { status: 502, message: 'The company business date could not be verified.' };
  });
}
export function structureReceipt(row: MasterRow, company: string, id?: string, previous?: number) {
  assertMaster(row, company, id);
  if (!structureId.test(row.id) || !Number.isSafeInteger(row.row_version) || Number(row.row_version) < 1 || previous != null && Number(row.row_version) <= previous) throw { status: 502, message: 'The save receipt could not be verified. Retry the same request.' };
}
export function structureBody(config: MasterConfig, fields: readonly MasterField[], values: Record<string, unknown>, edge: readonly MasterField[], previous?: MasterRow) {
  const result = masterBody(config, fields.filter(field => !field.conditional_access), values, previous);
  if (!previous && config.resource === 'warehouse-groups') {
    if (!structureWritable(edge, ['group_id', 'parent_group_id', 'valid_from', 'valid_to'])) result.errors.fields = 'Your field access does not allow initial hierarchy creation.';
    if (!validMasterDate(values.valid_from)) result.errors.valid_from = 'Enter a valid effective date.';
    if (values.parent_group_id != null && !structureId.test(String(values.parent_group_id))) result.errors.parent_group_id = 'Choose an available parent group.';
    result.body.valid_from = values.valid_from; result.body.parent_group_id = values.parent_group_id ?? null;
  }
  return result;
}
