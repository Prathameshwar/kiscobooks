/** Shared browser/server validation; credentials are never persisted by this application. */
export const MIN_PASSWORD_LENGTH = 6;
export const MAX_PASSWORD_LENGTH = 128;
export type RegistrationInput = { name: string; username: string; email: string; password: string; password_repeat: string; country_code: string; state_code: string; workspace_name: string };
export type RegistrationErrors = Partial<Record<keyof RegistrationInput, string>>;
export function initialWorkspaceName(email: string): string {
  const local = Array.from(email.split('@')[0].split('+')[0].replace(/[^\p{L}\p{N}]+/gu, ' ').trim()).slice(0, 160).join('');
  const label = local ? local.replace(/(^|\s)\p{L}/gu, value => value.toLocaleUpperCase('en')) : 'My';
  return `${Array.from(label).slice(0, 180).join('')} Workspace`;
}
/** The one password rule: 6–128 Unicode code points, no control characters. Strength is advice only. */
export function passwordAcceptable(password: string): boolean {
  const length = Array.from(password).length;
  return length >= MIN_PASSWORD_LENGTH && length <= MAX_PASSWORD_LENGTH && !/[\x00-\x1f\x7f]/.test(password);
}
export const PASSWORD_RULE_MESSAGE = `Use ${MIN_PASSWORD_LENGTH}–${MAX_PASSWORD_LENGTH} characters. A long, unique passphrase works well.`;
export function registrationErrors(value: RegistrationInput): RegistrationErrors {
  const errors: RegistrationErrors = {};
  if (!value.name.trim() || value.name.trim().length > 100 || /[\x00-\x1f\x7f]/.test(value.name)) errors.name = 'Enter your full name (up to 100 characters).';
  if (!/^[a-z0-9][a-z0-9._-]{2,63}$/.test(value.username)) errors.username = 'Use 3–64 lowercase letters, numbers, dots, hyphens or underscores.';
  if (value.email.length > 254 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.email)) errors.email = 'Enter a valid email address.';
  if (!passwordAcceptable(value.password)) errors.password = PASSWORD_RULE_MESSAGE;
  if (value.password_repeat !== value.password) errors.password_repeat = 'Passwords must match.';
  if (!/^[A-Z]{2}$/.test(value.country_code)) errors.country_code = 'Choose a country.';
  if (value.state_code && !/^[A-Z]{2}-[A-Z0-9]{1,3}$/.test(value.state_code)) errors.state_code = 'Choose a valid state.';
  if (value.workspace_name.length > 200 || /[\x00-\x1f\x7f]/.test(value.workspace_name)) errors.workspace_name = 'Enter a workspace name with up to 200 characters.';
  return errors;
}
export function parseRegistration(value: unknown, workspaceEnabled = true): RegistrationInput | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const body = value as Record<string, unknown>;
  const keys = ['name', 'username', 'email', 'password', 'password_repeat', 'country_code', 'state_code'];
  if (!keys.every(key => typeof body[key] === 'string') || Object.keys(body).some(key => !keys.includes(key) && !(workspaceEnabled && key === 'workspace_name')) ||
      (body.workspace_name !== undefined && typeof body.workspace_name !== 'string')) return null;
  return { name: (body.name as string).trim(), username: (body.username as string).trim().toLowerCase(),
    email: (body.email as string).trim().toLowerCase(), password: body.password as string, password_repeat: body.password_repeat as string,
    country_code: body.country_code as string, state_code: body.state_code as string, workspace_name: workspaceEnabled ? ((body.workspace_name as string | undefined) ?? '').trim() : '' };
}
