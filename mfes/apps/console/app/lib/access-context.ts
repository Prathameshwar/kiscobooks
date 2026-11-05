import type { Session } from '../session';
import type { AccessContext } from './access-directory';
import { accessReviewPermissions, tenantAccessPermissions } from './access-permissions';

export function accessContext(session: Session): AccessContext {
  return { permissions: accessReviewPermissions(session), tenantPermissions: tenantAccessPermissions(session),
    userId: session.user.id, tenantId: session.organisation.id, companyId: session.company.id, companyName: session.company.name, accountType: session.role, grants: session.grants };
}
