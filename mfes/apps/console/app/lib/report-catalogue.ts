'use client';

import type { components } from '@janso/api-client/reports';
import { productFieldRequest } from './product-fields';
import { useServiceRead, type ServiceReader } from './service-resource';

type Catalogue = components['schemas']['DefinitionCatalog'];
const reader: ServiceReader = request => productFieldRequest('reports', request.method ?? 'GET', request.path, request.body, request.key, request.signal);

export function useReportCatalogue(company: string) {
  return useServiceRead<Catalogue>('/v2/companies/' + encodeURIComponent(company) + '/report-definitions', reader, value => {
    if (!value || !Array.isArray(value.items) || value.items.length > 200) throw { status: 502, message: 'Report availability could not be verified.' };
    const seen = new Set<string>();
    for (const item of value.items) {
      const code = item?.definition?.code, version = item?.definition?.version;
      if (typeof code !== 'string' || !/^[A-Z][A-Z0-9_]{0,63}$/.test(code) || seen.has(code) || !Number.isSafeInteger(version) || version < 1 || typeof item.run_enabled !== 'boolean') throw { status: 502, message: 'Report availability could not be verified.' };
      seen.add(code);
    }
  }, 'report availability');
}
