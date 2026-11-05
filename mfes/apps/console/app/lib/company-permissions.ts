import type { Session } from '../session';

/** Navigation hints only. Identity independently resolves current grants on every request. */
export function companyPermission(session: Pick<Session, 'grants'>, permission: string, companyId?: string,
  today = new Date().toISOString().slice(0, 10)): boolean {
  return (session.grants ?? []).some(grant => grant.valid_from <= today
    && (!grant.valid_to || grant.valid_to >= today) && grant.permissions.includes(permission)
    && (grant.scope_type === 'tenant' || (grant.scope_type === 'company'
      && permission !== 'company.create' && (!companyId || grant.scope_id === companyId))));
}

/** Tenant-wide history requires a current tenant grant, never a company's grant. */
export function tenantPermission(session: Pick<Session, 'grants'>, permission: string): boolean {
  return companyPermission({ grants: session.grants?.filter(grant => grant.scope_type === 'tenant') }, permission);
}
