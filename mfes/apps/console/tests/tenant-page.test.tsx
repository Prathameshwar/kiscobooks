import { render, screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import Page from '../app/platform/tenants/page';
const { session } = vi.hoisted(() => ({ session: vi.fn() }));
vi.mock('../app/session', () => ({ getSession: session }));
vi.mock('../app/lib/page-context', async () => {
  // Pages resolve the session and the company context through one helper now; the session
  // mock above still decides what that helper returns.
  const { getSession } = await import('../app/session');
  return { pageContext: async () => ({ session: await getSession(),
    context: { companies: [], companiesNote: null, fiscalYears: [], fiscalYear: null, fiscalNote: null } }) };
});
vi.mock('../app/providers', () => ({ Providers: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/components/ConsoleShell', () => ({ ConsoleShell: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/platform/tenants/TenantDirectory', () => ({ TenantDirectory: () => <p>Tenant directory</p> }));
beforeEach(() => session.mockReset());
it('renders the authorized tenant directory', async () => { session.mockResolvedValue({ permissions: ['platform.tenant.read'], organisation: { id: 'own' } }); render(await Page()); expect(screen.getByText('Tenant directory')).toBeInTheDocument(); });
it('denies tenant directory access without platform permission', async () => { session.mockResolvedValue({ permissions: [], organisation: {} }); render(await Page()); expect(screen.getByRole('alert')).toHaveTextContent('permission is required'); expect(screen.queryByText('Tenant directory')).not.toBeInTheDocument(); });
