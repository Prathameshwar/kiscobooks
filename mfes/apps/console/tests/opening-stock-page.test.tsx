import { render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import Page from '../app/inventory/stock/opening/page';
import { pageContext } from '../app/lib/page-context';
import { companyContextFor, sessionFor } from './helpers';
import { COMPANY, RECORD, SOURCE } from './product-classification-fixtures';
vi.mock('../app/lib/page-context', () => ({ pageContext: vi.fn() }));
vi.mock('../app/providers', () => ({
  Providers: ({ children }: { children: React.ReactNode }) => children,
}));
vi.mock('../app/components/ConsoleShell', () => ({
  ConsoleShell: ({ children }: { children: React.ReactNode }) => children,
}));
vi.mock('../app/components/OpeningStockWorkspace', () => ({
  OpeningStockWorkspace: ({
    company,
    initialItemId,
    access,
  }: {
    company: string;
    initialItemId?: string;
    access: { manage: boolean };
  }) => (
    <p>
      Opening {String(access.manage)} {company} {initialItemId}
    </p>
  ),
}));
it.each([true, false])(
  'requires stock read authority for the current company (%s)',
  async (allowed) => {
    const session = await sessionFor();
    session.company = { id: COMPANY, name: 'Current company' };
    session.grants = [
      {
        scope_type: 'company',
        scope_id: allowed ? COMPANY : SOURCE,
        permissions: ['accounting.stock.read'],
        valid_from: '2020-01-01',
        valid_to: null,
      },
    ];
    vi.mocked(pageContext).mockResolvedValue({
      session,
      context: companyContextFor(),
    });
    render(await Page({ searchParams: Promise.resolve({ item_id: RECORD }) }));
    if (allowed) {
      expect(
        screen.getByText(`Opening false ${COMPANY} ${RECORD}`),
      ).toBeVisible();
    } else expect(screen.queryByText(/Opening false/)).not.toBeInTheDocument();
  },
);

it('normalizes a valid bookmarked product ID before verified prefill', async () => {
  const session = await sessionFor();
  session.company = { id: COMPANY, name: 'Current company' };
  session.grants = [
    {
      scope_type: 'company',
      scope_id: COMPANY,
      permissions: ['accounting.stock.read'],
      valid_from: '2020-01-01',
      valid_to: null,
    },
  ];
  vi.mocked(pageContext).mockResolvedValue({
    session,
    context: companyContextFor(),
  });
  const id = '0199ABCD-ABCD-7000-8000-000000000001';
  render(await Page({ searchParams: Promise.resolve({ item_id: id }) }));
  expect(
    screen.getByText(`Opening false ${COMPANY} ${id.toLowerCase()}`),
  ).toBeVisible();
});
