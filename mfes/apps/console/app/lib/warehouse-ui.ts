'use client';
import { useEffect, useRef, useState } from 'react';
import type { components } from '@janso/api-client/catalog';
import { assertMasterFields, masterRequest } from './catalog-master-api';
import type { MasterFieldSet } from './catalog-masters';
import { requestFailure, type RequestFailure } from './service-call';

export type WarehousePolicy = components['schemas']['OperationPolicyView'];
export type WarehousePreview = components['schemas']['OperationPolicyPreview'];
export type WarehouseConfiguration = components['schemas']['WarehouseConfigurationDetail'];
export const operationLabels = {
  allow_sale_issue: 'Allow sale from this store', allow_purchase_receipt: 'Allow purchase into this store',
  allow_transfer_in: 'Allow transfer in', allow_transfer_out: 'Allow transfer out',
  allow_customer_return_receipt: 'Allow customer returns', allow_supplier_return_issue: 'Allow supplier returns',
  allow_opening_stock: 'Allow opening stock', allow_adjustment: 'Allow adjustments',
} as const;
export const defaultLabels = {
  default_sale_warehouse_id: 'Default sale warehouse', default_purchase_warehouse_id: 'Default purchase warehouse',
  default_customer_return_warehouse_id: 'Default customer return warehouse', default_opening_warehouse_id: 'Default opening warehouse',
} as const;

export function useWarehouseRead<T>(company: string, path: string, entity: string, writing: boolean, warehouse?: string) {
  const [data, setData] = useState<T | null>(null), [fields, setFields] = useState<MasterFieldSet['fields']>([]), [loading, setLoading] = useState(true), [failure, setFailure] = useState<RequestFailure | null>(null), [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setData(null); setFields([]); setFailure(null);
    Promise.all([
      masterRequest<T>({ path, signal: controller.signal }),
      masterRequest<MasterFieldSet>({ path: `/v1/companies/${company}/entities/${entity}/field-set${writing ? '?operation=update' : ''}`, signal: controller.signal }),
    ]).then(([value, metadata]) => { if (!controller.signal.aborted) {
      const record = value as Record<string, unknown>;
      if (!record || (warehouse ? record.warehouse_id !== warehouse : record.company_id !== company)) throw { status: 502, message: 'The warehouse response did not match the open company and location. Reload before continuing.' };
      setFields(assertMasterFields(metadata, company, entity)); setData(value); setLoading(false);
    } })
      .catch(error => { if (!controller.signal.aborted) { setFailure(requestFailure(error, 'warehouse service')); setLoading(false); } });
    return () => controller.abort();
  }, [company, path, entity, writing, warehouse, revision]);
  return { data, fields, loading, failure, refresh: () => setRevision(value => value + 1) };
}

/** A lost response keeps the same payload/key available for deliberate recovery. */
export function useWarehouseCommand() {
  const busy = useRef(false), retry = useRef<{ payload: string; key: string } | null>(null);
  const [pending, setPending] = useState(false), [failure, setFailure] = useState<RequestFailure | null>(null);
  const uncertain = !!failure && failure.status >= 500;
  async function execute(path: string, body: unknown): Promise<boolean> {
    if (busy.current) return false;
    const payload = JSON.stringify({ path, body });
    if (uncertain && retry.current?.payload !== payload) return false;
    if (retry.current?.payload !== payload) retry.current = { payload, key: crypto.randomUUID() };
    busy.current = true; setPending(true); setFailure(null);
    try { await masterRequest({ path, method: 'POST', body, key: retry.current.key }); retry.current = null; return true; }
    catch (error) { setFailure(requestFailure(error, 'warehouse service')); return false; }
    finally { busy.current = false; setPending(false); }
  }
  return { execute, pending, failure, uncertain, clear: () => { if (!busy.current) { retry.current = null; setFailure(null); } } };
}
