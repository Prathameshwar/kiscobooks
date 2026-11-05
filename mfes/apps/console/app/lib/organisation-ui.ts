'use client';
import { useCallback, useEffect, useState } from 'react';
import type { SearchSelectLoader } from '@janso/ui';
import { accessCall, type AccessContext, type AccessPageData } from './access-directory';
import { requestFailure, type RequestFailure } from './service-call';

import { organisationBase, organisationPermission, type DepartmentRow, type OrganisationFields } from './organisation-contract';
export * from './organisation-contract';

export function useOrganisationFields(path: string, entity: string) {
  const [data, setData] = useState<OrganisationFields | null>(null), [loading, setLoading] = useState(true), [failure, setFailure] = useState<RequestFailure | null>(null), [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setFailure(null); setData(null);
    accessCall<OrganisationFields>({ path, signal: controller.signal }).then(result => {
      if (controller.signal.aborted) return;
      if (result?.entity_type !== entity || !Array.isArray(result.fields) || new Set(result.fields.map(field => field.key)).size !== result.fields.length) throw { status: 502, message: 'Unexpected form metadata. Reload before continuing.' };
      setData(result); setLoading(false);
    }).catch(error => { if (!controller.signal.aborted) { setFailure(requestFailure(error)); setLoading(false); } });
    return () => controller.abort();
  }, [path, entity, revision]);
  return { data, loading, failure, refresh: () => setRevision(value => value + 1) };
}
export function useDepartmentOptions(context: AccessContext, excludePath?: string): SearchSelectLoader {
  return useCallback(async ({ q, cursor, signal }) => {
    const params = new URLSearchParams({ limit: '50' }); if (q.trim().length >= 2) params.set('q', q.trim().slice(0, 20)); if (cursor) params.set('cursor', cursor);
    const result = await accessCall<AccessPageData<DepartmentRow>>({ path: organisationBase('departments', context) + '?' + params, signal });
    return { items: result.items.map(row => ({ id: row.id, label: row.name, meta: row.code, disabled: !row.is_active || !!excludePath && row.path.startsWith(excludePath) || !organisationPermission(context, 'departments', 'manage', row) })), nextCursor: result.page.has_more ? result.page.next_cursor : null };
  }, [context.companyId, context.grants, excludePath]);
}
