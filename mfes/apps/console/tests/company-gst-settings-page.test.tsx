import { render, screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import GstSettingsPage from '../app/companies/[companyId]/gst-settings/page';
import { CompanyGstSettings } from '../app/components/CompanyGstSettings';
import { pageContext } from '../app/lib/page-context';
import { companyContextFor, sessionFor } from './helpers';
import { companyId, userId } from './access-fixtures';

vi.mock('next/navigation', () => ({ notFound: () => { throw new Error('not found'); } }));
vi.mock('../app/lib/page-context', () => ({ pageContext: vi.fn() }));
vi.mock('../app/providers', () => ({ Providers: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/components/ConsoleShell', () => ({ ConsoleShell: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/components/CompanyGstSettings', () => ({ CompanyGstSettings: vi.fn(({ companyId }: { companyId: string }) => <p>GST settings {companyId}</p>) }));
const props = (id = companyId) => ({ params: Promise.resolve({ companyId: id }), searchParams: Promise.resolve({ returnTo: '/companies/' + companyId + '/configuration?returnTo=%2Fsettings' }) });
beforeEach(async () => {
  vi.clearAllMocks(); const session = await sessionFor({ permissions: ['company.read'] });
  session.company = { id: userId, name: 'Other open company' };
  session.grants = [{ scope_type: 'company', scope_id: companyId, permissions: ['company.read'], valid_from: '2000-01-01', valid_to: null }];
  vi.mocked(pageContext).mockResolvedValue({ session, context: companyContextFor() });
});
it('allows scoped readers without changing the open company and forwards the return context', async () => {
  render(await GstSettingsPage(props())); expect(screen.getByText('GST settings ' + companyId)).toBeVisible();
  expect(vi.mocked(CompanyGstSettings).mock.calls[0][0]).toMatchObject({ companyId, returnTo: '/companies/' + companyId + '/configuration?returnTo=%2Fsettings' });
  expect((await pageContext()).session.company.id).toBe(userId);
});
it('normalizes valid company IDs and rejects malformed routes before resolving a session', async () => {
  await GstSettingsPage(props(companyId.toUpperCase())); vi.mocked(pageContext).mockClear();
  await expect(GstSettingsPage(props('invalid'))).rejects.toThrow('not found');
  expect(pageContext).not.toHaveBeenCalled();
});
it.each(['other_company', 'expired', 'platform_label'])('denies GST settings through %s', async authority => {
  const { session } = await pageContext();
  if (authority === 'other_company') session.grants![0].scope_id = userId;
  if (authority === 'expired') session.grants![0].valid_to = '2020-01-01';
  if (authority === 'platform_label') { session.role = 'platform_admin'; session.grants = []; }
  render(await GstSettingsPage(props()));
  expect(screen.getByText('Company read access is required for this company.')).toBeVisible();
  expect(CompanyGstSettings).not.toHaveBeenCalled();
});
