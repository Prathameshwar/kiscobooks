import type { components } from '@janso/api-client/identity';
import type { RegistrationErrors } from './registration-input';

export type RegistrationChoices = components['schemas']['RegistrationChoices'];
export type RegistrationRegion = { country_code: string; state_code: string };

/** Profile metadata supplies editable defaults, never permissions or verification. */
export function parseRegion(value: unknown): RegistrationRegion | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const region = value as Record<string, unknown>;
  if (typeof region.country_code !== 'string' || !/^[A-Z]{2}$/.test(region.country_code) ||
      typeof region.state_code !== 'string' || (region.state_code !== '' && !/^[A-Z]{2}-[A-Z0-9]{1,3}$/.test(region.state_code))) return null;
  return { country_code: region.country_code, state_code: region.state_code };
}

/** Reject incomplete or malformed catalogues instead of rendering guessed choices. */
export function parseChoices(value: unknown): RegistrationChoices | null {
  if (!value || typeof value !== 'object') return null;
  const data = value as RegistrationChoices;
  if (!Array.isArray(data.countries) || !data.countries.length || data.countries.length > 1000 ||
      !Array.isArray(data.states) || data.states.length > 10000) return null;
  if (!data.countries.every(item => item && typeof item.code === 'string' && /^[A-Z]{2}$/.test(item.code) &&
      typeof item.name === 'string' && item.name.length > 0 && item.name.length <= 200) ||
      new Set(data.countries.map(item => item.code)).size !== data.countries.length) return null;
  const countries = new Set(data.countries.map(item => item.code));
  if (!data.states.every(item => item && typeof item.code === 'string' && /^[A-Z]{2}-[A-Z0-9]{1,3}$/.test(item.code) &&
      countries.has(item.country_code) && item.code.startsWith(item.country_code + '-') &&
      typeof item.name === 'string' && item.name.length > 0 && item.name.length <= 200) ||
      new Set(data.states.map(item => item.code)).size !== data.states.length) return null;
  return { countries: data.countries.map(({ code, name }) => ({ code, name })),
    states: data.states.map(({ code, name, country_code }) => ({ code, name, country_code })) };
}

export function regionErrors(region: RegistrationRegion, options: RegistrationChoices): RegistrationErrors {
  if (!options.countries.some(item => item.code === region.country_code)) return { country_code: 'Choose an available country.' };
  const states = options.states.filter(item => item.country_code === region.country_code);
  if ((states.length > 0 || region.state_code !== '') && !states.some(item => item.code === region.state_code)) {
    return { state_code: 'Choose an available state for this country.' };
  }
  return {};
}
