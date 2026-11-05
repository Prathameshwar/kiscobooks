import { render, screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import DirectoryPage from '../app/platform/references/[catalog]/page';
import NewPage from '../app/platform/references/[catalog]/new/page';
import ViewPage from '../app/platform/references/[catalog]/[code]/page';
import EditPage from '../app/platform/references/[catalog]/[code]/edit/page';
const { session, redirect } = vi.hoisted(() => ({ session: vi.fn(), redirect: vi.fn(() => { throw new Error('redirect'); }) }));
vi.mock('../app/session', () => ({ getSession: session }));
vi.mock('../app/lib/page-context', async () => {
  // Pages resolve the session and the company context through one helper now; the session
  // mock above still decides what that helper returns.
  const { getSession } = await import('../app/session');
  return { pageContext: async () => ({ session: await getSession(),
    context: { companies: [], companiesNote: null, fiscalYears: [], fiscalYear: null, fiscalNote: null } }) };
});
vi.mock('next/navigation', () => ({ notFound: () => { throw new Error('not found'); }, redirect }));
vi.mock('../app/providers', () => ({ Providers: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/components/ConsoleShell', () => ({ ConsoleShell: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/platform/references/ReferenceDirectory', () => ({ ReferenceDirectory: ({ catalog }: { catalog: string }) => <p>Directory {catalog}</p> }));
vi.mock('../app/platform/references/ReferenceRecord', () => ({ ReferenceRecord: ({ catalog, mode, code, returnTo }: { catalog: string; mode: string; code?: string; returnTo?: string }) => <p>{catalog} {mode} {code} {returnTo}</p> }));
beforeEach(() => session.mockResolvedValue({ permissions: ['platform.config.manage'] }));
it.each(['countries', 'states', 'languages', 'currencies'])('renders list and all dedicated record routes for %s', async catalog => {
  const params = Promise.resolve({ catalog, code: catalog === 'states' ? 'IN-MH' : 'IN' });
  const searchParams = Promise.resolve({ returnTo: '/platform/references/' + catalog + '?status=active' });
  for (const [page, text] of [[DirectoryPage, 'Directory'], [NewPage, 'new'], [ViewPage, 'view'], [EditPage, 'edit']] as const) {
    const result = render(await page({ params, searchParams }));
    expect(screen.getByText(new RegExp(text))).toHaveTextContent(catalog); result.unmount();
  }
});
it('denies catalog pages without configuration authority', async () => {
  session.mockResolvedValue({ permissions: [] });
  const params = Promise.resolve({ catalog: 'countries', code: 'IN' }), searchParams = Promise.resolve({});
  for (const page of [DirectoryPage, NewPage, ViewPage, EditPage]) {
    const result = render(await page({ params, searchParams }));
    expect(screen.getByRole('alert')).toHaveTextContent('permission is required'); result.unmount();
  }
});
it('rejects unknown catalogs and malformed codes', async () => {
  await expect(DirectoryPage({ params: Promise.resolve({ catalog: 'secret' }) })).rejects.toThrow('not found');
  await expect(ViewPage({ params: Promise.resolve({ catalog: 'countries', code: '../' }), searchParams: Promise.resolve({}) })).rejects.toThrow('not found');
});

it('opens the reference landing page with all five catalogue cards and a back link', async () => {
  const ReferencesPage = (await import('../app/platform/references/page')).default;
  render(await ReferencesPage());
  for (const label of ['Countries', 'States', 'Currencies', 'Languages', 'Timezones'])
    expect(screen.getByRole('link', { name: label })).toHaveAttribute('href', '/platform/references/' + label.toLowerCase());
  expect(screen.getByRole('link', { name: 'Back to platform administration' })).toHaveAttribute('href', '/platform');
});
it('denies the reference landing page without configuration authority', async () => {
  session.mockResolvedValue({ permissions: ['platform.tenant.read'] });
  const ReferencesPage = (await import('../app/platform/references/page')).default;
  render(await ReferencesPage());
  expect(screen.getByRole('alert')).toHaveTextContent('permission is required');
  expect(screen.queryByRole('link', { name: 'Countries' })).not.toBeInTheDocument();
});
