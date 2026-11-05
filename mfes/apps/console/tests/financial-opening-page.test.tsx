import { render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import Page from '../app/accounting/opening/page';
import { pageContext } from '../app/lib/page-context';
import { companyContextFor, sessionFor } from './helpers';
import { ACCOUNT, COMPANY, OTHER } from './financial-opening-fixtures';
vi.mock('../app/lib/page-context', () => ({ pageContext: vi.fn() }));
vi.mock('../app/providers', () => ({ Providers: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/components/ConsoleShell', () => ({ ConsoleShell: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/components/FinancialOpeningWorkspace', () => ({ FinancialOpeningWorkspace: ({ company, access, initialAccountId }: { company: string; access: { manage: boolean; post: boolean; cancel: boolean; export: boolean }; initialAccountId?: string }) => <p data-post={String(access.post)} data-cancel={String(access.cancel)} data-export={String(access.export)}>Opening {company} {String(access.manage)} {initialAccountId}</p> }));
it.each([true, false])('uses current company finance authority (%s)', async allowed => {
  const session = await sessionFor(); session.company = { id: COMPANY, name: 'Current company' };
  session.grants = [{ scope_type: 'company', scope_id: allowed ? COMPANY : OTHER, permissions: ['accounting.finance.read'], valid_from: '2020-01-01', valid_to: null }];
  vi.mocked(pageContext).mockResolvedValue({ session, context: companyContextFor() });
  render(await Page({ searchParams: Promise.resolve({ account_id: ACCOUNT }) }));
  if (allowed) expect(screen.getByText(`Opening ${COMPANY} false ${ACCOUNT}`)).toBeVisible();
  else { expect(screen.queryByText(/Opening .*false/)).not.toBeInTheDocument(); expect(screen.getByText(/Choose a company with finance read access/)).toBeVisible(); }
});

it.each(['tenant', 'company'] as const)('native opening grants enable controls at %s scope', async scope => {
  const session = await sessionFor(); session.company = { id: COMPANY, name: 'Current company' };
  session.grants = [{ scope_type: scope, scope_id: scope === 'tenant' ? null : COMPANY, permissions: ['accounting.finance.read', 'accounting.finance.manage', 'ledger.post_journal', 'period.post', 'accounting.export.read'], valid_from: '2020-01-01', valid_to: null }];
  vi.mocked(pageContext).mockResolvedValue({ session, context: companyContextFor() });
  render(await Page({ searchParams: Promise.resolve({ account_id: ACCOUNT }) }));
  const workspace = screen.getByText(`Opening ${COMPANY} true ${ACCOUNT}`);
  expect(workspace).toHaveAttribute('data-post', 'true');
  expect(workspace).toHaveAttribute('data-cancel', 'true');
  expect(workspace).toHaveAttribute('data-export', 'true');
});

it('another company grant cannot upgrade the selected company read access', async () => {
  const session = await sessionFor(); session.company = { id: COMPANY, name: 'Current company' };
  session.grants = [
    { scope_type: 'company', scope_id: COMPANY, permissions: ['accounting.finance.read'], valid_from: '2020-01-01', valid_to: null },
    { scope_type: 'company', scope_id: OTHER, permissions: ['accounting.finance.manage', 'ledger.post_journal', 'period.post', 'accounting.export.read'], valid_from: '2020-01-01', valid_to: null },
  ];
  vi.mocked(pageContext).mockResolvedValue({ session, context: companyContextFor() });
  render(await Page({ searchParams: Promise.resolve({ account_id: ACCOUNT }) }));
  const workspace = screen.getByText(`Opening ${COMPANY} false ${ACCOUNT}`);
  expect(workspace).toHaveAttribute('data-post', 'false');
  expect(workspace).toHaveAttribute('data-cancel', 'false');
  expect(workspace).toHaveAttribute('data-export', 'false');
});
