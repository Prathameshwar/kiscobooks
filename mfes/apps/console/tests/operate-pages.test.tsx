import { render, screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { pageContext } from '../app/lib/page-context';
import { companyContextFor, sessionFor } from './helpers';
import AreaPage from '../app/operate/[area]/page';
import FamilyPage from '../app/operate/[area]/[family]/page';

vi.mock('../app/lib/page-context', () => ({ pageContext: vi.fn() }));
vi.mock('../app/providers', () => ({ Providers: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/components/ConsoleShell', () => ({ ConsoleShell: ({ children, activeHref }: { children: React.ReactNode; activeHref: string }) => <div data-active={activeHref}>{children}</div> }));
vi.mock('../app/components/OperateLanding', () => ({ OperateLanding: ({ area }: { area: { title: string } }) => <p>Landing {area.title}</p> }));
vi.mock('../app/components/OperateFamily', () => ({ OperateFamilyPage: (props: Record<string, unknown>) => <p>Family {JSON.stringify(props)}</p> }));
vi.mock('next/navigation', () => ({ notFound: () => { throw new Error('NEXT_NOT_FOUND'); } }));
const company = '10000000-0000-7000-8000-000000000001';
beforeEach(() => vi.mocked(pageContext).mockReset());
async function open(permissions = ['vouchers.read'], scope = company, selected: string | undefined = company) {
  const session = await sessionFor({ permissions }); session.company = { id: selected, name: 'Company' };
  session.grants = [{ scope_type: 'company', scope_id: scope, permissions, valid_from: '2000-01-01', valid_to: null }];
  vi.mocked(pageContext).mockResolvedValue({ session, context: companyContextFor() });
}
it.each(['income', 'expense', 'inventory'])('opens the %s server landing with scoped read access', async area => {
  await open(); render(await AreaPage({ params: Promise.resolve({ area }) }));
  expect(screen.getByText(/^Landing/)).toBeInTheDocument();
  expect(document.querySelector('[data-active]')).toHaveAttribute('data-active', '/operate/' + area);
});
it('passes print/type grants individually to the family', async () => {
  await open(['vouchers.read', 'design.template.read']);
  render(await FamilyPage({ params: Promise.resolve({ area: 'expense', family: 'purchase' }) }));
  expect(screen.getByText(/^Family/)).toHaveTextContent('"canPrint":true');
  expect(screen.getByText(/^Family/)).toHaveTextContent('"canManageTypes":false');
});
it('refuses another company grant before mounting a voucher page', async () => {
  await open(['vouchers.read'], '10000000-0000-7000-8000-000000000002');
  render(await AreaPage({ params: Promise.resolve({ area: 'income' }) }));
  expect(screen.getByText(/Voucher read access is required/)).toBeInTheDocument();
  expect(screen.queryByText(/^Landing/)).not.toBeInTheDocument();
});
it('explains an unopened company', async () => {
  await open(); const context = await pageContext(); context.session.company = { name: 'Select company' };
  render(await AreaPage({ params: Promise.resolve({ area: 'income' }) }));
  expect(screen.getByText(/No company is open/)).toBeInTheDocument();
});
it('rejects unknown areas and inconsistent families without reading session data', async () => {
  await expect(AreaPage({ params: Promise.resolve({ area: 'nonsense' }) })).rejects.toThrow('NEXT_NOT_FOUND');
  await expect(FamilyPage({ params: Promise.resolve({ area: 'income', family: 'purchase' }) })).rejects.toThrow('NEXT_NOT_FOUND');
  expect(pageContext).not.toHaveBeenCalled();
});
