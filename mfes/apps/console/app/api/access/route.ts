import type { NextRequest } from 'next/server';
import { allowedAccessRequest } from '../../lib/access-request-policy';
import { proxyServiceRequest } from '../../lib/service-proxy';
import { serviceOrigin } from '../../lib/services';

export async function POST(request: NextRequest) {
  return proxyServiceRequest(request, { allow: allowedAccessRequest, base: serviceOrigin, subject: 'access management' });
}
