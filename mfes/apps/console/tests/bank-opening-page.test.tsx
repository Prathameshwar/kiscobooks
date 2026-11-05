import { render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import Page from '../app/accounting/bank-reconciliation/page';
import { pageContext } from '../app/lib/page-context';
import { companyContextFor, sessionFor } from './helpers';
import { COMPANY, OTHER } from './financial-opening-fixtures';
vi.mock('../app/lib/page-context', () => ({ pageContext: vi.fn() }));
vi.mock('../app/providers', () => ({ Providers: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/components/ConsoleShell', () => ({ ConsoleShell: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/components/BankReconciliation', () => ({ BankReconciliation: ({ company }: { company: string }) => <p>Bank opening owner {company}</p> }));
it.each([true, false])('uses company-scoped bank authority without granting report access (%s)', async allowed => {
  const session = await sessionFor(); session.company = { id: COMPANY, name: 'Current company' };
  session.grants = [{ scope_type: 'company', scope_id: allowed ? COMPANY : OTHER,
    permissions: ['accounting.bank.read', 'accounting.statement.read'], valid_from: '2020-01-01', valid_to: null }];
  vi.mocked(pageContext).mockResolvedValue({ session, context: companyContextFor() });
  render(await Page());
  if (allowed) {
    expect(screen.getByText('Bank opening owner ' + COMPANY)).toBeVisible();
    expect(screen.getByRole('link', { name: /Account and party openings/i })).toHaveAttribute('href', '/accounting/opening');
  } else expect(screen.queryByText(/Bank opening owner/)).not.toBeInTheDocument();
});
