import type { components } from '@janso/api-client/identity';
import type { AccessContext } from './access-directory';
const UUID = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
export const validOrganisationId = (value: string) => UUID.test(value);

export type OrganisationResource = 'departments' | 'user-groups';
export type Department = components['schemas']['DepartmentItem'];
export type DepartmentRow = components['schemas']['DepartmentListItem'];
export type UserGroup = components['schemas']['UserGroupItem'];
export type OrganisationRow = DepartmentRow | components['schemas']['UserGroupListItem'];
export type OrganisationRecord = Department | UserGroup;
export type OrganisationFields = components['schemas']['FieldSet'];
export type GroupMember = components['schemas']['GroupMemberListItem'];
export const organisationTitle = (resource: OrganisationResource) => resource === 'departments' ? 'Departments' : 'User groups';
export const organisationBase = (resource: OrganisationResource, context: AccessContext) => resource === 'departments' ? '/v1/companies/' + context.companyId + '/departments' : '/v1/user-groups';
export function organisationPermission(context: AccessContext, resource: OrganisationResource, operation: 'read' | 'manage', row?: { id: string; path?: string }) {
  const key = (resource === 'departments' ? 'department.' : 'group.') + operation;
  const today = new Date().toISOString().slice(0, 10);
  return (context.grants ?? []).some(grant => grant.permissions.includes(key) && grant.valid_from <= today && (!grant.valid_to || grant.valid_to >= today)
    && (grant.scope_type === 'tenant' || resource === 'departments' && !!context.companyId && (grant.scope_type === 'company' && grant.scope_id === context.companyId
      || !!row?.path && grant.scope_type === 'department' && !!grant.scope_id && row.path.split('/').includes(grant.scope_id.replaceAll('-', '')))));
}
export function departmentDirectoryAccess(context: AccessContext, operation: 'read' | 'manage' = 'read') {
  const today = new Date().toISOString().slice(0, 10);
  return !!context.companyId && (organisationPermission(context, 'departments', operation) || (context.grants ?? []).some(grant => grant.scope_type === 'department' && grant.permissions.includes('department.' + operation) && grant.valid_from <= today && (!grant.valid_to || grant.valid_to >= today)));
}
export function organisationReturn(resource: OrganisationResource, value?: string) {
  const base = '/' + resource;
  try {
    if (!value || !value.startsWith(base) || /[\\#\x00-\x1f\x7f]/.test(value)) return base;
    const url = new URL(value, 'https://console.invalid');
    if (url.origin !== 'https://console.invalid' || url.pathname !== base) return base;
    const params = new URLSearchParams();
    for (const [key, item] of url.searchParams) {
      if (url.searchParams.getAll(key).length !== 1) continue;
      if (key === 'q' && item.length <= (resource === 'departments' ? 20 : 40) || key === 'is_active' && ['true', 'false'].includes(item)
        || key === 'sort' && (resource === 'departments' ? ['path', 'code'] : ['id', 'code']).includes(item.replace(/^-/, ''))
        || key === 'limit' && /^\d+$/.test(item) && +item >= 1 && +item <= 200) params.set(key, item);
    }
    return base + (params.size ? '?' + params : '');
  } catch { return base; }
}
export function organisationPayload(fields: OrganisationFields['fields'], draft: Record<string, string>, row?: OrganisationRecord | null) {
  const body: Record<string, string | null> = {}, errors: Record<string, string> = {};
  for (const field of fields) {
    if (!field.writable || !field.is_visible) continue;
    const value = (draft[field.key] ?? '').trim(), validation = field.validation ?? {}, label = field.label ?? field.key;
    if (field.required && !value) errors[field.key] = label + ' is required.';
    else if (value && /[\x00-\x1f\x7f]/.test(value)) errors[field.key] = 'Use printable characters.';
    else if (value && typeof validation.max_length === 'number' && value.length > validation.max_length) errors[field.key] = 'Use at most ' + validation.max_length + ' characters.';
    else if (value && field.data_type === 'reference' && !UUID.test(value)) errors[field.key] = 'Choose a valid record.';
    const normalized = value || (validation.nullable ? null : '');
    if (!row || (row as unknown as Record<string, unknown>)[field.key] !== normalized) body[field.key] = normalized;
  }
  return { body, errors };
}
