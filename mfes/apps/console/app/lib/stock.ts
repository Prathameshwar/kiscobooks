'use client';
import type { components } from '@janso/api-client/accounting';
import { serviceCall, type ServiceRequest } from './service-call';
import { useServiceRead } from './service-resource';
import { trackingId } from './stock-tracking-resources';

export type StockView = 'cost-pools' | 'positions' | 'movements' | 'account-policies';
export type StockRow = components['schemas']['StockCostPoolListItem'] & components['schemas']['StockPositionListItem'] & components['schemas']['StockMovementListItem'];
export type StockFields = components['schemas']['FieldSet'];
export type StockConfiguration = components['schemas']['StockConfiguration'];
export const stockBase = (company: string) => `/v1/companies/${company}/stock`;
export const stockRequest = <T>(request: ServiceRequest) => serviceCall<T>('/api/product-fields', { ...request, service: 'accounting' }, 'stock service');
export function useStockFields(company: string, view: StockView) {
  return useServiceRead<StockFields>(stockBase(company) + '/' + view + '/field-set', stockRequest, value => {
    const expected = { 'cost-pools': 'stock-cost-pools', positions: 'stock-positions', movements: 'stock-movements', 'account-policies': 'stock-account-policies' }[view];
    if (value.resource !== expected || !Array.isArray(value.fields)) throw { status: 502, message: 'Stock field permissions could not be verified.' };
  });
}
export function verifyStockRow(row: { id: string }) {
  if (!trackingId.test(row.id)) throw { status: 502, message: 'The stock record could not be verified.' };
}
