import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { reachTenantReview, renderTenant, tenantChoices as choices } from './tenant-wizard-fixtures';
const { fetcher } = vi.hoisted(() => ({ fetcher: vi.fn() }));
vi.mock('../app/lib/session-fetch', () => ({ sessionFetch: fetcher }));
beforeEach(() => {
  fetcher.mockReset(); sessionStorage.clear();
  fetcher.mockImplementation(async (_url, init) => Response.json(JSON.parse(init.body).path.includes('pending-registration') ? { match: null } : choices));
});
it('restores only metadata after reauthentication and reuses the creation key', async () => {
  const view = renderTenant(); await reachTenantReview();
  const original = fetcher.getMockImplementation()!;
  fetcher.mockImplementation((...args) => JSON.parse(args[1].body).method === 'POST' ? Response.json({ error: { code: 'platform_reauthentication_required', message: 'Sign in to confirm' } }, { status: 403 }) : original(...args));
  await userEvent.click(screen.getByRole('button', { name: 'Create tenant' }));
  const key = JSON.parse(fetcher.mock.lastCall![1].body).key;
  const link = await screen.findByRole('link', { name: 'Sign in again' });
  link.addEventListener('click', event => event.preventDefault()); fireEvent.click(link);
  const recovered = JSON.parse(sessionStorage.getItem('janso-platform-draft:operator:new')!);
  expect(recovered.draft).not.toHaveProperty('password');
  expect(recovered.draft).not.toHaveProperty('recipient_confirmed');
  view.unmount();
  fetcher.mockImplementation((...args) => JSON.parse(args[1].body).method === 'POST' ? Response.json({ error: { message: 'Temporary service failure' } }, { status: 503 }) : original(...args));
  renderTenant();
  await waitFor(() => expect(screen.getByRole('textbox', { name: 'Tenant name' })).toHaveValue('New Books'));
  await userEvent.click(screen.getByRole('button', { name: 'Next' }));
  expect(screen.getByRole('checkbox', { name: /I confirm this person controls/ })).not.toBeChecked();
  fireEvent.click(screen.getByRole('checkbox', { name: /I confirm this person controls/ }));
  await userEvent.click(screen.getByRole('button', { name: 'Next' }));
  await screen.findByRole('heading', { name: 'Review & create', level: 1 });
  await userEvent.click(screen.getByRole('button', { name: 'Create tenant' }));
  await screen.findByText('Temporary service failure');
  expect(JSON.parse(fetcher.mock.lastCall![1].body).key).toBe(key); expect(sessionStorage.length).toBe(0);
});
it('locks creation navigation while pending and returns server field errors to tenant details', async () => {
  renderTenant(); await reachTenantReview(); let finish!: (response: Response) => void;
  const original = fetcher.getMockImplementation()!;
  fetcher.mockImplementation((...args) => JSON.parse(args[1].body).method === 'POST' ? new Promise(resolve => { finish = resolve; }) : original(...args));
  await userEvent.click(screen.getByRole('button', { name: 'Create tenant' }));
  expect(screen.getByRole('button', { name: 'Creating tenant…' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Back' })).toBeDisabled();
  expect(screen.queryByRole('button', { name: 'Edit tenant name' })).not.toBeInTheDocument();
  finish(Response.json({ error: { message: 'State unavailable', fields: { default_state_code: 'inactive' } } }, { status: 422 }));
  expect(await screen.findByRole('combobox', { name: 'State' })).toHaveAttribute('aria-invalid', 'true');
  expect(screen.getByRole('textbox', { name: 'Tenant name' })).toHaveValue('New Books');
});
it('recovers after regional lookup failure', async () => {
  fetcher.mockResolvedValue(Response.json({ error: { message: 'Choices unavailable' } }, { status: 500 }));
  renderTenant(); await screen.findByText('Choices unavailable');
  fetcher.mockResolvedValue(Response.json(choices)); await userEvent.click(screen.getByRole('button', { name: 'Retry loading form' }));
  expect(await screen.findByRole('combobox', { name: 'Country' })).toHaveValue('IN');
});
it('ignores expired or malformed recovered drafts', async () => {
  sessionStorage.setItem('janso-platform-draft:operator:new', JSON.stringify({ at: Date.now() - 31 * 60000, key: 'old-key', draft: { name: 'Old draft' } }));
  renderTenant(); expect(await screen.findByRole('textbox', { name: 'Tenant name' })).toHaveValue(''); expect(sessionStorage.length).toBe(0);
});
