'use client';
import { BellIcon, EmptyState, ErrorState, PageHeader, PageNavigation } from '@janso/ui';
import { NotificationRequests, NotificationDeliveries, NotificationReceipts } from './notifications/Operations';
import type { NotificationOwner } from '../lib/notification-api';
import { isNotificationId, notificationAccess, notificationQuery, notificationReturnPath, notificationRoot, validNotificationRoute, visibleNotificationSections, type NotificationQuery } from '../lib/notification-navigation';
import { NotificationScope } from './notifications/common';
import { NotificationChannels, NotificationOverview } from './notifications/Overview';
import { NotificationProviders } from './notifications/Providers';
import { NotificationTemplates } from './notifications/Templates';
import { NotificationAssignments } from './notifications/Assignments';
import { NotificationRouting } from './notifications/Routing';
import { NotificationRecipients, NotificationConsent, NotificationSuppressions } from './notifications/RecipientPolicy';

/**
 * What the record one level up *is*, for the back chip. Only two areas nest past `area/{id}` —
 * providers over their senders and templates over their variants and versions — so this covers
 * every parent that is not simply an area.
 */
const PARENT_LABELS: Record<string, string> = {
  providers: 'the provider account', senders: 'sender identities',
  templates: 'the template', variants: 'this channel and language',
};
export type NotificationAdminProps = { owner: NotificationOwner; permissions: readonly string[]; companyId?: string; route?: readonly string[]; query?: NotificationQuery };
export function NotificationAdmin(props: NotificationAdminProps) {
  return <Admin key={[props.owner, props.companyId, ...props.permissions, ...(props.route ?? []), JSON.stringify(props.query ?? {})].join('|')} {...props} />;
}
function Admin({ owner, permissions, companyId, route = [], query = {} }: NotificationAdminProps) {
  const area = route[0] ?? 'overview'; const root = notificationRoot(owner);
  const sections = visibleNotificationSections(owner, permissions); const section = sections.find(item => item.key === area);
  const title = owner === 'platform' ? 'Platform notifications' : 'Notifications';
  const parentLength = route.length === 6 ? 4 : route.length === 4 && route[2] === 'variants' ? 2 : route.length - 1;
  const returnPath = route.length > 1 ? notificationReturnPath(route, query.back) : undefined;
  const parent = route.length > 1 ? root + '/' + (returnPath ?? route.slice(0, parentLength).join('/')) : route.length ? root : owner === 'platform' ? '/platform' : '/organisation';
  // The back chip names where it *goes* — so the label is read off the same slice that produces
  // `parent`, not off the top-level area. On a version page the destination is the variant, and
  // "Back to templates" there would be a chip whose words and whose href disagree.
  const parentRoute = returnPath ? returnPath.split('?')[0].split('/') : route.slice(0, parentLength);
  const areaLabel = (sections.find(item => item.key === parentRoute[0])?.label ?? title).toLowerCase();
  const tail = [...parentRoute].reverse().find(part => !isNotificationId(part));
  const parentLabel = route.length > 1 ? parentRoute.length === 1 ? areaLabel : PARENT_LABELS[tail ?? ''] ?? areaLabel
    : route.length ? title : owner === 'platform' ? 'Platform administration' : 'Administration';
  return <div className="janso-page"><PageNavigation back={{ href: parent, label: parentLabel }} breadcrumbs={[
    { label: owner === 'platform' ? 'Platform administration' : 'Administration', href: owner === 'platform' ? '/platform' : '/organisation' },
    { label: title, href: root }, ...(area !== 'overview' ? [{ label: section?.label ?? 'Unavailable', href: root + '/' + area }] : []),
    ...(route.length > 1 ? [{ label: 'Record details' }] : []),
  ]} /><PageHeader title={title} lede={owner === 'platform' ? 'Email, SMS and WhatsApp for platform staff and pre-tenant recipients.' : 'Email, SMS and WhatsApp delivery for your organisation.'} />
    {!notificationAccess(owner, permissions) || !section ? <ErrorState status={403} detail="Notification access is required for this area." />
      : !validNotificationRoute(route) ? <EmptyState icon={<BellIcon />} title="Notification page not found." body="The address does not name a notification record in this scope." action={<a className="janso-btn janso-btn--ghost" href={root}>Back to {title.toLowerCase()}</a>} /> : <>
        {/*
          * The area strip, drawn as the console's tab row rather than a line of blue links:
          * thirteen `janso-link`s side by side gave the current area no mark at all, and every
          * label the same weight as every other. These are routes, so they are anchors carrying
          * `aria-current="page"` — not a `role="tablist"`, which would promise arrow-key
          * movement between panels that are in fact separate pages (design-system decision 11).
          */}
        <nav className="janso-tabs" aria-label="Notification areas">{sections.map(item => <a key={item.key} className="janso-tabs__tab" aria-current={item.key === area ? 'page' : undefined} href={item.key === 'overview' ? root : root + '/' + item.key}>{item.label}</a>)}</nav>
        <NotificationScope owner={owner} permissions={permissions} companyId={companyId} query={notificationQuery(query)}>
          {area === 'overview' ? <NotificationOverview /> : area === 'channels' ? <NotificationChannels /> : area === 'providers' ? <NotificationProviders route={route} /> : area === 'templates' ? <NotificationTemplates route={route} /> : area === 'assignments' ? <NotificationAssignments /> : area === 'routing' ? <NotificationRouting identity={route[1]} /> : area === 'recipients' ? <NotificationRecipients /> : area === 'consent' ? <NotificationConsent /> : area === 'suppressions' ? <NotificationSuppressions /> : area === 'requests' ? <NotificationRequests identity={route[1]} /> : area === 'receipts' ? <NotificationReceipts identity={route[1]} /> : <NotificationDeliveries identity={route[1]} recovery={area === 'recovery'} />}
        </NotificationScope></>}
  </div>;
}
