'use client';
import { useCallback, useEffect, useState } from 'react';
import type { PageMeta, SearchSelectLoader } from '@janso/ui';
import { serviceCall, requestFailure, type RequestFailure, type ServiceRequest } from './service-call';
import type { MasterConfig, MasterFieldSet, MasterRow } from './catalog-masters';

export type MasterPage = { items: MasterRow[]; page: PageMeta };
export async function masterRequest<T>(request: ServiceRequest): Promise<T> {
  const retryable = (request.service ?? 'catalog') === 'catalog' && request.method === 'POST'
    && !!request.key && /^\/v1\/companies\/[^/]+\/(products|product-families)$/.test(request.path);
  for (let attempt = 0; ; attempt++) {
    request.signal?.throwIfAborted();
    try {
      return await serviceCall<T>('/api/product-fields', { service: 'catalog', ...request }, 'master service');
    } catch (error) {
      const failure = requestFailure(error);
      if (!retryable || attempt >= 2 || failure.status !== 409
        || failure.message !== 'request is busy; retry with the same idempotency key') throw error;
      await new Promise<void>((resolve, reject) => {
        const cancel = () => { clearTimeout(timer); reject(request.signal?.reason); };
        const timer = setTimeout(() => { request.signal?.removeEventListener('abort', cancel); resolve(); }, attempt ? 750 : 250);
        request.signal?.addEventListener('abort', cancel, { once: true });
        if (request.signal?.aborted) cancel();
      });
    }
  }
}
export const masterBase = (company: string, config: MasterConfig) => `/v1/companies/${company}/${config.resource}`;
export function assertMasterFields(metadata: MasterFieldSet, company: string, entity: string) {
  if (metadata.company_id !== company || metadata.entity_type !== entity || !Array.isArray(metadata.fields)) throw { status: 502, message: 'Field settings are unavailable for this company. Retry loading.' };
  return metadata.fields;
}
export function assertMaster(row: MasterRow, company: string, id?: string) {
  if (!row?.id || row.company_id !== company || (id && row.id !== id)) throw { status: 502, message: 'The record response did not match this company. Reload before continuing.' };
  return row;
}
export function useMasterRecord(company: string, config: MasterConfig, id: string | undefined, editing: boolean) {
  const [fields, setFields] = useState<MasterFieldSet['fields']>([]), [row, setRow] = useState<MasterRow | null>(null);
  const [loading, setLoading] = useState(true), [failure, setFailure] = useState<RequestFailure | null>(null), [revision, setRevision] = useState(0);
  const refresh = () => setRevision(value => value + 1);
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setFailure(null); setFields([]); setRow(null);
    Promise.all([
      masterRequest<MasterFieldSet>({ path: `/v1/companies/${company}/entities/${config.entity}/field-set` + (editing ? '?operation=' + (id ? 'update' : 'create') : ''), signal: controller.signal }),
      id ? masterRequest<MasterRow>({ path: masterBase(company, config) + '/' + id, signal: controller.signal }) : Promise.resolve(null),
    ]).then(([metadata, record]) => {
      if (controller.signal.aborted) return;
      setFields(assertMasterFields(metadata, company, config.entity)); setRow(record ? assertMaster(record, company, id) : null); setLoading(false);
    }).catch(error => { if (!controller.signal.aborted) { setFailure(requestFailure(error, 'master service')); setLoading(false); } });
    return () => controller.abort();
  }, [company, config, id, editing, revision]);
  return { fields, row, setRow, loading, failure, refresh, revision };
}
export function useMasterLookup(company: string, resource: 'item-groups' | 'parties') {
  return useCallback<SearchSelectLoader>(async ({ q, cursor, signal }) => {
    const query = new URLSearchParams({ limit: '50', ...(resource === 'parties' ? { status: 'ACTIVE' } : { is_active: 'true' }) });
    if (q.trim().length >= 2) query.set('q', q.trim());
    if (cursor) query.set('cursor', cursor);
    const page = await masterRequest<MasterPage>({ service: resource === 'parties' ? 'accounting' : 'catalog', path: `/v1/companies/${company}/${resource}?${query}`, signal });
    return { items: page.items.map(row => ({ id: row.id, label: row.name ?? row.code ?? 'Record', meta: row.code })), nextCursor: page.page.has_more ? page.page.next_cursor : null };
  }, [company, resource]);
}
