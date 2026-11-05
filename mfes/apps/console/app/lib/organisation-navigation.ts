import type { Session } from '../session';
import type { AccessContext } from './access-directory';
import { accessContext } from './access-context';
import { companyPermission } from './company-permissions';
import { hasPeopleAccess } from './access-permissions';
import { departmentDirectoryAccess, organisationPermission } from './organisation-contract';
import { canAdministerOrganisation } from './session-authority';

/** Presentation follows each destination's actual scope; parent hubs grant no authority. */
export function organisationLinks(context: AccessContext) {
  const links: { label: string; href: string }[] = [];
  if (companyPermission(context, 'company.read') || companyPermission(context, 'company.create')) links.push({ label: 'Companies', href: '/companies/manage' });
  if (departmentDirectoryAccess(context) || organisationPermission(context, 'departments', 'manage')) links.push({ label: 'Departments', href: '/departments' });
  if (hasPeopleAccess(context)) links.push({ label: 'Users', href: '/users' });
  if (organisationPermission(context, 'user-groups', 'read') || organisationPermission(context, 'user-groups', 'manage')) links.push({ label: 'User groups', href: '/user-groups' });
  if (context.permissions.includes('role.read')) links.push({ label: 'Roles', href: '/roles' }, { label: 'Assignments', href: '/assignments' }, { label: 'Permissions', href: '/permissions' });
  return links;
}
export function organisationNavigationAvailable(session: Session) {
  return organisationLinks(accessContext(session)).length > 0 || canAdministerOrganisation(session);
}
