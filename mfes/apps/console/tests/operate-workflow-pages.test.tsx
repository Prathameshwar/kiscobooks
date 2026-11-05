import { render, screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import ListPage from '../app/operate/[area]/[family]/[kind]/page';
import EntryPage from '../app/vouchers/entry/page';
import ImportPage from '../app/vouchers/import/page';
import DetailPage from '../app/vouchers/[voucherId]/page';
import PrintPage from '../app/documents/vouchers/[kind]/page';
import EditPage from '../app/vouchers/[voucherId]/edit/page';
import { pageContext } from '../app/lib/page-context';
import { OPERATE_AREAS, listHref } from '../app/lib/operate-navigation';
import { VOUCHER_KINDS, kindSlug } from '../app/lib/voucher-kinds';
import { companyContextFor, sessionFor } from './helpers';

vi.mock('../app/lib/page-context', () => ({ pageContext: vi.fn() }));
vi.mock('../app/providers', () => ({ Providers: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/components/ConsoleShell', () => ({ ConsoleShell: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/components/OperateVoucherList', () => ({ OperateVoucherList: (props: Record<string, unknown>) => <p>List {JSON.stringify(props)}</p> }));
vi.mock('../app/components/VoucherEntry', () => ({ VoucherEntry: (props: Record<string, unknown>) => <p>Entry {JSON.stringify(props)}</p> }));
vi.mock('../app/components/SalesEntryConnected', () => ({ SalesEntryConnected: ({ navigation, ...props }: { navigation?: React.ReactNode }) => <>{navigation}<p>Entry {JSON.stringify(props)}</p></> }));
vi.mock('../app/components/PurchaseEntryConnected', () => ({ PurchaseEntryConnected: (props: Record<string, unknown>) => <p>Entry {JSON.stringify(props)}</p> }));
vi.mock('../app/components/VoucherImportLanding', () => ({ VoucherImportLanding: (props: Record<string, unknown>) => <p>Import {JSON.stringify(props)}</p> }));
vi.mock('../app/components/VoucherWorkflow', () => ({ VoucherWorkflow: () => <p>Saved workflow</p> }));
vi.mock('../app/components/VoucherPrintKind', () => ({ VoucherPrintKind: (props: Record<string, unknown>) => <p>Print {JSON.stringify(props)}</p> }));
vi.mock('../app/components/VoucherDraftEditor', () => ({ VoucherDraftEditor: (props: Record<string, unknown>) => <p>Edit {JSON.stringify(props)}</p> }));
vi.mock('next/navigation', () => ({ notFound: () => { throw new Error('NEXT_NOT_FOUND'); }, redirect: (url: string) => { throw new Error('NEXT_REDIRECT ' + url); } }));
const company = '10000000-0000-7000-8000-000000000001', typeId = '10000000-0000-7000-8000-000000000002';
const area = OPERATE_AREAS[1], family = area.families[0], back = listHref(area, family, 'PURCHASE', typeId);
beforeEach(async () => {
  vi.mocked(pageContext).mockReset();
  const permissions = ['vouchers.read', 'vouchers.create', 'vouchers.edit', 'vouchers.import.read', 'design.template.read'];
  const session = await sessionFor({ permissions }); session.company = { id: company, name: 'Company' };
  session.grants = [{ scope_type: 'company', scope_id: company, permissions, valid_from: '2000-01-01', valid_to: null }];
  vi.mocked(pageContext).mockResolvedValue({ session, context: companyContextFor() });
});
it.each(VOUCHER_KINDS)('resolves $value into its own list page', async ({ value: kind }) => {
  const owner = OPERATE_AREAS.find(area => area.families.some(family => family.kinds.includes(kind)))!;
  const family = owner.families.find(family => family.kinds.includes(kind))!;
  render(await ListPage({ params: Promise.resolve({ area: owner.key, family: family.key, kind: kindSlug(kind) }), searchParams: Promise.resolve({ type_id: typeId }) }));
  expect(screen.getByText(/^List /)).toHaveTextContent('"kind":"' + kind + '"');
  expect(screen.getByText(/^List /)).toHaveTextContent('"typeId":"' + typeId + '"');
});
it.each(VOUCHER_KINDS)('denies direct $value lists when read belongs to another company', async ({ value: kind }) => {
  const { session } = await pageContext(); session.grants![0].scope_id = typeId;
  const owner = OPERATE_AREAS.find(area => area.families.some(family => family.kinds.includes(kind)))!;
  const family = owner.families.find(family => family.kinds.includes(kind))!;
  render(await ListPage({ params: Promise.resolve({ area: owner.key, family: family.key, kind: kindSlug(kind) }) }));
  expect(screen.getByRole('alert')).toHaveTextContent('Voucher read access is required');
  expect(screen.queryByText(/^List /)).not.toBeInTheDocument();
});
it.each([
  { role: 'tenant_admin', scope: 'tenant' as const, keys: ['vouchers.read', 'vouchers.type.manage', 'design.template.read'], create: false, imported: false, print: true },
  { role: 'company_admin', scope: 'company' as const, keys: ['vouchers.read', 'vouchers.type.manage', 'design.template.read'], create: false, imported: false, print: true },
  { role: 'purchase_clerk', scope: 'company' as const, keys: ['vouchers.read', 'vouchers.create', 'vouchers.edit', 'vouchers.submit', 'vouchers.import.read', 'vouchers.import.manage', 'vouchers.import.commit'], create: true, imported: true, print: false },
  { role: 'billing_approver', scope: 'company' as const, keys: ['vouchers.read', 'vouchers.approve', 'vouchers.reject', 'design.template.read'], create: false, imported: false, print: true },
  { role: 'viewer', scope: 'company' as const, keys: ['vouchers.read', 'design.template.read'], create: false, imported: false, print: true },
  { role: 'tenant_auditor', scope: 'tenant' as const, keys: ['vouchers.read', 'design.template.read', 'vouchers.import.read'], create: false, imported: true, print: true },
])('checks new/import/print pages independently for the $role permission bundle', async row => {
  const { session } = await pageContext(); session.permissions = row.keys;
  session.grants = [{ scope_type: row.scope, scope_id: row.scope === 'tenant' ? null : company, permissions: row.keys, valid_from: '2000-01-01', valid_to: null }];
  const entry = render(await EntryPage({ searchParams: Promise.resolve({ kind: 'RECEIPT' }) }));
  expect(!!screen.queryByText(/^Entry /)).toBe(row.create); entry.unmount();
  const imported = render(await ImportPage({ searchParams: Promise.resolve({ kind: 'PURCHASE' }) }));
  expect(!!screen.queryByText(/^Import /)).toBe(row.imported); imported.unmount();
  render(await PrintPage({ params: Promise.resolve({ kind: 'purchase' }) }));
  expect(!!screen.queryByText(/^Print /)).toBe(row.print);
});
it.each([{ area: 'income', family: 'purchase', kind: 'purchase' }, { area: 'expense', family: 'purchase', kind: 'sales' }, { area: 'inventory', family: 'stock', kind: 'bad' }])('rejects inconsistent route %j before reading the session', async params => {
  await expect(ListPage({ params: Promise.resolve(params) })).rejects.toThrow('NEXT_NOT_FOUND');
  expect(pageContext).not.toHaveBeenCalled();
});
it.each(['not-an-id', ['duplicate', 'id']])('rejects invalid type identity %j', async type_id => {
  await expect(ListPage({ params: Promise.resolve({ area: 'expense', family: 'purchase', kind: 'purchase' }), searchParams: Promise.resolve({ type_id }) })).rejects.toThrow('NEXT_NOT_FOUND');
});
it('preserves kind, exact type and back link in the import landing', async () => {
  render(await ImportPage({ searchParams: Promise.resolve({ kind: 'PURCHASE', type_id: typeId, returnTo: back }) }));
  const text = screen.getByText(/^Import /);
  expect(text).toHaveTextContent('"typeId":"' + typeId + '"');
  expect(text).toHaveTextContent('"returnTo":"' + back + '"');
});
it('preserves kind, exact type and back target in the generic entry', async () => {
  const receipts = OPERATE_AREAS[0].families.find(group => group.kinds.includes('RECEIPT'))!, receiptBack = listHref(OPERATE_AREAS[0], receipts, 'RECEIPT', typeId);
  render(await EntryPage({ searchParams: Promise.resolve({ kind: 'RECEIPT', type_id: typeId, returnTo: receiptBack }) }));
  const text = screen.getByText(/^Entry /);
  expect(text).toHaveTextContent('"initialKind":"RECEIPT"'); expect(text).toHaveTextContent('"initialTypeId":"' + typeId + '"'); expect(text).toHaveTextContent('"returnTo":"' + receiptBack + '"');
});
it.each(['SALES', 'PURCHASE'])('sends %s to its one entry screen with the exact type and back target', async kind => {
  const target = kind === 'SALES' ? '/vouchers/new/sales' : '/vouchers/new/purchase';
  const owner = OPERATE_AREAS.find(candidate => candidate.families.some(group => group.kinds.includes(kind)))!, group = owner.families.find(candidate => candidate.kinds.includes(kind))!;
  const returnTo = listHref(owner, group, kind, typeId);
  await expect(EntryPage({ searchParams: Promise.resolve({ kind, type_id: typeId, returnTo }) })).rejects.toThrow('NEXT_REDIRECT ' + target + '?type_id=' + typeId + '&returnTo=' + encodeURIComponent(returnTo));
  await expect(EntryPage({ searchParams: Promise.resolve({ kind }) })).rejects.toThrow('NEXT_REDIRECT ' + target);
  expect(pageContext).not.toHaveBeenCalled();
});
it('drops an unsafe back target instead of carrying it to the entry screen', async () => {
  await expect(EntryPage({ searchParams: Promise.resolve({ kind: 'PURCHASE', returnTo: 'https://evil.example/' }) })).rejects.toThrow(/^NEXT_REDIRECT \/vouchers\/new\/purchase$/);
});
it.each([{ kind: 'sales' }, { kind: 'UNKNOWN' }, { kind: ['PURCHASE'] }, { type_id: typeId }, { kind: 'PURCHASE', type_id: '../escape' }])('rejects invalid New/Import selection %j', async query => {
  await expect(EntryPage({ searchParams: Promise.resolve(query) })).rejects.toThrow('NEXT_NOT_FOUND');
  await expect(ImportPage({ searchParams: Promise.resolve(query) })).rejects.toThrow('NEXT_NOT_FOUND');
  expect(pageContext).not.toHaveBeenCalled();
});
it('refuses import and entry without their live company grants', async () => {
  const context = await pageContext(); context.session.permissions = ['vouchers.read']; context.session.grants![0].permissions = ['vouchers.read'];
  render(await ImportPage({}));
  expect(screen.getByText(/Voucher import read access is required/)).toBeInTheDocument();
});
it('preserves an Operate list return from voucher review', async () => {
  render(await DetailPage({ params: Promise.resolve({ voucherId: company }), searchParams: Promise.resolve({ returnTo: back }) }));
  expect(screen.getByRole('link', { name: /Back to voucher list/ })).toHaveAttribute('href', back);
});
it('passes a safe return through draft editing and print configuration', async () => {
  render(await EditPage({ params: Promise.resolve({ voucherId: company }), searchParams: Promise.resolve({ type_id: typeId, returnTo: back }) }));
  expect(screen.getByText(/^Edit /)).toHaveTextContent('"returnTo":"' + back + '"');
  render(await PrintPage({ params: Promise.resolve({ kind: 'purchase' }), searchParams: Promise.resolve({ returnTo: '/operate/expense/purchase' }) }));
  expect(screen.getByText(/^Print /)).toHaveTextContent('"returnTo":"/operate/expense/purchase"');
});
