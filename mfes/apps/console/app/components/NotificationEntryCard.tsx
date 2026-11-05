import { ActionCard, BellIcon } from '@janso/ui';
import { notificationAccess, notificationRoot } from '../lib/notification-navigation';
import type { NotificationOwner } from '../lib/notification-ownership';

export function NotificationEntryCard({ owner, permissions }: { owner: NotificationOwner; permissions: readonly string[] }) {
  const allowed = notificationAccess(owner, permissions);
  if (owner === 'platform' && !allowed) return null;
  return <ActionCard icon={<BellIcon />} title={owner === 'platform' ? 'Platform notifications' : 'Notifications'}
    description={owner === 'platform' ? 'Manage platform email, SMS and WhatsApp providers, senders, templates, recipient policy and delivery history.' : 'Manage tenant email, SMS and WhatsApp settings, templates, recipient policy and delivery history.'}
    actionLabel={owner === 'platform' ? 'Manage platform notifications' : 'Manage notifications'}
    {...(allowed ? { href: notificationRoot(owner) } : { disabledReason: 'Notification access required' })} />;
}
