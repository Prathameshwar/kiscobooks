'use client';
import { serviceCall, type ServiceRequest } from './service-call';
import { downloadMasterImport } from './product-import';

export const partyImportRequest = <T>(request: ServiceRequest) =>
  serviceCall<T>(
    '/api/party-import',
    { ...request, service: 'accounting' },
    'party import',
  );
export const downloadPartyImport = (
  request: ServiceRequest,
  filename: string,
) => downloadMasterImport('/api/party-import', 'accounting', request, filename);

export { partyImportResources } from './party-import-resources';
