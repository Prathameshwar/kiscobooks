import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { DisplayConfigProvider } from '@janso/ui';
import { ProductConfigurationEditor } from '../app/components/ProductConfigurationEditor';
import { ProductConfigurationDetail } from '../app/components/ProductConfigurationDetail';
import { serviceCall } from '../app/lib/service-call';
import { COMPANY, DRAFT } from './product-configuration-fixtures';
import { completeResponse } from './product-configuration-layout-fixtures';

vi.mock('../app/lib/service-call', async original => ({ ...await original<typeof import('../app/lib/service-call')>(), serviceCall: vi.fn() }));
vi.mock('../app/lib/navigate', () => ({ goTo: vi.fn(), signInUrl: () => '/signin' }));
beforeEach(() => { vi.clearAllMocks(); vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => completeResponse(request.path, request.method) as never); });
const editor = () => render(<DisplayConfigProvider config={{ timezone: 'Asia/Kolkata', currency: 'INR' }}><ProductConfigurationEditor company={COMPANY} id={DRAFT} timezone="Asia/Kolkata" returnTo="/settings" /></DisplayConfigProvider>);

it('groups conversion separately, saves Model independently and clears its obsolete default', async () => {
  editor();
  const model = await screen.findByRole('combobox', { name: 'Model' });
  expect(screen.getByRole('combobox', { name: 'Brand' })).toHaveValue('DISABLED');
  const conversion = screen.getByRole('region', { name: 'Unit conversion' });
  expect(within(conversion).getByRole('combobox', { name: 'Alternate units and fixed conversion' })).toHaveValue('DISABLED');
  expect(within(conversion).getByRole('combobox', { name: 'Measured conversion' })).toHaveValue('DISABLED');
  await userEvent.selectOptions(model, 'OPTIONAL');
  const choice = screen.getByRole('combobox', { name: 'Enable model by default' });
  expect(choice.closest('.janso-config-fields__option')).toBe(model.closest('.janso-config-fields__option'));
  await userEvent.selectOptions(choice, 'true');
  await userEvent.selectOptions(model, 'REQUIRED');
  expect(screen.queryByRole('combobox', { name: 'Enable model by default' })).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Save draft changes' }));
  await waitFor(() => expect(vi.mocked(serviceCall).mock.calls.find(([, request]) => request.method === 'PATCH')?.[1].body).toEqual({ expected_version: 3, options: { model_mode: 'REQUIRED' } }));
});

it('provides working section targets while retaining settings return navigation', async () => {
  editor(); await screen.findByRole('combobox', { name: 'Model' });
  for (const link of within(screen.getByRole('navigation', { name: 'Configuration sections' })).getAllByRole('link')) {
    const target = document.getElementById(link.getAttribute('href')!.slice(1));
    expect(target).not.toBeNull(); expect(target).toHaveAttribute('tabindex', '-1');
  }
  expect(screen.getByRole('link', { name: 'Back to company settings' })).toHaveAttribute('href', '/settings');
  expect(vi.mocked(serviceCall).mock.calls.every(([, request]) => !request.method || request.method === 'GET')).toBe(true);
});

it('keeps protected dependent defaults from being implicitly overwritten', async () => {
  vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => {
    const value = structuredClone(completeResponse(request.path, request.method));
    if (value && typeof value === 'object' && 'fields' in value) {
      const modelDefault = value.fields?.find(field => field.key === 'model_default');
      if (modelDefault) modelDefault.writable = false;
    }
    return value as never;
  });
  editor(); const model = await screen.findByRole('combobox', { name: 'Model' });
  expect(within(model).getByRole('option', { name: 'Optional' })).toBeDisabled();
});

it('shows conversion and pricing groups in read-only draft review without granting edit access', async () => {
  render(<DisplayConfigProvider config={{ timezone: 'Asia/Kolkata' }}><ProductConfigurationDetail company={COMPANY} id={DRAFT} canManage={false} canPublish={false} timezone="Asia/Kolkata" /></DisplayConfigProvider>);
  expect(await screen.findByRole('heading', { name: 'Unit conversion' })).toBeVisible();
  expect(screen.getByRole('heading', { name: 'Additional pricing options' })).toBeVisible();
  expect(screen.getByText('Model', { selector: 'dt' })).toBeVisible();
  expect(screen.queryByRole('link', { name: 'Edit draft' })).not.toBeInTheDocument();
});
