import type { NextRequest } from 'next/server';
import { allowedNotificationRequest } from '../../lib/notification-request-policy';
import { proxyServiceRequest } from '../../lib/service-proxy';
import { serviceOrigin } from '../../lib/services';

export async function POST(request: NextRequest) {
  return proxyServiceRequest(request, { allow: allowedNotificationRequest, base: serviceOrigin, subject: 'notification' });
}
