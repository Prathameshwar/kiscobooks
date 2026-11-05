'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import type { components } from '@janso/api-client/identity';
import type { PageMeta, SearchSelectLoader, SearchSelectOption } from '@janso/ui';
import { serviceCall, requestFailure, type RequestFailure, type ServiceRequest } from './service-call';
import type { Session } from '../session';

export type UserRow = components['schemas']['UserListItem'];
export type UserRecord = components['schemas']['UserDetail'];
export type RoleRow = components['schemas']['RoleListItem'];
export type RoleRecord = components['schemas']['RoleDetail'];
export type Assignment = components['schemas']['AssignmentItem'];
export type Invitation = components['schemas']['InvitationItem'];
export type AccessPageData<T> = { items: T[]; page: PageMeta };
export type AccessResource = 'users' | 'roles' | 'assignments' | 'permissions';
export type AccessContext = { permissions: readonly string[]; tenantPermissions: readonly string[]; userId?: string; tenantId?: string; companyId?: string; companyName?: string; accountType?: string; grants?: Session['grants'] };
export async function accessCall<T>(request: ServiceRequest): Promise<T> {
  const result = await serviceCall<T>('/api/access', { ...request, service: 'identity' }, 'access service');
  // Identity cursor pages omit limit; the shared pager also needs the requested size.
  if (result && typeof result === 'object' && 'items' in result && 'page' in result) {
    const page = result as AccessPageData<unknown>;
    if (page.page) page.page = { ...page.page, limit: Number(new URL(request.path, 'https://console.invalid').searchParams.get('limit') ?? 50) };
  }
  return result;
}
export const UUID = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
export const userStatuses = ['invited', 'active', 'suspended', 'deactivated'];
export const userTypes = ['tenant_user', 'customer_portal_user', 'service_account', 'platform_admin'];
export const labelKey = (key: string) => key.replaceAll('_', ' ').replaceAll('.', ' · ');
export function safeAccessReturn(resource: AccessResource, value?: string) {
  const base = '/' + resource;
  try {
    if (!value || !value.startsWith(base) || /[\\#\x00-\x1f]/.test(value)) return base;
    const url = new URL(value, 'https://console.invalid');
    if (url.origin !== 'https://console.invalid' || url.pathname !== base) return base;
    const params = new URLSearchParams();
    const filters = resource === 'users' ? ['status', 'user_type'] : resource === 'roles' ? ['scope_hint'] : resource === 'assignments' ? ['subject_type', 'subject_id', 'role_id', 'scope_type', 'active'] : [];
    const sorts = resource === 'users' ? ['updated_at', 'display_name', 'email'] : resource === 'roles' ? ['name', 'key', 'updated_at'] : ['created_at'];
    const enums: Record<string, string[]> = { status: userStatuses, user_type: userTypes, scope_hint: ['platform', 'tenant', 'company', 'department'], subject_type: ['user', 'user_group'], scope_type: ['tenant', 'company', 'department'], active: ['true', 'false'] };
    for (const key of ['sort', 'limit', ...(resource === 'assignments' ? [] : ['q']), ...filters]) {
      const item = url.searchParams.get(key);
      if (!item || url.searchParams.getAll(key).length !== 1 || item.length > 100 || /[\x00-\x1f\x7f]/.test(item)) continue;
      if (enums[key] && !enums[key]!.includes(item) || key.endsWith('_id') && !UUID.test(item) || key === 'limit' && (!/^\d+$/.test(item) || Number(item) < 1 || Number(item) > 200) || key === 'sort' && item.split(',').some(part => !sorts.includes(part.replace(/^-/, '')))) continue;
      params.set(key, item);
    }
    return base + (params.size ? '?' + params : '');
  } catch { return base; }
}
export function assignmentStatus(row: Assignment, today: string) {
  return !row.is_active ? 'Revoked' : row.valid_from > today ? 'Scheduled' : row.valid_to && row.valid_to < today ? 'Expired' : 'Active';
}
export function scopedAccess(context: AccessContext, permission: string, type: string, id: string | null, today: string, departmentCompanyId?: string) {
  return (context.grants ?? []).some(grant => grant.permissions.includes(permission) && grant.valid_from <= today && (!grant.valid_to || grant.valid_to >= today)
    && (grant.scope_type === 'tenant' || (grant.scope_type === type && grant.scope_id === id) || (type === 'department' && grant.scope_type === 'company' && grant.scope_id === departmentCompanyId)));
}
export function useAccessRecord<T extends { id: string }>(path?: string, dependencies = '') {
  const [data, setData] = useState<T | null>(null), [loading, setLoading] = useState(!!path), [failure, setFailure] = useState<RequestFailure | null>(null), [revision, setRevision] = useState(0);
  const refresh = useCallback(() => setRevision(value => value + 1), []);
  useEffect(() => {
    const controller = new AbortController(); setLoading(!!path); setData(null); setFailure(null);
    if (path) accessCall<T>({ path, signal: controller.signal }).then(row => {
      if (controller.signal.aborted) return;
      if (!row?.id || row.id.toLowerCase() !== path.split('/').at(-1)?.toLowerCase()) throw { status: 502, message: 'The record response did not match. Reload before continuing.' };
      setData(row); setLoading(false);
    }).catch(error => { if (!controller.signal.aborted) { setFailure(requestFailure(error, 'access service')); setLoading(false); } });
    return () => controller.abort();
  }, [path, revision, dependencies]);
  return { data, setData, loading, failure, refresh };
}
/** Keyless writes are never blindly retried after a lost response. */
export function useAccessCommand() {
  const busy = useRef(false), unconfirmed = useRef(false), mounted = useRef(true), [pending, setPending] = useState(false), [failure, setFailure] = useState<RequestFailure | null>(null), [uncertain, setUncertain] = useState(false);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  async function execute<T>(request: ServiceRequest, success: (result: T) => void) {
    if (busy.current || unconfirmed.current) return;
    busy.current = true; setPending(true); setFailure(null);
    try { const result = await accessCall<T>(request); if (mounted.current) success(result); }
    catch (error) { if (mounted.current) { const value = requestFailure(error, 'access service'); setFailure(value); if (value.status >= 500 && !request.key) { unconfirmed.current = true; setUncertain(true); } } }
    finally { busy.current = false; if (mounted.current) setPending(false); }
  }
  return { execute, pending, failure, uncertain, reset: () => { if (!busy.current) { unconfirmed.current = false; setFailure(null); setUncertain(false); } } };
}
export function usePermissionCatalogue() {
  const [permissions, setPermissions] = useState<string[]>([]), [loading, setLoading] = useState(true), [failure, setFailure] = useState<RequestFailure | null>(null), [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setFailure(null);
    accessCall<{ permissions: string[] }>({ path: '/v1/permissions', signal: controller.signal }).then(result => {
      if (controller.signal.aborted) return;
      if (!Array.isArray(result.permissions) || result.permissions.some(key => typeof key !== 'string')) throw { status: 502, message: 'Unexpected permission catalogue response.' };
      setPermissions([...new Set(result.permissions)].sort()); setLoading(false);
    }).catch(error => { if (!controller.signal.aborted) { setFailure(requestFailure(error)); setLoading(false); } });
    return () => controller.abort();
  }, [revision]);
  return { permissions, loading, failure, refresh: () => setRevision(value => value + 1) };
}
export function useAccessLookup(kind: 'users' | 'roles' | 'groups' | 'companies' | 'departments', companyId?: string, excludeId?: string, activeUsersOnly = false): SearchSelectLoader {
  return useCallback(async ({ q, cursor, signal }) => {
    const params = new URLSearchParams({ limit: '50' }); if (cursor) params.set('cursor', cursor);
    if (q.trim().length >= 2) params.set('q', q.trim().slice(0, kind === 'departments' ? 20 : kind === 'groups' ? 40 : 100));
    const path = kind === 'companies' ? '/v1/session/companies' : kind === 'departments' ? `/v1/companies/${companyId}/departments` : kind === 'groups' ? '/v1/user-groups' : kind === 'users' && companyId ? `/v1/companies/${companyId}/users` : '/v1/' + kind;
    const page = await accessCall<AccessPageData<{ id: string; name?: string; display_name?: string; code?: string; key?: string; email?: string; is_active?: boolean; status?: string }>>({ path: path + '?' + params, signal });
    return { items: page.items.map(row => ({ id: row.id, label: row.display_name ?? row.name ?? row.code ?? row.id, meta: row.code ?? row.key ?? row.email,
      disabled: row.id.toLowerCase() === excludeId?.toLowerCase() || row.is_active === false || row.status === 'deactivated' || row.status === 'closed' || kind === 'users' && activeUsersOnly && row.status !== 'active' })), nextCursor: page.page.has_more ? page.page.next_cursor : null };
  }, [kind, companyId, excludeId, activeUsersOnly]);
}
/** Resolve an existing foreign key through the same authorized lookup surface. */
export function useAccessSelection(kind: 'companies' | 'departments', id?: string, companyId?: string, enabled = true) {
  const [selected, setSelected] = useState<SearchSelectOption | null>(null);
  useEffect(() => {
    const controller = new AbortController(); setSelected(null);
    if (enabled && id && UUID.test(id) && (kind !== 'departments' || companyId && UUID.test(companyId))) {
      const path = kind === 'companies' ? '/v1/session/companies' : '/v1/companies/' + companyId + '/departments';
      accessCall<AccessPageData<{ id: string; display_name?: string; name?: string; code?: string }>>({ path: path + '?id=' + id + '&limit=1', signal: controller.signal }).then(result => {
        if (controller.signal.aborted) return;
        const row = result.items.find(item => item.id === id);
        if (row) setSelected({ id: row.id, label: row.display_name ?? row.name ?? row.code ?? row.id, meta: row.code });
      }).catch(() => { /* The main record remains usable; an unreadable label stays unresolved. */ });
    }
    return () => controller.abort();
  }, [kind, id, companyId, enabled]);
  return selected;
}
