import type { NextRequest } from 'next/server';
import { allowedPartyImportRequest } from '../../lib/party-import-policy';
import { masterImportProxy } from '../../lib/master-import-proxy';
export function POST(request: NextRequest) {
  return masterImportProxy(request, allowedPartyImportRequest, 'party import');
}
