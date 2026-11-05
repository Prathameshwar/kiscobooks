import { identityCall, readUpstream } from './local-auth-server';
import type { RegistrationErrors, RegistrationInput } from './registration-input';

/**
 * Sign-up for the local provider: Identity owns the credential from the first request
 * (docs/local-auth.md §4). Replaces the Authentik flow-executor `enroll()`; the route has already
 * validated the input, the region and any invitation, and rate-limited the caller.
 *
 * Returns `created: false` for a refusal the person can act on (field errors) or the generic
 * `registration_unavailable` (no existence leak). Anything else throws, which the route answers
 * with its generic 503. Identity's messages are never forwarded.
 */
export async function registerLocal(input: RegistrationInput, workspaceEnabled: boolean, clientAddress?: string): Promise<{ created: boolean; errors?: RegistrationErrors }> {
  // Explicit allowlist: nothing from the browser body reaches Identity except these fields, and
  // the confirmation field is a browser-side convenience that Identity does not take.
  const response = await identityCall('registrations', { method: 'POST', clientAddress, body: {
    name: input.name, username: input.username, email: input.email, password: input.password,
    country_code: input.country_code, state_code: input.state_code,
    // An empty name is meaningful: it is how an invited sign-up says it joins an existing workspace.
    ...(workspaceEnabled ? { workspace_name: input.workspace_name } : {}),
  } });
  if (response.status === 201) return { created: true };
  if (response.status !== 422) throw new Error('Registration unavailable');
  const upstream = await readUpstream(response);
  if (upstream.code === 'registration_unavailable') return { created: false };
  const errors: RegistrationErrors = {};
  for (const key of ['name', 'username', 'email', 'password', 'country_code', 'state_code', 'workspace_name'] as const) {
    if (upstream.fields.includes(key)) errors[key] = key === 'username' ? 'Choose another username. This one cannot be used.' :
      key === 'password' ? 'Check your password and confirmation.' : 'Check this account detail.';
  }
  if (!Object.keys(errors).length) throw new Error('Unexpected registration result');
  return { created: false, errors };
}
