export type NotificationOwner = 'tenant' | 'platform';
export function notificationPermission(owner: NotificationOwner, family: string, action: string): string {
  return owner === 'platform' ? `platform.notification_${family}.${action}` : `notification.${family}.${action}`;
}
