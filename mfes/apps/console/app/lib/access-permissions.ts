import type { Session } from '../session';
import type { AccessContext } from './access-directory';

/** Identity filters access-directory reads by each grant's actual scope. */
export function accessReviewPermissions(session: Session, today = new Date().toISOString().slice(0, 10)): string[] {
  return [...new Set([...session.permissions, ...(session.grants ?? [])
    .filter(grant => grant.valid_from <= today && (!grant.valid_to || grant.valid_to >= today))
    .flatMap(grant => grant.permissions.filter(key => key === 'role.read' || key === 'role.assign'))])];
}

/** Tenant directories and role composition must not inherit company-only authority. */
export function tenantAccessPermissions(session: Session, today = new Date().toISOString().slice(0, 10)): string[] {
  return [...new Set((session.grants ?? []).filter(grant => grant.scope_type === 'tenant'
    && grant.valid_from <= today && (!grant.valid_to || grant.valid_to >= today)).flatMap(grant => grant.permissions))];
}

export function companyAccess(context: AccessContext, permission: string, companyId = context.companyId) {
  const today = new Date().toISOString().slice(0, 10);
  return !!companyId && (context.grants ?? []).some(grant => grant.permissions.includes(permission) && grant.valid_from <= today && (!grant.valid_to || grant.valid_to >= today) && (grant.scope_type === 'tenant' || grant.scope_type === 'company' && grant.scope_id?.toLowerCase() === companyId.toLowerCase()));
}
export function hasPeopleAccess(context: AccessContext) {
  const today = new Date().toISOString().slice(0, 10);
  return context.tenantPermissions.some(key => ['user.read', 'user.invite'].includes(key))
    || (context.grants ?? []).some(grant => grant.scope_type === 'company' && grant.valid_from <= today && (!grant.valid_to || grant.valid_to >= today) && grant.permissions.some(key => ['user.read', 'user.invite'].includes(key)));
}
export function permissionAuthority(context: AccessContext, key: string) {
  if (context.tenantPermissions.includes(key)) return 'Held at tenant scope';
  if (companyAccess(context, key)) return 'Held in selected company';
  const today = new Date().toISOString().slice(0, 10);
  if ((context.grants ?? []).some(grant => grant.permissions.includes(key) && grant.valid_from <= today && (!grant.valid_to || grant.valid_to >= today))) return 'Held in another scope';
  return 'Not held';
}
