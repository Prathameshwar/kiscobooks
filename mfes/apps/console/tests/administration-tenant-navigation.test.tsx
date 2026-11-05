import { screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { TenantDetail } from '../app/platform/tenants/TenantDetail';
import { TenantForm } from '../app/platform/tenants/TenantForm';
import { platformCall } from '../app/lib/platform-api';
import { renderWithProviders } from './helpers';
import { companyId } from './access-fixtures';
vi.mock('../app/lib/platform-api', async original => ({ ...await original<object>(), platformCall: vi.fn() }));
vi.mock('../app/lib/navigate', () => ({ goTo: vi.fn(), signInUrl: () => 'http://localhost:4310/login' }));
const detail = { id: companyId, name: 'Acme workspace', slug: 'acme', status: 'active', primary_contact_email: 'ava@example.com', default_country_code: 'IN', default_state_code: null, default_currency_code: 'INR', default_timezone: 'UTC', default_locale: 'en', created_at: '2026-10-24T10:00:00Z', updated_at: '2026-10-24T10:00:00Z' };
const directory = '/platform/tenants?q=Ac', origin = '/platform/tenants/' + companyId + '?returnTo=' + encodeURIComponent(directory);
beforeEach(() => {
  vi.mocked(platformCall).mockReset();
  vi.mocked(platformCall).mockImplementation(async path => path.includes('tenant-options') ? { countries: [{ code: 'IN', name: 'India' }], states: [], currencies: [{ code: 'INR', name: 'Rupee' }], timezones: [{ code: 'UTC', name: 'UTC' }], languages: [{ code: 'en', name: 'English' }] } : detail);
});
it('retains the tenant detail and directory context when opening its editor', async () => {
  await renderWithProviders(<TenantDetail tenantId={companyId} returnTo={directory} permissions={['platform.tenant.read', 'platform.config.manage']} />);
  const edit = await screen.findByRole('link', { name: 'Edit details' });
  expect(new URL(edit.getAttribute('href')!, 'https://console.invalid').searchParams.get('returnTo')).toBe(origin);
});
it('returns a tenant edit direct visit to the provided detail', async () => {
  await renderWithProviders(<TenantForm scope={companyId} tenantId={companyId} returnTo={origin} />);
  expect(screen.getByRole('link', { name: 'Back to tenant details' })).toHaveAttribute('href', origin);
});
