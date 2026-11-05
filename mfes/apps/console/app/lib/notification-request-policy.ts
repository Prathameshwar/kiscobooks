/** Fixed notification management surface. Provider callbacks never pass through this proxy. */
export function allowedNotificationRequest(service: string, method: string, path: string): boolean {
  if (service !== 'notification' || !path.startsWith('/v1/') || /[\\#]/.test(path) || path.includes('..')) return false;
  let url: URL;
  try { url = new URL(path, 'https://notification.invalid'); } catch { return false; }
  if (url.origin !== 'https://notification.invalid' || url.pathname.includes('%')) return false;
  const keys = [...url.searchParams.keys()];
  if (keys.length !== new Set(keys).size || keys.some(key => !['limit', 'cursor', 'status', 'event_key', 'channel', 'request_id', 'sort', 'q', 'provider_account_id', 'recipient_endpoint_id', 'subject_id'].includes(key))) return false;
  if (method !== 'GET' && url.search) return false;
  const route = url.pathname.replace(/^\/v1\/(?:platform\/)?/, '');
  const id = '[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}';
  if (['channels', 'provider-types', 'use-cases', 'credential-bindings', 'reconciliation-cases'].includes(route)) return method === 'GET';
  if (['provider-accounts', 'sender-identities', 'templates', 'use-case-bindings', 'routing-rules'].includes(route)) return ['GET', 'POST'].includes(method);
  if (['suppressions'].includes(route)) return ['GET', 'POST'].includes(method);
  if (route === 'consent-events') return method === 'POST';
  if (['deliveries', 'requests', 'provider-events', 'recipient-endpoints', 'consent-states'].includes(route)) return method === 'GET';
  if (/^channel-settings\/(email|sms|whatsapp|push)$/.test(route)) return method === 'PUT';
  if (route === 'effective-policy') return method === 'POST';
  if (new RegExp(`^(provider-accounts|sender-identities|templates|variants|routing-rules)/${id}$`, 'i').test(route)) return ['GET', 'PATCH'].includes(method);
  if (new RegExp(`^(template-versions|jobs|requests|deliveries|use-case-bindings|provider-events|recipient-endpoints)/${id}$`, 'i').test(route)) return method === 'GET';
  if (new RegExp(`^provider-accounts/${id}/callback-configuration$`, 'i').test(route)) return method === 'GET';
  if (new RegExp(`^provider-accounts/${id}/validate$|^sender-identities/${id}/(sync|verify)$|^bindings/${id}/sync$|^(use-case-bindings|activations)/${id}/end$|^suppressions/${id}/expire$|^deliveries/${id}/(retry|reconciliation)$|^variants/${id}/activate$|^template-versions/${id}/preview$`, 'i').test(route)) return method === 'POST';
  if (new RegExp(`^templates/${id}/variants$|^variants/${id}/(versions|activations)$|^template-versions/${id}/bindings$`, 'i').test(route)) return ['GET', 'POST'].includes(method);
  return method === 'GET' && new RegExp(`^deliveries/${id}/(attempts|events)$|^requests/${id}/outcomes$`, 'i').test(route);
}
