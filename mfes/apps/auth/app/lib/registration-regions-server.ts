import { boundedJson } from './registration-server';
import { parseChoices, type RegistrationChoices } from './registration-regions';

export async function registrationChoices(): Promise<RegistrationChoices> {
  const base = new URL(process.env.IDENTITY_URL ?? '');
  if (!['https:', 'http:'].includes(base.protocol) || base.username || base.password || base.search || base.hash ||
      (base.protocol === 'http:' && !['localhost', '127.0.0.1', '[::1]'].includes(base.hostname))) throw new Error('Invalid regional endpoint');
  // Fixed server-configured destination and no caller cookies/credentials forwarded.
  const response = await fetch(new URL('/v1/registration/options', base), {
    cache: 'no-store', redirect: 'error', signal: AbortSignal.timeout(5000), headers: { Accept: 'application/json' },
  });
  if (!response.ok) throw new Error('Regional choices unavailable');
  const options = parseChoices(await boundedJson(response, 2 * 1024 * 1024));
  if (!options) throw new Error('Regional choices unavailable');
  return options;
}

export async function invitationAvailable(tenant: string, invitation: string, email: string): Promise<boolean> {
  const base = new URL(process.env.IDENTITY_URL ?? '');
  if (!['https:', 'http:'].includes(base.protocol) || base.username || base.password || base.search || base.hash ||
      (base.protocol === 'http:' && !['localhost', '127.0.0.1', '[::1]'].includes(base.hostname))) throw new Error('Invalid invitation endpoint');
  const url = new URL('/v1/registration/invitation', base);
  url.search = new URLSearchParams({ tenant, invitation, email }).toString();
  const response = await fetch(url, { cache: 'no-store', redirect: 'error', signal: AbortSignal.timeout(5000), headers: { Accept: 'application/json' } });
  if (!response.ok) throw new Error('Invitation check unavailable');
  const result = await boundedJson(response, 4096) as { available?: unknown };
  return result?.available === true;
}
