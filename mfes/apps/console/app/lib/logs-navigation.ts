import type { Session } from '../session';
import { companyPermission } from './company-permissions';

export const logsAndActivitiesPath = '/logs-and-activities';

/** A link is available only for the company currently open. APIs recheck access. */
export function logsAndActivitiesAccess(session: Session) {
  const company = session.company.id;
  return {
    audit: !!company && companyPermission(session, 'audit.read', company),
    activities: !!company && companyPermission(session, 'activity.read', company),
  };
}
