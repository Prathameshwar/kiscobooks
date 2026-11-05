import { screen } from '@testing-library/react';
import { beforeEach, expect, expectTypeOf, it, vi } from 'vitest';
import TenantPage from '../app/settings/notifications/page';
import PlatformPage from '../app/platform/notifications/page';
import PlatformAreaPage from '../app/platform/notifications/[...segments]/page';
import TenantAreaPage from '../app/settings/notifications/[...segments]/page';
import { pageContext } from '../app/lib/page-context';
import { sessionFor, companyContextFor, renderWithProviders } from './helpers';
import type { NotificationQuery } from '../app/lib/notification-navigation';
it('uses the required Next page props object for notification entry points', () => {
  expectTypeOf<Parameters<typeof PlatformPage>[0]>().toMatchTypeOf<{ searchParams?: Promise<NotificationQuery> }>();
  expectTypeOf<Parameters<typeof TenantPage>[0]>().toMatchTypeOf<{ searchParams?: Promise<NotificationQuery> }>();
});
vi.mock('../app/lib/page-context', () => ({ pageContext: vi.fn() }));
vi.mock('../app/components/ConsoleShell', () => ({ ConsoleShell: ({ children }: { children: React.ReactNode }) => <>{children}</> }));
vi.mock('../app/components/NotificationAdmin', () => ({ NotificationAdmin: ({ owner, permissions, companyId, route = [], query }: { owner: string; permissions: string[]; companyId?: string; route?: string[]; query?: Record<string, unknown> }) => <p data-testid="workspace" data-company={companyId ?? 'none'} data-route={route.join('/')} data-query={JSON.stringify(query)}>{owner}: {permissions.join(',')}</p> }));
beforeEach(async () => {
  const session = await sessionFor({ permissions: ['notification.template.read'] });
  session.grants = [{ permissions: session.permissions, scope_type: 'tenant', scope_id: null, valid_from: '2020-01-01', valid_to: null }];
  vi.mocked(pageContext).mockResolvedValue({ session, context: companyContextFor() });
});
it('passes the tenant context and resolved grants into the workspace', async () => {
  await renderWithProviders(await TenantPage({})); expect(screen.getByText('tenant: notification.template.read')).toBeVisible();
});
it('does not grant tenant notification management from a company-only permission', async () => {
  const data = await pageContext(); data.session.grants![0].scope_type = 'company';
  await renderWithProviders(await TenantPage({}));
  expect(screen.getByTestId('workspace')).toHaveTextContent('tenant:');
  expect(screen.getByTestId('workspace')).not.toHaveTextContent('notification.template.read');
});
it('uses a separate platform workspace', async () => {
  await renderWithProviders(await PlatformPage({})); expect(screen.getByText('platform: notification.template.read')).toBeVisible();
});
it('resolves a platform detail route and filters without adopting the selected business company', async () => {
  const id = '019a0000-0000-7000-8000-000000000001';
  await renderWithProviders(await PlatformAreaPage({ params: Promise.resolve({ segments: ['providers', id] }), searchParams: Promise.resolve({ channel: 'sms' }) }));
  expect(screen.getByTestId('workspace')).toHaveAttribute('data-company', 'none');
  expect(screen.getByTestId('workspace')).toHaveAttribute('data-route', 'providers/' + id);
  expect(screen.getByTestId('workspace')).toHaveAttribute('data-query', JSON.stringify({ channel: 'sms' }));
});
it('resolves a tenant area through the tenant page boundary', async () => {
  await renderWithProviders(await TenantAreaPage({ params: Promise.resolve({ segments: ['consent'] }) }));
  expect(screen.getByTestId('workspace')).toHaveTextContent('tenant: notification.template.read');
  expect(screen.getByTestId('workspace')).toHaveAttribute('data-route', 'consent');
});
