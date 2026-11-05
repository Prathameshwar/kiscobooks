import { allowedMasterImportRequest } from './product-import-policy';
import { partyImportResources } from './party-import-resources';
export function allowedPartyImportRequest(
  service: string,
  method: string,
  path: string,
): boolean {
  return allowedMasterImportRequest(
    service,
    method,
    path,
    'accounting',
    partyImportResources.map((resource) => resource.value),
    ['CREATE', 'UPDATE', 'ACTIVATE', 'DEACTIVATE'],
  );
}
