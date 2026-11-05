import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { AccessDirectory } from '../app/components/AccessDirectory';
import { serviceCall } from '../app/lib/service-call';
import { access, page, roleRecord, userRecord } from './access-fixtures';
import { renderWithProviders } from './helpers';

vi.mock('../app/lib/service-call', async original => ({ ...await original<object>(), serviceCall: vi.fn() }));
beforeEach(() => {
  window.history.replaceState(null, '', '/'); vi.mocked(serviceCall).mockReset();
  vi.mocked(serviceCall).mockImplementation(async (_, request) => page([request.path.startsWith('/v1/roles') ? roleRecord : userRecord]) as never);
});

it.each(['users', 'roles'] as const)('returns to Settings from %s and keeps that parent through filtering and related actions', async resource => {
  await renderWithProviders(<AccessDirectory resource={resource} context={access} initialQuery="returnTo=%2Fsettings" />);
  expect(screen.getByRole('link', { name: 'Back to company settings' })).toHaveAttribute('href', '/settings');
  await userEvent.type(screen.getByRole('searchbox'), 'Ava');
  await waitFor(() => {
    const query = new URLSearchParams(window.location.search);
    expect(query.get('q')).toBe('Ava'); expect(query.get('returnTo')).toBe('/settings');
  });
  await userEvent.click(await screen.findByRole('button', { name: /^Actions for / }));
  const assignments = new URL(screen.getByRole('menuitem', { name: 'Manage role assignments' }).getAttribute('href')!, 'https://console.invalid');
  const directory = new URL(assignments.searchParams.get('returnTo')!, assignments);
  expect(directory.pathname).toBe('/' + resource);
  expect(directory.searchParams.get('q')).toBe('Ava');
  expect(directory.searchParams.get('returnTo')).toBe('/settings');
});

it.each(['//outside.invalid/settings', '/users?q=Ava'])('rejects unsafe or self directory returns %s', async returnTo => {
  await renderWithProviders(<AccessDirectory resource="users" context={access} initialQuery={'returnTo=' + encodeURIComponent(returnTo)} />);
  expect(screen.getByRole('link', { name: /^Back to / })).toHaveAttribute('href', '/organisation');
});
