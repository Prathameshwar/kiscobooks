import { identityFetch } from '../identity-session';

/** Read the company's country through the actor's normal Identity authorization. */
export async function partyCompanyCountry(company: string): Promise<string> {
  const response = await identityFetch(`/v1/companies/${company}`);
  if (!response.ok) return 'IN';
  const value: unknown = await response.json().catch(() => null);
  if (value && typeof value === 'object' && 'country_code' in value &&
      typeof value.country_code === 'string' && /^[A-Z]{2}$/.test(value.country_code))
    return value.country_code;
  return 'IN';
}
