import type { ReactNode } from 'react';
import { render, screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import Page from '../app/audit/page';
import { getSession } from '../app/session';
vi.mock('../app/session', () => ({ getSession: vi.fn() }));
vi.mock('../app/lib/page-context', async () => {
  // Pages resolve the session and the company context through one helper now; the session
  // mock above still decides what that helper returns.
  const { getSession } = await import('../app/session');
  return { pageContext: async () => ({ session: await getSession(),
    context: { companies: [], companiesNote: null, fiscalYears: [], fiscalYear: null, fiscalNote: null } }) };
});
vi.mock('../app/providers', () => ({ Providers: ({ children }: { children: ReactNode }) => <>{children}</> }));
vi.mock('../app/components/ConsoleShell', () => ({ ConsoleShell: ({ children }: { children: ReactNode }) => <>{children}</> }));
vi.mock('../app/components/AuditEvents', () => ({
  AuditEvents: ({ navigation, ...props }: { navigation?: ReactNode }) => <>{navigation}<pre data-testid="scope">{JSON.stringify(props)}</pre></>,
}));
beforeEach(() => {
  vi.mocked(getSession).mockResolvedValue({ company: { id: 'current' }, permissions: ['audit.read'], grants: [{ scope_type: 'company', scope_id: 'current', permissions: ['audit.read'], valid_from: '2000-01-01', valid_to: null }] } as Awaited<ReturnType<typeof getSession>>);
});
it('uses the active company without sample events', async () => {
  render(await Page({ searchParams: Promise.resolve({}) }));
  expect(screen.getByTestId('scope')).toHaveTextContent('{"companyId":"current"}');
  expect(screen.getByRole('link', { name: 'Back to logs and activities' })).toHaveAttribute('href', '/logs-and-activities');
});
it('requires switching company instead of mixing a history link with the current company header', async () => {
  render(await Page({ searchParams: Promise.resolve({ company_id: 'selected', entity_type: 'accounting.party', entity_id: 'record' }) }));
  expect(screen.queryByTestId('scope')).not.toBeInTheDocument();
  expect(screen.getByText(/Open the company associated with this history link/)).toBeVisible();
});
it('does not mount audit reads without the required permission', async () => {
  vi.mocked(getSession).mockResolvedValue({ company: { id: 'current' }, permissions: [] } as unknown as Awaited<ReturnType<typeof getSession>>);
  render(await Page({ searchParams: Promise.resolve({}) })); expect(screen.queryByTestId('scope')).not.toBeInTheDocument();
});
it('rejects repeated company filters without crashing or mounting history reads', async () => {
  render(await Page({ searchParams: Promise.resolve({ company_id: ['current', 'other'] }) as never }));
  expect(screen.queryByTestId('scope')).not.toBeInTheDocument();
  expect(screen.getByText('This history link contains invalid filters.')).toBeVisible();
});
it('does not render another user scope when session resolution fails', async () => {
  vi.mocked(getSession).mockRejectedValue(new Error('Session unavailable'));
  await expect(Page({ searchParams: Promise.resolve({}) })).rejects.toThrow('Session unavailable');
});

it('does not mount audit reads with an audit grant for another company', async () => {
  vi.mocked(getSession).mockResolvedValue({ company: { id: 'current' }, permissions: ['audit.read'], grants: [{ scope_type: 'company', scope_id: 'other', permissions: ['audit.read'], valid_from: '2000-01-01', valid_to: null }] } as Awaited<ReturnType<typeof getSession>>);
  render(await Page({ searchParams: Promise.resolve({}) }));
  expect(screen.queryByTestId('scope')).not.toBeInTheDocument();
});

it('opens tenant-wide subject history only with a current tenant audit grant', async () => {
  vi.mocked(getSession).mockResolvedValue({ company: { id: 'current' }, permissions: ['audit.read'], grants: [{ scope_type: 'tenant', scope_id: null, permissions: ['audit.read'], valid_from: '2000-01-01', valid_to: null }] } as Awaited<ReturnType<typeof getSession>>);
  render(await Page({ searchParams: Promise.resolve({ scope: 'organisation', entity_type: 'department', entity_id: 'record' }) }));
  const props = JSON.parse(screen.getByTestId('scope').textContent!);
  expect(props).toMatchObject({ entityType: 'department', entityId: 'record' });
  expect(props.companyId).toBeUndefined();
});

it('rejects organisation history with a company-only grant', async () => {
  render(await Page({ searchParams: Promise.resolve({ scope: 'organisation' }) }));
  expect(screen.queryByTestId('scope')).not.toBeInTheDocument();
});

it('rejects mixed organisation and company scope filters', async () => {
  render(await Page({ searchParams: Promise.resolve({ scope: 'organisation', company_id: 'current' }) }));
  expect(screen.queryByTestId('scope')).not.toBeInTheDocument();
});
