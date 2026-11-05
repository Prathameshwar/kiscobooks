import { render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import EditPage from '../app/vouchers/[voucherId]/edit/page';
import EntryPage from '../app/vouchers/entry/page';
import { pageContext } from '../app/lib/page-context';
import { companyContextFor, sessionFor } from './helpers';
vi.mock('../app/lib/page-context', () => ({ pageContext: vi.fn() }));
vi.mock('../app/providers', () => ({ Providers: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/components/ConsoleShell', () => ({ ConsoleShell: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/components/VoucherDraftEditor', () => ({ VoucherDraftEditor: () => <p>Native draft editor</p> }));
vi.mock('../app/components/VoucherEntry', () => ({ VoucherEntry: () => <p>Native draft entry</p> }));
vi.mock('next/navigation', () => ({ notFound: () => { throw new Error('404'); } }));
const company = '10000000-0000-7000-8000-000000000001', voucherId = '10000000-0000-7000-8000-000000000002';
it.each([true, false])('scopes entry and edit permissions to the current company (%s)', async allowed => {
  const session = await sessionFor({permissions:['vouchers.read','vouchers.create','vouchers.edit']}); session.company = { id: company, name: 'QA' };
  session.grants = [{ scope_type: 'company', scope_id: allowed ? company : voucherId, permissions: ['vouchers.read', 'vouchers.edit', 'vouchers.create'], valid_from: '2000-01-01', valid_to: null }];
  vi.mocked(pageContext).mockResolvedValue({ session, context: companyContextFor() });
  render(await EditPage({ params: Promise.resolve({ voucherId }), searchParams: Promise.resolve({ type_id: company }) }));
  if (allowed) expect(screen.getByText('Native draft editor')).toBeVisible(); else expect(screen.getByRole('alert')).toBeVisible();
});
it('requires scoped creation access for the generic entry continuation', async () => {
  const session = await sessionFor({permissions:['vouchers.read','vouchers.create']}); session.company = { id: company, name: 'QA' };
  session.grants = [{ scope_type: 'company', scope_id: company, permissions: ['vouchers.read', 'vouchers.create'], valid_from: '2000-01-01', valid_to: null }];
  vi.mocked(pageContext).mockResolvedValue({ session, context: companyContextFor() });
  render(await EntryPage({})); expect(screen.getByText('Native draft entry')).toBeVisible();
});
it('explains that a company must be opened before entry',async()=>{
  const session=await sessionFor();session.company={name:'No open company'};
  vi.mocked(pageContext).mockResolvedValue({session,context:companyContextFor()});
  render(await EntryPage({}));expect(screen.getByText(/No company is open/)).toBeVisible();
});
it.each([{ voucherId: '../escape', type_id: company }, { voucherId, type_id: 'bad' }])('rejects invalid route identities', async value => {
  await expect(EditPage({ params: Promise.resolve({ voucherId: value.voucherId }), searchParams: Promise.resolve({ type_id: value.type_id }) })).rejects.toThrow('404');
});
