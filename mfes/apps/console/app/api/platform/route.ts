import type { NextRequest } from 'next/server';
import { allowedPlatformRequest } from '../../lib/platform-request';
import { proxyServiceRequest } from '../../lib/service-proxy';
import { serviceOrigin } from '../../lib/services';

/**
 * Platform administration, through the one proxy boundary (`lib/service-proxy`). Only the
 * allowlist and the single service it serves are this route's own.
 */
export async function POST(request: NextRequest) {
  return proxyServiceRequest(request, {
    allow: (service, method, path) => service === 'identity' && allowedPlatformRequest(method, path),
    subject: 'platform',
    base: serviceOrigin,
  });
}
