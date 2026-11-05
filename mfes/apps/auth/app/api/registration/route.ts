import { NextRequest, NextResponse } from 'next/server';
import { initialWorkspaceName, parseRegistration, registrationErrors } from '../../lib/registration-input';
import { allowRegistration, boundedJson, enroll, registrationConfiguration } from '../../lib/registration-server';
import { invitationAvailable, registrationChoices } from '../../lib/registration-regions-server';
import { regionErrors } from '../../lib/registration-regions';
import { registerLocal } from '../../lib/local-registration';
import { clientAddress } from '../../lib/local-auth-server';

export const runtime = 'nodejs';
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const reply = (value: unknown, status = 200) => NextResponse.json(value, { status, headers: {
  'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer', 'X-Content-Type-Options': 'nosniff',
  ...(status === 429 ? { 'Retry-After': '60' } : {}) } });
// Public intentionally: availability and active global regions, never an account lookup.
export async function GET() {
  let configuration;
  try { configuration = registrationConfiguration(); }
  catch { return reply({ enabled: false }); }
  try { return reply({ enabled: true, mode: 'manual-review', workspace_enabled: configuration.workspaceEnabled, options: await registrationChoices(),
    // Let signup explain both identifiers accepted by the local provider.
    ...(configuration.provider === 'local' ? { sign_in: 'username_or_email' } : {}) }); }
  catch { return reply({ enabled: false, error: 'Regional choices are temporarily unavailable. Please try again.' }, 503); }
}
// Public intentionally: creates an inactive provider account; cannot assign billing membership.
export async function POST(request: NextRequest) {
  try {
    const configuration = registrationConfiguration();
    if (request.headers.get('origin') !== configuration.origin ||
        request.headers.get('sec-fetch-site') === 'cross-site') return reply({ error: 'Request is not allowed.' }, 403);
    if (!/^application\/json(?:\s*;|$)/i.test(request.headers.get('content-type') ?? '')) return reply({ error: 'Send account details as JSON.' }, 415);
    if (Number(request.headers.get('content-length') ?? 0) > 8192) return reply({ error: 'Account details are too large.' }, 413);
    if (!await allowRegistration()) return reply({ error: 'Too many attempts. Please wait a minute and try again.' }, 429);
    let value: unknown;
    try { value = await boundedJson(new Response(request.body, { headers: request.headers }), 8192); }
    catch { return reply({ error: 'Account details are invalid or too large.' }, 400); }
    const body = value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : null;
    const inviteTenant = body?.invitation_tenant, inviteId = body?.invitation_id;
    const invited = configuration.workspaceEnabled && inviteTenant !== undefined && inviteId !== undefined;
    if (invited && (typeof inviteTenant !== 'string' || typeof inviteId !== 'string' || !uuid.test(inviteTenant) || !uuid.test(inviteId)))
      return reply({ error: 'Invitation details are invalid.' }, 422);
    const account = invited ? Object.fromEntries(Object.entries(body!).filter(([key]) => key !== 'invitation_tenant' && key !== 'invitation_id')) : value;
    const input = parseRegistration(account, configuration.workspaceEnabled);
    if (!input) return reply({ error: 'Send only the required account details.' }, 422);
    const errors = registrationErrors(input);
    if (Object.keys(errors).length) return reply({ error: 'Please check the highlighted fields.', fields: errors }, 422);
    const regionalErrors = regionErrors(input, await registrationChoices());
    if (Object.keys(regionalErrors).length) return reply({ error: 'Please check the highlighted fields.', fields: regionalErrors }, 422);
    if (configuration.workspaceEnabled) {
      if (invited) {
        if (input.workspace_name || !await invitationAvailable(inviteTenant as string, inviteId as string, input.email))
          return reply({ error: 'This invitation is unavailable or does not match this email.' }, 422);
      } else input.workspace_name = initialWorkspaceName(input.email);
    }
    const result = configuration.provider === 'local' ? await registerLocal(input, configuration.workspaceEnabled, clientAddress(request)) : await enroll(input);
    if (!result.created) return reply({ error: 'These account details cannot be used. Check the fields or contact your administrator.', fields: result.errors }, 422);
    return reply({ created: true, status: 'pending-review' }, 201);
  } catch { return reply({ error: 'Account creation is temporarily unavailable. Please try again later.' }, 503); }
}
