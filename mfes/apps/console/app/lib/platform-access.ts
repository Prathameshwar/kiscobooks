import type { components } from '@janso/api-client/identity';
import { platformCall } from './platform-api';
import type { ServiceReader } from './service-resource';

export type Administrator = components['schemas']['PlatformAdministrator'];
export type AdministratorItem = components['schemas']['AdministratorListItem'];
export type AdministratorTenant = components['schemas']['AdministratorTenant'];
export type AdministratorRole =
  components['schemas']['PlatformAdministratorRole'];
export type AdministratorReceipt =
  components['schemas']['AdministratorReceipt'];
export type AdministratorCommand =
  components['schemas']['AdministratorCommand'];
export type AdministratorPage =
  components['schemas']['Page_AdministratorListItem_'];
export type TenantPage = components['schemas']['Page_AdministratorTenant_'];
export const platformAccessReader: ServiceReader = (request) =>
  platformCall(
    request.path,
    request.method,
    request.body,
    request.key,
    request.signal,
  );
export const administratorRoot = '/platform/access/administrators';
export const uuidPattern = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
export function administratorPath(tenant: string, user?: string) {
  return (
    '/v1/platform/access/tenants/' +
    tenant +
    '/administrators' +
    (user ? '/' + user : '')
  );
}
export function administratorReturn(
  value?: string | null,
  tenant?: string,
): string {
  const fallback =
    administratorRoot +
    (tenant && uuidPattern.test(tenant) ? '?tenant=' + tenant : '');
  if (!value || value.length > 3000 || /[\\\r\n]/.test(value)) return fallback;
  try {
    const url = new URL(value, 'https://console.invalid'),
      keys = [...url.searchParams.keys()];
    if (
      url.origin !== 'https://console.invalid' ||
      url.pathname !== administratorRoot ||
      url.hash ||
      new Set(keys).size !== keys.length ||
      keys.some(
        (key) =>
          !['tenant', 'q', 'status', 'sort', 'limit', 'cursor'].includes(key),
      )
    )
      return fallback;
    const selected = url.searchParams.get('tenant');
    if (
      !selected ||
      !uuidPattern.test(selected) ||
      (tenant && selected !== tenant)
    )
      return fallback;
    return url.pathname + url.search;
  } catch {
    return fallback;
  }
}
export function administratorLink(path: string, tenant: string, back?: string) {
  const query = new URLSearchParams({ tenant });
  if (back) query.set('returnTo', administratorReturn(back, tenant));
  return path + '?' + query;
}
export function verifyAdministrator(
  value: Administrator,
  tenant: string,
  user: string,
) {
  if (
    value.id !== user ||
    value.tenant?.id !== tenant ||
    !uuidPattern.test(value.assignment_id) ||
    !value.updated_at ||
    !value.assignment_updated_at
  )
    throw {
      status: 502,
      message:
        'Administrator details could not be verified. Refresh and try again.',
    };
}
export function verifyReceipt(
  value: AdministratorReceipt,
  tenant: string,
  user?: string,
) {
  if (
    value.tenant_id !== tenant ||
    !uuidPattern.test(value.administrator_id) ||
    (user && value.administrator_id !== user) ||
    !uuidPattern.test(value.assignment_id) ||
    !value.updated_at ||
    !value.assignment_updated_at
  )
    throw {
      status: 502,
      message:
        'The administrator change could not be confirmed. Retry the same request.',
    };
  if (value.invitation_url) {
    const url = new URL(value.invitation_url);
    if (
      !['http:', 'https:'].includes(url.protocol) ||
      url.username ||
      url.password ||
      url.searchParams.get('tenant') !== tenant ||
      url.searchParams.get('invitation') !== value.invitation_id
    )
      throw {
        status: 502,
        message: 'The invitation link could not be verified.',
      };
  }
}
