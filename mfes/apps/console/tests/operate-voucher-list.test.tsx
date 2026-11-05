import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { OperateVoucherList } from '../app/components/OperateVoucherList';
import { VoucherDirectory } from '../app/components/VoucherDirectory';
import { OPERATE_AREAS, listHref, newVoucherHref, withReturn } from '../app/lib/operate-navigation';
import { VOUCHER_KINDS } from '../app/lib/voucher-kinds';
import { serviceCall } from '../app/lib/service-call';

vi.mock('../app/lib/service-call', async original => ({ ...await original<typeof import('../app/lib/service-call')>(), serviceCall: vi.fn() }));
const company = '10000000-0000-7000-8000-000000000001', typeId = '10000000-0000-7000-8000-000000000002', voucher = '10000000-0000-7000-8000-000000000003';
const page = { items: [], page: { limit: 25, has_more: false, next_cursor: null } };
const area = OPERATE_AREAS[1], family = area.families[0];
const permissions = ['vouchers.read', 'vouchers.create', 'vouchers.edit', 'vouchers.import.read'];
beforeEach(() => { vi.mocked(serviceCall).mockReset(); vi.mocked(serviceCall).mockResolvedValue(page); });

it.each(VOUCHER_KINDS)('provides a bounded $value list with New and Import links', async ({ value: kind }) => {
  const owner = OPERATE_AREAS.find(area => area.families.some(family => family.kinds.includes(kind)))!;
  const group = owner.families.find(family => family.kinds.includes(kind))!;
  render(<OperateVoucherList company={company} permissions={permissions} area={owner} family={group} kind={kind} />);
  await screen.findByText('No saved vouchers match');
  const path = vi.mocked(serviceCall).mock.calls[0][1].path;
  const filters = new URL(path, 'https://console.invalid').searchParams;
  expect(path).toContain('/companies/' + company + '/vouchers?');
  expect(filters.get('kind')).toBe(kind); expect(filters.get('limit')).toBe('25');
  expect(filters.has('status')).toBe(false);
  expect(screen.getByRole('link', { name: 'New voucher' })).toHaveAttribute('href', newVoucherHref(kind, undefined, listHref(owner, group, kind)));
  expect(screen.getByRole('link', { name: 'Import voucher' })).toHaveAttribute('href', withReturn('/vouchers/import?kind=' + kind, listHref(owner, group, kind)));
  expect(screen.getByRole('searchbox', { name: 'Search voucher number' })).toBeInTheDocument();
  expect(screen.getByLabelText('Status')).toHaveValue('');
});
it('verifies an exact type before fetching its list and preserves review/edit return links', async () => {
  vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => request.path.includes('/voucher-types/')
    ? { id: typeId, company_id: company, kind: 'PURCHASE', name: 'Local supplier bills' }
    : { ...page, items: [{ id: voucher, company_id: company, row_version: 1, type_id: typeId, type_code: 'LP', kind: 'PURCHASE', profile: 'STANDARD', status: 'DRAFT' }] });
  render(<OperateVoucherList company={company} permissions={permissions} area={area} family={family} kind="PURCHASE" typeId={typeId} />);
  await screen.findByText('LP');
  const calls = vi.mocked(serviceCall).mock.calls;
  expect(calls[0][1].path).toContain('/voucher-types/' + typeId);
  expect(new URL(calls[1][1].path, 'https://console.invalid').searchParams.get('type_id')).toBe(typeId);
  expect(screen.getByRole('heading', { name: 'Local supplier bills vouchers' })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /actions/i }));
  const back = listHref(area, family, 'PURCHASE', typeId);
  expect(screen.getByRole('menuitem', { name: 'Review voucher' })).toHaveAttribute('href', withReturn('/vouchers/' + voucher, back));
  // A Purchase is edited on its one entry screen, where its tax, terms and approval are, not in the generic draft editor.
  expect(screen.getByRole('menuitem', { name: 'Edit draft' })).toHaveAttribute('href', withReturn('/vouchers/new/purchase?voucher_id=' + voucher + '&type_id=' + typeId, back));
});
it.each([{ company_id: voucher, kind: 'PURCHASE' }, { company_id: company, kind: 'SALES' }, { id: voucher, company_id: company, kind: 'PURCHASE' }])('does not fetch vouchers for a mismatched type %j', async overrides => {
  vi.mocked(serviceCall).mockResolvedValue(Object.assign({ id: typeId, company_id: company, kind: 'PURCHASE' }, overrides));
  render(<OperateVoucherList company={company} permissions={permissions} area={area} family={family} kind="PURCHASE" typeId={typeId} />);
  await waitFor(() => expect(screen.queryByText('Loading voucher type…')).not.toBeInTheDocument());
  expect(vi.mocked(serviceCall).mock.calls).toHaveLength(1);
  expect(screen.queryByRole('link', { name: 'New voucher' })).not.toBeInTheDocument();
  expect(screen.queryByRole('table')).not.toBeInTheDocument();
});
it('retries a failed type read before enabling a list', async () => {
  vi.mocked(serviceCall).mockRejectedValueOnce({ status: 503, message: 'Temporarily unavailable' });
  render(<OperateVoucherList company={company} permissions={permissions} area={area} family={family} kind="PURCHASE" typeId={typeId} />);
  await screen.findByText('Temporarily unavailable');
  vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => request.path.includes('/voucher-types/') ? { id: typeId, company_id: company, kind: 'PURCHASE' } : page);
  fireEvent.click(screen.getByRole('button', { name: 'Retry voucher type' }));
  await screen.findByText('No saved vouchers match');
});
it('keeps kind/type filters while applying search, status and signed-cursor paging', async () => {
  vi.mocked(serviceCall).mockResolvedValue({ ...page, page: { ...page.page, has_more: true, next_cursor: 'signed-next' } });
  render(<VoucherDirectory company={company} permissions={permissions} scope={{ kind: 'PURCHASE', typeId, title: 'Purchase', href: listHref(area, family, 'PURCHASE', typeId) }} />);
  await waitFor(() => expect(screen.getByRole('button', { name: /next/i })).toBeEnabled());
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'PB-001' } }); fireEvent.keyDown(screen.getByRole('searchbox'), { key: 'Enter' });
  fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'POSTED' } });
  await waitFor(() => expect(vi.mocked(serviceCall).mock.calls.at(-1)![1].path).toContain('status=POSTED'));
  fireEvent.click(screen.getByRole('button', { name: /next/i }));
  await waitFor(() => expect(vi.mocked(serviceCall).mock.calls.at(-1)![1].path).toContain('cursor=signed-next'));
  const query = new URL(vi.mocked(serviceCall).mock.calls.at(-1)![1].path, 'https://console.invalid').searchParams;
  expect(query.get('kind')).toBe('PURCHASE'); expect(query.get('type_id')).toBe(typeId); expect(query.get('q')).toBe('PB-001');
});
it.each([{ kind: 'SALES', type_id: typeId }, { kind: 'PURCHASE', type_id: voucher }])('refuses a voucher outside the requested kind/type %j', async fields => {
  vi.mocked(serviceCall).mockResolvedValue({ ...page, items: [{ id: voucher, company_id: company, row_version: 1, type_code: 'Wrong voucher', ...fields }] });
  render(<VoucherDirectory company={company} permissions={permissions} scope={{ kind: 'PURCHASE', typeId, title: 'Purchase', href: listHref(area, family, 'PURCHASE', typeId) }} />);
  await screen.findByText('The voucher list could not be verified for this company.');
  expect(screen.queryByText('Wrong voucher')).not.toBeInTheDocument();
});
it('withholds New and Import controls without their respective permissions', async () => {
  render(<OperateVoucherList company={company} permissions={['vouchers.read']} area={area} family={family} kind="PURCHASE" />);
  await screen.findByText('No saved vouchers match');
  expect(screen.queryByRole('link', { name: 'New voucher' })).not.toBeInTheDocument();
  expect(screen.queryByRole('link', { name: 'Import voucher' })).not.toBeInTheDocument();
  expect(screen.getByText(/Read-only access/)).toBeInTheDocument();
});
