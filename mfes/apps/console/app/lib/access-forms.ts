import type { components } from '@janso/api-client/identity';
import { UUID, type RoleRecord, type UserRecord } from './access-directory';
export type AccessDraft = Record<string, string>;
export function validAccessDate(value: string) {
  const time = Date.parse(value + 'T00:00:00Z');
  return /^\d{4}-\d{2}-\d{2}$/.test(value) && Number.isFinite(time) && new Date(time).toISOString().slice(0, 10) === value;
}
export const userFields = ['first_name', 'middle_name', 'last_name', 'display_name', 'salutation', 'job_title', 'employee_code', 'phone_country_code', 'phone', 'reporting_manager_id', 'default_company_id', 'default_department_id', 'date_of_joining', 'date_of_exit'];
export function userDraft(row?: UserRecord | null): AccessDraft { return Object.fromEntries(['email', ...userFields].map(key => [key, String(row?.[key as keyof UserRecord] ?? '')])); }
export function validateUser(draft: AccessDraft, create: boolean) {
  const fields: Record<string, string> = {};
  if (!draft.first_name?.trim()) fields.first_name = 'Enter a first name.';
  if (create && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(draft.email?.trim() ?? '')) fields.email = 'Enter a valid email address.';
  if (!create && !draft.display_name?.trim()) fields.display_name = 'Enter a display name.';
  for (const [key, length] of [['first_name', 100], ['middle_name', 100], ['last_name', 100], ['display_name', 200], ['job_title', 120], ['employee_code', 40], ['phone', 20], ['phone_country_code', 8]] as const) if ((draft[key]?.trim().length ?? 0) > length) fields[key] = `Use no more than ${length} characters.`;
  if (draft.phone && !/^\d{4,20}$/.test(draft.phone)) fields.phone = 'Enter the phone number using digits.';
  if (draft.phone && !/^\+\d{1,4}$/.test(draft.phone_country_code ?? '')) fields.phone_country_code = 'Enter the country dial code, such as +91.';
  if (draft.phone_country_code && !draft.phone) fields.phone = 'Enter the phone number or clear its dial code.';
  for (const key of ['reporting_manager_id', 'default_company_id', 'default_department_id']) if (draft[key] && !UUID.test(draft[key]!)) fields[key] = 'Select an available record.';
  if (draft.default_department_id && !draft.default_company_id) fields.default_company_id = 'Select the company before its department.';
  for (const key of ['date_of_joining', 'date_of_exit']) if (draft[key] && !validAccessDate(draft[key]!)) fields[key] = 'Enter a valid date.';
  if (draft.date_of_joining && draft.date_of_exit && draft.date_of_exit < draft.date_of_joining) fields.date_of_exit = 'Exit date must be on or after joining date.';
  return fields;
}
export function userPayload(draft: AccessDraft, previous?: UserRecord | null): components['schemas']['UserInvite'] | components['schemas']['UserUpdate'] {
  const body: Record<string, string | null> = {};
  for (const key of userFields) {
    if (!previous && ['date_of_exit', 'default_department_id'].includes(key)) continue;
    const value = draft[key]?.trim() || null;
    if (previous ? value !== (previous[key as keyof UserRecord] ?? null) : value !== null) body[key] = value;
  }
  if (!previous) { body.email = draft.email!.trim().toLowerCase(); body.user_type = draft.user_type || 'tenant_user'; }
  if (previous && 'default_company_id' in body) body.default_department_id = draft.default_department_id || null;
  return body as components['schemas']['UserInvite'] | components['schemas']['UserUpdate'];
}
export function validateRole(draft: AccessDraft, permissions: readonly string[], catalogue: readonly string[], creating: boolean) {
  const fields: Record<string, string> = {};
  if (creating && !/^[a-z][a-z0-9_]{2,59}$/.test(draft.key ?? '')) fields.key = 'Use 3–60 lowercase letters, digits and underscores, starting with a letter.';
  if (!draft.name?.trim() || draft.name.trim().length > 150) fields.name = 'Enter a name of no more than 150 characters.';
  if ((draft.description?.length ?? 0) > 500) fields.description = 'Use no more than 500 characters.';
  if (!permissions.length || permissions.some(key => !catalogue.includes(key))) fields.permissions = 'Choose at least one permission from the catalogue.';
  return fields;
}
export function rolePayload(draft: AccessDraft, permissions: readonly string[], previous?: RoleRecord | null) {
  const result: Record<string, unknown> = {};
  for (const key of ['name', 'description', 'scope_hint'] as const) { const value = draft[key]?.trim() || null; if (!previous || value !== previous[key]) result[key] = value; }
  if (!previous) result.key = draft.key;
  if (!previous || [...permissions].sort().join('\n') !== [...previous.permissions].sort().join('\n')) result.permissions = [...permissions];
  return result;
}
export function validateAssignment(draft: AccessDraft, userId?: string) {
  const fields: Record<string, string> = {};
  for (const key of ['role_id', 'subject_id']) if (!UUID.test(draft[key] ?? '')) fields[key] = 'Select an available record.';
  if (draft.subject_type === 'user' && draft.subject_id?.toLowerCase() === userId?.toLowerCase()) fields.subject_id = 'You cannot change your own role assignments.';
  if (draft.scope_type !== 'tenant' && !UUID.test(draft.scope_id ?? '')) fields.scope_id = 'Select the scope for this grant.';
  if (!draft.reason?.trim() || draft.reason.length > 500) fields.reason = 'Enter an access reason of no more than 500 characters.';
  for (const key of ['valid_from', 'valid_to']) if (draft[key] && !validAccessDate(draft[key]!)) fields[key] = 'Enter a valid date.';
  const start = draft.valid_from || new Date().toISOString().slice(0, 10);
  if (draft.valid_to && draft.valid_to < start) fields.valid_to = 'Expiry must be on or after the start date.';
  return fields;
}
