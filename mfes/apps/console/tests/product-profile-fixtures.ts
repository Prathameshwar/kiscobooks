import native from './product-profile-fields.json';
import type { MasterField, MasterRow } from '../app/lib/catalog-masters';
import type { ServiceRequest } from '../app/lib/service-call';
import { profileDefaults } from '../app/lib/product-profile-resources';
import {
  profileDefinitions,
  type ProductProfileResource,
} from '../app/lib/product-profile-resources';
export {
  COMPANY,
  RECORD,
  SOURCE,
  FRESH,
  page,
} from './units-identifiers-fixtures';
import {
  COMPANY,
  RECORD,
  SOURCE,
  FRESH,
  page,
} from './units-identifiers-fixtures';
export const access = {
  'inventory-templates': true,
  'warranty-policies': true,
  'return-policies': true,
  'handling-profiles': true,
  identifiers: true,
  publish: true,
};
export const fields = (entity: string, operation = 'read'): MasterField[] =>
  structuredClone(
    (native as Record<string, MasterField[]>)[
      entity.replace('catalog.', '') + ':' + operation
    ] ?? [],
  );
export const master = (id = RECORD): MasterRow => ({
  id,
  company_id: COMPANY,
  code: 'STANDARD',
  name: 'Standard profile',
  is_active: true,
  row_version: 4,
});
export const revision = (
  resource: ProductProfileResource,
  id = SOURCE,
): MasterRow => ({
  id,
  company_id: COMPANY,
  [profileDefinitions[resource].parent]: RECORD,
  revision: 1,
  row_version: 4,
  published_at: null,
  ...Object.fromEntries(
    Object.entries(profileDefaults[resource]).filter(
      ([key]) => key !== 'condition_codes' && key !== 'steps',
    ),
  ),
  ...(resource === 'manufacturing-routes'
    ? {
        status: 'DRAFT',
        step_count: 1,
        specification: 'Cut then pack.',
        change_reason: 'Initial route',
      }
    : resource === 'manufacturing-operations'
      ? {
          status: 'DRAFT',
          specification: 'Cut to the approved dimensions.',
          change_reason: 'Initial definition',
        }
      : resource === 'warranty-policies'
        ? { duration: 12 }
        : resource === 'return-policies'
          ? { returns_allowed: true, window_days: 30, condition_count: 2 }
          : {}),
});
const records = new Map<string, MasterRow>(),
  members = new Map<string, string[]>();
export const resetFixtures = () => {
  records.clear();
  members.clear();
};
export function response(request: ServiceRequest): unknown {
  const url = new URL(request.path, 'https://api.invalid'),
    parts = url.pathname.split('/'),
    resource = parts[4] as ProductProfileResource,
    id = parts[5],
    revisionId = parts[7],
    action = parts[8],
    method = request.method ?? 'GET',
    body = (request.body as Record<string, unknown>) ?? {};
  if ((resource as string) === 'entities')
    return {
      company_id: COMPANY,
      entity_type: id,
      fields: fields(id!, url.searchParams.get('operation') ?? 'read'),
    };
  if ((resource as string) === 'identifier-profiles')
    return id
      ? { ...master(id), name: 'Phone identifiers', normalization_version: 1 }
      : {
          items: [
            {
              ...master(SOURCE),
              name: 'Phone identifiers',
              normalization_version: 1,
            },
          ],
          page,
        };
  const revisions = parts[6] === 'revisions',
    targetId = revisions ? (revisionId ?? FRESH) : (id ?? FRESH),
    key = resource + ':' + targetId,
    original =
      records.get(key) ??
      (revisions ? revision(resource, targetId) : master(targetId));
  if (method !== 'GET') {
    const result: MasterRow = {
      ...original,
      ...body,
      row_version:
        method === 'PATCH' || action || parts[6]
          ? Number(body.expected_version ?? 4) + 1
          : 1,
      ...(revisions
        ? { [profileDefinitions[resource].parent]: id }
        : parts[6]
          ? { is_active: parts[6] === 'activate' }
          : {}),
      ...(action === 'publish' ? { published_at: '2026-10-25T10:00:00Z' } : {}),
      ...(['manufacturing-operations', 'manufacturing-routes'].includes(
        resource,
      ) && action === 'publish'
        ? { status: 'PUBLISHED' }
        : {}),
      ...(['manufacturing-operations', 'manufacturing-routes'].includes(
        resource,
      ) && action === 'retire'
        ? { status: 'RETIRED' }
        : {}),
    };
    if (resource === 'manufacturing-routes' && Array.isArray(body.steps))
      result.step_count = body.steps.length;
    delete result.steps;
    delete result.expected_version;
    if (revisions && resource === 'return-policies') {
      const selected = body.condition_codes as string[] | undefined;
      if (selected) members.set(targetId, selected);
      result.condition_count =
        members.get(targetId)?.length ?? Number(original.condition_count);
      delete result.condition_codes;
    }
    records.set(key, result);
    return result;
  }
  if (action === 'conditions')
    return {
      items: (members.get(targetId) ?? ['UNUSED', 'UNDAMAGED']).map(
        (condition_code, index) => ({
          id: index ? FRESH : RECORD,
          revision_id: revisionId,
          condition_code,
        }),
      ),
      page: { ...page, limit: Number(url.searchParams.get('limit') ?? 25) },
    };
  if (revisions && !revisionId)
    return {
      items: [revision(resource)],
      page: { ...page, limit: Number(url.searchParams.get('limit') ?? 25) },
    };
  if (id) return original;
  return {
    items: [master()],
    page: { ...page, limit: Number(url.searchParams.get('limit') ?? 25) },
  };
}
