import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { DisplayConfigProvider } from '@janso/ui';
import { ReferenceRecord } from '../app/platform/references/ReferenceRecord';
import { ReferenceDirectory } from '../app/platform/references/ReferenceDirectory';
const { fetcher } = vi.hoisted(() => ({ fetcher: vi.fn() }));
vi.mock('../app/lib/session-fetch', () => ({ sessionFetch: fetcher }));
const record = { id: '01900000-0000-7000-8000-000000000001', code: 'en', name: 'English', parent_code: null, is_active: true, source: 'operator', version: 1, sync_ready: false, updated_at: '2026-10-21T00:00:00Z', protected_fields: ['code', 'iso3'], data: { kind: 'language', code: 'en', iso3: 'eng', name: 'English', native_name: null, is_active: true } };
beforeEach(() => { vi.restoreAllMocks(); fetcher.mockReset(); window.history.replaceState({}, '', '/platform/references/languages');
  fetcher.mockImplementation(async (_url, init) => { const input = JSON.parse(init.body);
    if (input.path.endsWith('/options')) return Response.json({ countries: [{ code: 'IN', name: 'India' }], currencies: [{ code: 'INR', name: 'Indian rupee' }] });
    if (input.path.includes('?')) return Response.json({ items: [record], page: { has_more: false, next_cursor: null } });
    return Response.json(record);
  });
});
const show = (node: React.ReactNode) => render(<DisplayConfigProvider>{node}</DisplayConfigProvider>);
it('protects unsaved reference edits when checking synchronization', async () => {
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
  show(<ReferenceRecord catalog="languages" code="en" mode="edit" />);
  fireEvent.change(await screen.findByRole('textbox', { name: 'Name' }), { target: { value: 'Changed name' } });
  const before = fetcher.mock.calls.length;
  fireEvent.click(screen.getByRole('button', { name: 'Check synchronization' }));
  await waitFor(() => expect(confirm).toHaveBeenCalled());
  expect(fetcher.mock.calls).toHaveLength(before);
  expect(screen.getByRole('textbox', { name: 'Name' })).toHaveValue('Changed name');
});
it('freezes a new reference after an unconfirmed create so it cannot be submitted twice', async () => {
  fetcher.mockImplementation(async (_url, init) => {
    const input = JSON.parse(init.body);
    if (input.method === 'POST') throw new Error('connection lost after commit');
    return Response.json({ countries: [], currencies: [] });
  });
  show(<ReferenceRecord catalog="languages" mode="new" />);
  fireEvent.change(await screen.findByRole('textbox', { name: 'Code' }), { target: { value: 'zz' } });
  fireEvent.change(screen.getByRole('textbox', { name: 'ISO alpha-3 code' }), { target: { value: 'zzz' } });
  fireEvent.change(screen.getByRole('textbox', { name: 'Name' }), { target: { value: 'New language' } });
  fireEvent.click(screen.getByRole('button', { name: 'Create language' }));
  await screen.findByText(/could not be confirmed/i);
  expect(screen.getByRole('button', { name: 'Create language' })).toBeDisabled();
  expect(screen.getByRole('textbox', { name: 'Name' })).toBeDisabled();
});
it('uses searchable country and currency selectors for reference forms', async () => {
  show(<ReferenceRecord catalog="countries" mode="new" />);
  expect(await screen.findByRole('combobox', { name: 'Default currency' })).toHaveAttribute('type', 'text');
});
it('sanitizes unsupported reference sort before a directory request', async () => {
  window.history.replaceState({}, '', '/platform/references/languages?sort=private_field');
  show(<ReferenceDirectory catalog="languages" />); await screen.findByText('English');
  const paths = fetcher.mock.calls.map(([, init]) => JSON.parse(init.body).path);
  expect(paths.every((path: string) => !path.includes('private_field'))).toBe(true);
});
