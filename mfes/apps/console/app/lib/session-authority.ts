import type { Session } from '../session';
import { notificationAccess } from './notification-navigation';

/** Tenant-wide controls must never borrow an effective company/department grant. */
export function organisationPermissions(session: Pick<Session, 'grants'>, today = new Date().toISOString().slice(0, 10)): string[] {
  return [...new Set((session.grants ?? []).filter(grant => grant.scope_type === 'tenant'
    && grant.valid_from <= today && (!grant.valid_to || grant.valid_to >= today)).flatMap(grant => grant.permissions))];
}
export function canAdministerOrganisation(session: Pick<Session, 'grants'>): boolean {
  const permissions = organisationPermissions(session);
  return permissions.some(key => ['company.read', 'company.create', 'role.read', 'user.read', 'user.invite', 'group.read', 'group.manage', 'department.read', 'department.manage'].includes(key)) || notificationAccess('tenant', permissions);
}
export const platformNavigationPermissions = [
  'platform.tenant_access.read',
  'platform.tenant.read', 'platform.account.read', 'platform.config.manage',
  'platform.notification_provider.read', 'platform.notification_template.read', 'platform.notification_route.read',
  'platform.notification_delivery.read', 'platform.notification_request.read', 'platform.notification_recipient.read',
  'platform.notification_consent.manage', 'platform.notification_suppression.manage',
];
