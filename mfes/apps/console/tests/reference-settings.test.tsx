import { render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import PlatformPage from '../app/platform/page';
vi.mock('../app/session', () => ({ getSession: async () => ({ permissions: ['platform.config.manage'] }) }));
vi.mock('../app/lib/page-context', async () => {
  // Pages resolve the session and the company context through one helper now; the session
  // mock above still decides what that helper returns.
  const { getSession } = await import('../app/session');
  return { pageContext: async () => ({ session: await getSession(),
    context: { companies: [], companiesNote: null, fiscalYears: [], fiscalYear: null, fiscalNote: null } }) };
});
vi.mock('../app/providers', () => ({ Providers: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/components/ConsoleShell', () => ({ ConsoleShell: ({ children }: { children: React.ReactNode }) => children }));
it('links all four global catalogs from Platform administration for a platform configuration administrator', async () => {
  render(await PlatformPage());
  for (const [title, path] of [['Countries', 'countries'], ['States', 'states'], ['Languages', 'languages'], ['Currencies', 'currencies']]) {
    expect(screen.getByRole('link', { name: title })).toHaveAttribute('href', '/platform/references/' + path);
  }
});
