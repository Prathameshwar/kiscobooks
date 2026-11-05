import { screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import RolesPage from '../app/roles/page';
import { pageContext } from '../app/lib/page-context';
import { sessionFor, companyContextFor, renderWithProviders } from './helpers';

vi.mock('../app/lib/page-context', () => ({ pageContext: vi.fn() }));
vi.mock('../app/components/ConsoleShell', () => ({ ConsoleShell: ({ children }: { children: React.ReactNode }) => <>{children}</> }));
vi.mock('../app/roles/RolesAccess', () => ({ RolesAccess: () => <p>Access directory</p> }));
beforeEach(async () => vi.mocked(pageContext).mockResolvedValue({ session: await sessionFor(), context: companyContextFor() }));
it('denies readers without role permissions', async () => {
  await renderWithProviders(await RolesPage({}));
  expect(screen.getByText('Role read permission is required.')).toBeInTheDocument();
});
it('supports scoped role readers without widening business permissions', async () => {
  const session = await sessionFor(); session.permissions = []; session.grants = [{ permissions: ['role.read'], scope_type: 'department', scope_id: 'department', valid_from: '2000-01-01', valid_to: null }];
  vi.mocked(pageContext).mockResolvedValue({ session, context: companyContextFor() });
  await renderWithProviders(await RolesPage({})); expect(screen.getByText('Access directory')).toBeInTheDocument();
});
