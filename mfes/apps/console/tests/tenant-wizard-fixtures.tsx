import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ThemeProvider } from '@janso/ui';
import { TenantForm } from '../app/platform/tenants/TenantForm';

export const tenantId = '01900000-0000-7000-8000-000000000001';
export const tenantDetail = { id: tenantId, name: 'Acme Books', slug: 'acme-books', status: 'active', primary_contact_email: 'owner@example.invalid', default_country_code: 'IN', default_currency_code: 'INR', default_timezone: 'Asia/Kolkata', default_locale: 'en' };
export const tenantCreated = { ...tenantDetail, administrator_username: 'bill-admin-new', administrator_password: 'generated-temporary-password', administrator_mode: 'new', sign_in_url: 'http://localhost:4310/login', notification_status: 'manual' };
export const tenantChoices = { countries: [{ code: 'IN', name: 'India' }], states: [{ code: 'IN-MH', name: 'Maharashtra', country_code: 'IN' }], currencies: [{ code: 'INR', name: 'Indian rupee' }], timezones: [{ code: 'Asia/Kolkata', name: 'Asia/Kolkata' }, { code: 'UTC', name: 'UTC' }], languages: [{ code: 'en', name: 'English' }, { code: 'hi', name: 'Hindi' }] };

export function renderTenant(props: { tenantId?: string; returnTo?: string } = {}) {
  return render(<ThemeProvider initial="light"><TenantForm scope="operator" {...props} /></ThemeProvider>);
}
export async function fillTenant() {
  fireEvent.change(await screen.findByRole('textbox', { name: 'Tenant name' }), { target: { value: 'New Books' } });
  fireEvent.change(screen.getByRole('combobox', { name: 'State' }), { target: { value: 'IN-MH' } });
  await userEvent.click(screen.getByRole('button', { name: 'Next' }));
  await screen.findByRole('heading', { level: 1, name: 'Administrator' });
}
export function fillAdministrator() {
  fireEvent.change(screen.getByRole('textbox', { name: 'Administrator full name' }), { target: { value: 'New Owner' } });
  fireEvent.change(screen.getByRole('textbox', { name: 'Administrator email' }), { target: { value: 'new@example.invalid' } });
  fireEvent.click(screen.getByRole('checkbox', { name: /I confirm this person controls/ }));
}
export async function reachTenantReview() {
  await fillTenant(); fillAdministrator();
  await userEvent.click(screen.getByRole('button', { name: 'Next' }));
  await screen.findByRole('heading', { level: 1, name: 'Review & create' });
}
