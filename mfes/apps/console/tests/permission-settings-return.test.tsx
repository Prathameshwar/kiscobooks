import { screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { PermissionDirectory } from '../app/components/PermissionDirectory';
import { access } from './access-fixtures';
import { renderWithProviders } from './helpers';

vi.mock('../app/lib/access-directory', async original => ({
  ...await original<object>(),
  usePermissionCatalogue: () => ({ permissions: ['role.read'], loading: false, failure: null, refresh: vi.fn() }),
}));
it('returns to Company Settings from the permission catalogue', async () => {
  await renderWithProviders(<PermissionDirectory context={access} returnTo="/settings" />);
  expect(screen.getByRole('link', { name: /^Back to / })).toHaveAttribute('href', '/settings');
});
it('rejects external returns and keeps a useful organisation fallback', async () => {
  await renderWithProviders(<PermissionDirectory context={access} returnTo="//outside.invalid/settings" />);
  expect(screen.getByRole('link', { name: /^Back to / })).toHaveAttribute('href', '/organisation');
});
it('does not make the permission catalogue its own Back destination', async () => {
  await renderWithProviders(<PermissionDirectory context={access} returnTo="/permissions?q=role" />);
  expect(screen.getByRole('link', { name: /^Back to / })).toHaveAttribute('href', '/organisation');
});
