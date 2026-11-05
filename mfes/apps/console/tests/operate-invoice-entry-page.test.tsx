import { render, screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import NewVoucherPage from '../app/vouchers/new/[kind]/page';
import { pageContext } from '../app/lib/page-context';
import { OPERATE_AREAS, listHref } from '../app/lib/operate-navigation';
import { companyContextFor, sessionFor } from './helpers';

/*
 * Sales and Purchase have exactly one entry screen, `/vouchers/new/<kind>`. An Operate list opens it
 * for one company voucher type and tells it where Back goes; this is the screen's side of that.
 */
vi.mock('../app/lib/page-context', () => ({ pageContext: vi.fn() }));
vi.mock('../app/providers', () => ({ Providers: ({ children }: { children: React.ReactNode }) => children }));
const shell = vi.fn();
vi.mock('../app/components/ConsoleShell', () => ({ ConsoleShell: ({ children, ...props }: { children: React.ReactNode }) => { shell(props); return children; } }));
vi.mock('../app/components/VoucherEntry', () => ({ VoucherEntry: () => <p>Generic draft entry</p> }));
vi.mock('../app/components/SalesEntryConnected', () => ({ SalesEntryConnected: ({ navigation, ...props }: { navigation?: React.ReactNode }) => <>{navigation}<p>Sales invoice {JSON.stringify(props)}</p></> }));
vi.mock('../app/components/PurchaseEntryConnected', () => ({ PurchaseEntryConnected: ({ navigation, ...props }: { navigation?: React.ReactNode }) => <>{navigation}<p>Purchase invoice {JSON.stringify(props)}</p></> }));
vi.mock('next/navigation', () => ({ notFound: () => { throw new Error('NEXT_NOT_FOUND'); } }));
const company = '10000000-0000-7000-8000-000000000001', typeId = '10000000-0000-7000-8000-000000000002';
const listFor = (kind: string) => { const area = OPERATE_AREAS.find(candidate => candidate.families.some(group => group.kinds.includes(kind)))!; return listHref(area, area.families.find(group => group.kinds.includes(kind))!, kind, typeId); };
beforeEach(async () => {
  shell.mockClear();
  const permissions = ['vouchers.read', 'vouchers.create']; const session = await sessionFor({ permissions });
  session.company = { id: company, name: 'Company' }; session.grants = [{ scope_type: 'company', scope_id: company, permissions, valid_from: '2000-01-01', valid_to: null }];
  vi.mocked(pageContext).mockResolvedValue({ session, context: companyContextFor() });
});
const open = async (kind: string, query: Record<string, string | string[]> = {}) => render(await NewVoucherPage({ params: Promise.resolve({ kind }), searchParams: Promise.resolve(query) }));

it.each([['sales', 'SALES', /^Sales invoice/], ['purchase', 'PURCHASE', /^Purchase invoice/]] as const)('opens the one %s screen for the exact type, with a way back to its list', async (slug, kind, text) => {
  const back = listFor(kind);
  await open(slug, { type_id: typeId, returnTo: back });
  expect(screen.getByText(text)).toHaveTextContent('"initialTypeId":"' + typeId + '"');
  expect(screen.queryByText('Generic draft entry')).not.toBeInTheDocument();
  expect(screen.getByRole('link', { name: /Back to voucher list/ })).toHaveAttribute('href', back);
  // the rail marks the list the reader came from, not the New menu
  expect(shell).toHaveBeenCalledWith(expect.objectContaining({ activeHref: back }));
});

it.each(['sales', 'purchase'])('opens the %s screen as before when it is reached without a selection', async slug => {
  await open(slug);
  expect(screen.getByText(/invoice/)).not.toHaveTextContent('initialTypeId');
  expect(screen.queryByRole('link', { name: /Back to voucher list/ })).not.toBeInTheDocument();
  expect(shell).toHaveBeenCalledWith(expect.objectContaining({ activeHref: '/vouchers/new/' + slug }));
});

it('drops a back target that is not a known Operate list, keeping the type', async () => {
  await open('purchase', { type_id: typeId, returnTo: 'https://evil.example/' });
  expect(screen.getByText(/^Purchase invoice/)).toHaveTextContent('"initialTypeId":"' + typeId + '"');
  expect(screen.queryByRole('link', { name: /Back to/ })).not.toBeInTheDocument();
});

it.each([{ type_id: 'not-an-id' }, { type_id: ['a', 'b'] }, { type_id: '../escape' }])('treats an unusable type %j as not found', async query => {
  await expect(open('purchase', query)).rejects.toThrow('NEXT_NOT_FOUND');
  await expect(open('sales', query)).rejects.toThrow('NEXT_NOT_FOUND');
});

it('still resumes a saved purchase by voucher id, with or without a back target', async () => {
  const draft = '10000000-0000-7000-8000-000000000003';
  await open('purchase', { voucher_id: draft });
  expect(screen.getByText(/^Purchase invoice/)).toHaveTextContent('"initialVoucherId":"' + draft + '"');
});

it.each(['receipt', 'payment', 'stock-adjustment'])('ignores a type on the generic %s screen', async slug => {
  await open(slug, { type_id: typeId });
  expect(screen.getByText('Generic draft entry')).toBeVisible();
});
