'use client';
import type { components } from '@janso/api-client/catalog';
import { masterRequest, assertMasterFields } from './catalog-master-api';
import { useServiceRead } from './service-resource';
import { taxUuid, type TaxConfig, type TaxContext, type TaxField, type TaxRow } from './tax-masters';

export const taxRequest = masterRequest;
export const taxBase = (company: string, resource: string) => `/v1/companies/${company}/${resource}`;
export function assertTaxRow(row: TaxRow, company: string, id?: string) {
  if (!row || !taxUuid.test(row.id) || row.company_id !== company || id && row.id !== id) throw { status: 502, message: 'The tax record could not be verified for this company. Reload before continuing.' };
}
export function assertTaxReceipt(row: TaxRow, id?: string) {
  if (!row || !taxUuid.test(row.id) || id && row.id !== id || !Number.isSafeInteger(row.row_version) || Number(row.row_version) < 1) throw { status: 502, message: 'The save result could not be verified. Retry the same request.' };
}
export function useTaxContext(company: string) {
  return useServiceRead<TaxContext>(taxBase(company, 'tax-administration'), taxRequest, value => {
    if (value.company_id !== company || !Number.isSafeInteger(value.policy_generation) || value.policy_generation < 1 || !Number.isSafeInteger(value.source_version) || value.source_version < 1) throw { status: 502, message: 'The current tax configuration could not be verified.' };
  }, 'tax service');
}
export function useTaxMetadata(company: string, config: TaxConfig, operation?: 'create' | 'update') {
  return useServiceRead<components['schemas']['FieldSet']>(taxBase(company, 'entities/' + config.entity + '/field-set') + (operation ? '?operation=' + operation : ''), taxRequest, value => { assertMasterFields(value, company, config.entity); }, 'tax field settings');
}
export function taxVisible(fields: TaxField[], key: string) { return fields.some(field => field.source === 'native' && field.visible && field.key === key); }
