import { sessionFetch } from './session-fetch';

export class ProductFieldError extends Error {
  constructor(message: string, public fields: Record<string,string> = {}, public status?: number) { super(message); }
}
export async function productFieldRequest<T>(service: 'identity' | 'catalog' | 'vouchers' | 'accounting' | 'reports', method: string, path: string, body?: unknown, key?: string, signal?: AbortSignal): Promise<T> {
  const replaySafe = method === 'GET' || (typeof key === 'string' && /^[a-zA-Z0-9_-]{1,128}$/.test(key));
  const response = await sessionFetch('/api/product-fields',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({service,method,path,body,key}),signal}, replaySafe);
  const value = await response.json();
  if (!response.ok) throw new ProductFieldError(value.error?.message ?? 'Unable to complete the action',value.error?.fields ?? {}, response.status);
  return value as T;
}
