import { notificationPermission, type NotificationOwner } from './notification-ownership';

/**
 * The areas of the notification console, in the order the work is actually done: transport first,
 * then the content it carries, then who may receive it, and only then the record of what happened.
 *
 * `group` is that reading order made visible — thirteen equal links tell a first-time operator
 * nothing about where to start. `blurb` is the landing card's description: "Manage routing for the
 * platform" restates the title and spends a card saying it, where the reader needs to know what a
 * route decides and what it does not.
 */
export const notificationSections = [
  { key: 'overview', label: 'Overview', family: '', group: 'Setup', blurb: 'Readiness of every channel, and where to go next.' },
  { key: 'channels', label: 'Channels', family: 'provider', group: 'Transport', blurb: 'Turn email, SMS and WhatsApp on or off, and see what each one still needs.' },
  { key: 'providers', label: 'Providers and senders', family: 'provider', group: 'Transport', blurb: 'Credential bindings, provider validation and the sender identities they verify.' },
  { key: 'templates', label: 'Templates', family: 'template', group: 'Content', blurb: 'Message content per channel and language, as immutable versions you activate by date.' },
  { key: 'assignments', label: 'Purpose assignments', family: 'template', group: 'Content', blurb: 'Which template a registered trigger uses, for which channel and effective period.' },
  { key: 'routing', label: 'Routing', family: 'route', group: 'Policy', blurb: 'The verified provider, sender and retry policy a purpose sends through.' },
  { key: 'recipients', label: 'Recipients', family: 'recipient', group: 'Policy', blurb: 'Look up a masked endpoint from a source-issued reference. Addresses are never editable here.' },
  { key: 'consent', label: 'Consent', family: 'consent', action: 'manage', group: 'Policy', blurb: 'Immutable consent evidence per endpoint and purpose. Marketing needs it recorded.' },
  { key: 'suppressions', label: 'Suppressions', family: 'suppression', action: 'manage', group: 'Policy', blurb: 'Block future delivery to a destination, category or purpose. Addresses are hashed server-side.' },
  { key: 'requests', label: 'Requests', family: 'request', group: 'Operations', blurb: 'What a source service asked for, and which channels planning selected or skipped.' },
  { key: 'deliveries', label: 'Deliveries', family: 'delivery', group: 'Operations', blurb: 'Attempts, provider acceptance and confirmed delivery, each as its own state.' },
  { key: 'receipts', label: 'Receipt inbox', family: 'delivery', group: 'Operations', blurb: 'Verified provider callbacks and how each one was matched. No raw payloads.' },
  { key: 'recovery', label: 'Recovery', family: 'delivery', group: 'Operations', blurb: 'Deliveries with no settled outcome. A blind retry can send the message twice.' },
] as const;
export type NotificationSection = typeof notificationSections[number]['key'];
export type NotificationSectionItem = typeof notificationSections[number];
/** The visible areas in group order, with the group each run belongs to — the nav's own shape. */
export const notificationSectionGroups = (owner: NotificationOwner, permissions: readonly string[]) => {
  const groups: { group: string; items: NotificationSectionItem[] }[] = [];
  for (const item of visibleNotificationSections(owner, permissions)) {
    const last = groups.at(-1);
    if (last && last.group === item.group) last.items.push(item);
    else groups.push({ group: item.group, items: [item] });
  }
  return groups;
};
export const notificationRoot = (owner: NotificationOwner) => owner === 'platform' ? '/platform/notifications' : '/settings/notifications';
export const notificationAccess = (owner: NotificationOwner, permissions: readonly string[]) =>
  notificationSections.some(item => item.family && permissions.includes(notificationPermission(owner, item.family, 'action' in item ? item.action : 'read')));
export const visibleNotificationSections = (owner: NotificationOwner, permissions: readonly string[]) =>
  notificationSections.filter(item => !item.family || permissions.includes(notificationPermission(owner, item.family, 'action' in item ? item.action : 'read')));
const uuid = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
export const isNotificationId = (value: string) => uuid.test(value);
export function validNotificationRoute(parts: readonly string[]): boolean {
  if (!parts.length) return true;
  const [area, id, child, childId] = parts;
  if (!notificationSections.some(item => item.key === area)) return false;
  if (parts.length === 1) return true;
  if (!id || !uuid.test(id)) return false;
  if (parts.length === 2) return ['providers', 'templates', 'routing', 'requests', 'deliveries', 'receipts'].includes(area);
  if (area === 'providers' && child === 'senders') return parts.length === 3 || (parts.length === 4 && uuid.test(childId));
  if (area === 'templates' && child === 'variants' && uuid.test(childId ?? '')) {
    return parts.length === 4 || (parts.length === 6 && parts[4] === 'versions' && uuid.test(parts[5]));
  }
  return false;
}
export type NotificationQuery = Record<string, string | string[] | undefined>;
export function notificationQuery(query: NotificationQuery): URLSearchParams {
  const values = new URLSearchParams();
  for (const key of ['cursor', 'status', 'channel', 'q', 'sort', 'request_id', 'event_key', 'provider_account_id', 'subject_id', 'recipient_endpoint_id']) {
    if (typeof query[key] === 'string') values.set(key, query[key] as string);
  }
  if (typeof query.back === 'string') values.set('back', query.back);
  return values;
}

const LIST_FILTERS: Record<string, readonly string[]> = {
  providers: ['status', 'channel', 'q', 'sort'], templates: ['event_key'],
  routing: ['channel', 'event_key', 'sort'], requests: ['status', 'event_key'],
  deliveries: ['status', 'channel', 'request_id'], receipts: ['status', 'provider_account_id'],
  recipients: ['subject_id'], consent: ['recipient_endpoint_id'], suppressions: ['channel'],
};
function listKeys(path: string): readonly string[] {
  return ['cursor', ...(path.includes('/') ? [] : LIST_FILTERS[path] ?? [])];
}
/** Carry only supported list predicates/position; form content never enters a return URL. */
export function notificationRecordLink(owner: NotificationOwner, destination: string | null, parent: string, query: URLSearchParams): string | null {
  if (!destination) return destination;
  const values = new URLSearchParams();
  for (const key of listKeys(parent)) { const value = query.get(key); if (value) values.set(key, value); }
  const directory = parent === 'recovery' ? 'deliveries' : parent;
  if ((!values.size && parent !== 'recovery') || !destination.startsWith(notificationRoot(owner) + '/' + directory + '/')) return destination;
  return destination + '?' + new URLSearchParams({ back: parent + '?' + values });
}
/** A return link must name this record's parent, within the same owner, with known filters. */
export function notificationReturnPath(route: readonly string[], value: unknown): string | undefined {
  if (typeof value !== 'string' || value.length > 3000 || /[\\#%]/.test(value.split('?')[0]) || value.includes('..')) return;
  const length = route.length === 6 ? 4 : route.length === 4 && route[2] === 'variants' ? 2 : route.length - 1;
  const parent = route.slice(0, length).join('/');
  const recovery = route.length === 2 && route[0] === 'deliveries';
  let url: URL;
  try { url = new URL('/' + value, 'https://notification.invalid'); }
  catch { return; }
  if (url.origin !== 'https://notification.invalid') return;
  const path = url.pathname.slice(1);
  if (path !== parent && !(recovery && path === 'recovery')) return;
  const keys = [...url.searchParams.keys()];
  if (keys.length !== new Set(keys).size || keys.some(key => !listKeys(path).includes(key))) return;
  return path + (url.searchParams.size ? '?' + url.searchParams : '');
}
