import { render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import Page from '../app/vouchers/[voucherId]/page';
import { pageContext } from '../app/lib/page-context';
import { companyContextFor, sessionFor } from './helpers';
import { COMPANY, CONTROL, ITEM } from './opening-stock-fixtures';
vi.mock('../app/lib/page-context', () => ({ pageContext: vi.fn() }));
vi.mock('../app/providers', () => ({
  Providers: ({ children }: { children: React.ReactNode }) => children,
}));
vi.mock('../app/components/ConsoleShell', () => ({
  ConsoleShell: ({ children }: { children: React.ReactNode }) => children,
}));
vi.mock('../app/components/VoucherWorkflow', () => ({
  VoucherWorkflow: ({ permissions }: { permissions: string[] }) => (
    <output>{permissions.join(',')}</output>
  ),
}));
it.each([COMPANY, ITEM])(
  'applies current-company grants before native voucher handoff %s',
  async (scope) => {
    const session = await sessionFor();
    session.company = { id: COMPANY, name: 'Current company' };
    session.permissions = ['vouchers.read', 'vouchers.approve'];
    session.grants = [
      {
        scope_type: 'company',
        scope_id: scope,
        permissions: ['vouchers.read'],
        valid_from: '2020-01-01',
        valid_to: null,
      },
    ];
    vi.mocked(pageContext).mockResolvedValue({
      session,
      context: companyContextFor(),
    });
    render(await Page({ params: Promise.resolve({ voucherId: CONTROL }) }));
    if (scope === COMPANY) {
      expect(screen.getByRole('status')).toHaveTextContent('vouchers.read');
      expect(screen.getByRole('status')).not.toHaveTextContent(
        'vouchers.approve',
      );
    } else expect(screen.queryByRole('status')).not.toBeInTheDocument();
  },
);
