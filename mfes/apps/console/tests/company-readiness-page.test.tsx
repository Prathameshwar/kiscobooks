import { render, screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import Page from '../app/settings/readiness/page';
import { pageContext } from '../app/lib/page-context';
import { companyContextFor, sessionFor } from './helpers';
vi.mock('../app/lib/page-context', () => ({ pageContext: vi.fn() }));
vi.mock('../app/providers', () => ({ Providers: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/components/ConsoleShell', () => ({ ConsoleShell: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/components/CompanyReadiness', () => ({ CompanyReadiness: ({ company, permissions }: { company: string; permissions: string[] }) => <><p>Readiness for {company}</p><p>{permissions.join(', ')}</p></> }));
beforeEach(async () => vi.mocked(pageContext).mockResolvedValue({ session: await sessionFor(), context: companyContextFor() }));
it('requires an open company before rendering setup checks', async () => {
  render(await Page()); expect(screen.queryByText(/Readiness for/)).not.toBeInTheDocument();
});
it('uses only the company resolved in the authenticated page context', async () => {
  const data = await pageContext(); data.session.company = { id: 'company-a', name: 'A' };
  render(await Page()); expect(screen.getByText('Readiness for company-a')).toBeVisible();
});
it.each(['company.update', 'opening_balance.initialize_zero', 'accounting.finance.manage'])('passes company-scoped %s through to the setup action', async permission => {
  const session = await sessionFor({ permissions: [permission] });
  session.company = { id: 'company-a', name: 'A' };
  session.grants = [{ permissions: [permission], scope_type: 'company', scope_id: 'company-a', valid_from: '2020-01-01', valid_to: null }];
  vi.mocked(pageContext).mockResolvedValue({ session, context: companyContextFor() });
  render(await Page()); expect(screen.getByText(permission)).toBeVisible();
});
it('does not borrow setup update permission from another company', async () => {
  const session = await sessionFor({ permissions: ['company.update'] });
  session.company = { id: 'company-a', name: 'A' };
  session.grants = [{ permissions: ['company.update'], scope_type: 'company', scope_id: 'company-b', valid_from: '2020-01-01', valid_to: null }];
  vi.mocked(pageContext).mockResolvedValue({ session, context: companyContextFor() });
  render(await Page()); expect(screen.queryByText('company.update')).not.toBeInTheDocument();
});
