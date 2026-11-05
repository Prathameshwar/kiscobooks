import { notFound } from 'next/navigation';
import type { NotificationOwner } from '../lib/notification-api';
import { notificationRoot, validNotificationRoute, type NotificationQuery } from '../lib/notification-navigation';
import { pageContext } from '../lib/page-context';
import { Providers } from '../providers';
import { ConsoleShell } from './ConsoleShell';
import { NotificationAdmin } from './NotificationAdmin';
import { organisationPermissions } from '../lib/session-authority';

export async function NotificationPage({ owner, route = [], query = {} }: { owner: NotificationOwner; route?: string[]; query?: NotificationQuery }) {
  if (!validNotificationRoute(route)) notFound();
  const { session, context } = await pageContext();
  return <Providers session={session}><ConsoleShell session={session} context={context} activeHref={notificationRoot(owner) + (route.length ? '/' + route.join('/') : '')}>
    <NotificationAdmin owner={owner} permissions={owner === 'tenant' ? organisationPermissions(session) : session.permissions} companyId={owner === 'tenant' ? session.company.id : undefined} route={route} query={query} />
  </ConsoleShell></Providers>;
}
