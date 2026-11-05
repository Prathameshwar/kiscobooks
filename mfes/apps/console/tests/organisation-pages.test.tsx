import { screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import DepartmentsPage from '../app/departments/[[...segments]]/page';
import GroupsPage from '../app/user-groups/[[...segments]]/page';
import OrganisationPage from '../app/organisation/page';
import { pageContext } from '../app/lib/page-context';
import { companyContextFor, renderWithProviders, sessionFor } from './helpers';
import { companyId, roleId } from './access-fixtures';
vi.mock('next/navigation', () => ({ notFound: () => { throw new Error('not found'); } }));
vi.mock('../app/lib/page-context', () => ({ pageContext: vi.fn() }));
vi.mock('../app/components/ConsoleShell', () => ({ ConsoleShell: ({ children }: { children: React.ReactNode }) => <>{children}</> }));
vi.mock('../app/components/OrganisationDirectory', () => ({ OrganisationDirectory: ({ resource }: { resource: string }) => <p>{resource} directory</p> }));
vi.mock('../app/components/OrganisationEditor', () => ({ OrganisationEditor: ({ resource }: { resource: string }) => <p>{resource} editor</p> }));
vi.mock('../app/components/OrganisationDetail', () => ({ OrganisationDetail: ({ resource }: { resource: string }) => <p>{resource} details</p> }));
const props = (segments: string[] = [], search: Record<string, string> = {}) => ({ params: Promise.resolve({ segments }), searchParams: Promise.resolve(search) });
async function seed(keys: string[], scope = 'tenant', scopeId: string | null = null, selected = true) {
  const session = { ...await sessionFor({ permissions: keys }), company: selected ? { id: companyId, name: 'Acme' } : { name: 'None' }, grants: [{ scope_type: scope, scope_id: scopeId, permissions: keys, valid_from: '2000-01-01', valid_to: null }] };
  vi.mocked(pageContext).mockResolvedValue({ session, context: companyContextFor() });
}
beforeEach(() => seed(['department.read', 'department.manage', 'group.read', 'group.manage']));
it.each([[[], 'directory'], [['new'], 'editor'], [[roleId], 'details'], [[roleId, 'edit'], 'editor']] as const)('routes department pages %j', async (segments, result) => { await renderWithProviders(await DepartmentsPage(props([...segments]))); expect(screen.getByText('departments ' + result)).toBeInTheDocument(); });
it.each([[[], 'directory'], [['new'], 'editor'], [[roleId], 'details'], [[roleId, 'edit'], 'editor']] as const)('routes user-group pages %j', async (segments, result) => { await renderWithProviders(await GroupsPage(props([...segments]))); expect(screen.getByText('user-groups ' + result)).toBeInTheDocument(); });
it.each([['invalid'], ['new', 'edit'], [roleId, 'invalid'], [roleId, 'edit', 'more']].map(segments => ({ segments })))('rejects invalid department routes $segments', async ({ segments }) => { await expect(DepartmentsPage(props(segments))).rejects.toThrow('not found'); });
it('rejects invalid parent preselection', async () => { await expect(DepartmentsPage(props(['new'], { parent_id: 'invalid' }))).rejects.toThrow('not found'); });
it('asks for a company before department administration', async () => { await seed(['department.read'], 'tenant', null, false); await renderWithProviders(await DepartmentsPage(props())); expect(screen.getByText(/Select an authorized company/)).toBeInTheDocument(); });
it('does not promote a company group grant into tenant authority', async () => { await seed(['group.read', 'group.manage'], 'company', companyId); await renderWithProviders(await GroupsPage(props())); expect(screen.getByText(/Tenant-wide group read permission is required/)).toBeInTheDocument(); });
it('allows departmental readers and child creation but withholds root creation', async () => {
  await seed(['department.read', 'department.manage'], 'department', roleId);
  await renderWithProviders(await DepartmentsPage(props(['new'], { parent_id: roleId }))); expect(screen.getByText('departments editor')).toBeInTheDocument();
});
it('withholds child creation from a departmental reader without management authority', async () => {
  await seed(['department.read'], 'department', roleId);
  await renderWithProviders(await DepartmentsPage(props(['new'], { parent_id: roleId })));
  expect(screen.getByText('Department management permission is required.')).toBeInTheDocument();
  expect(screen.queryByText('departments editor')).not.toBeInTheDocument();
});
it('keeps the organization entry available for a group-only tenant administrator', async () => { await seed(['group.read']); await renderWithProviders(await OrganisationPage()); expect(screen.getByRole('link', { name: 'User groups' })).toHaveAttribute('href', '/user-groups'); });
