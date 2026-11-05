import type { NextRequest } from 'next/server';
import { allowedProductImportRequest } from '../../lib/product-import-policy';
import { masterImportProxy } from '../../lib/master-import-proxy';
export function POST(request: NextRequest) {
  return masterImportProxy(
    request,
    allowedProductImportRequest,
    'product import',
    65000,
  );
}
