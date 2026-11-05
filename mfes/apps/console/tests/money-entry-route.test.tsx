import { render, screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import Page, { generateMetadata } from '../app/vouchers/new/[kind]/page';
import { pageContext } from '../app/lib/page-context';
import { companyContextFor, sessionFor } from './helpers';

vi.mock('../app/lib/page-context', () => ({ pageContext: vi.fn() }));
vi.mock('../app/providers', () => ({ Providers: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/components/ConsoleShell', () => ({ ConsoleShell: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/components/VoucherEntry', () => ({ VoucherEntry: ({ company, initialKind, canCreate, permissions }: { company: string; initialKind: string; canCreate: boolean; permissions: string[] }) => <p>Native entry {company} {initialKind} {canCreate ? 'create' : 'read'} {permissions.join(',')}</p> }));
vi.mock('../app/components/SalesEntryConnected', () => ({ SalesEntryConnected: () => <p>Connected Sales</p> }));
vi.mock('../app/components/PurchaseEntryConnected', () => ({ PurchaseEntryConnected: ({ company, canCreate }: { company: string; canCreate: boolean }) => <p>Connected Purchase {company} {canCreate ? 'create' : 'read'}</p> }));
vi.mock('next/navigation', () => ({ notFound: () => { throw Error('not found'); } }));
const company = '01990000-0000-7000-8000-000000000001';
beforeEach(async () => {
  const session = await sessionFor({ permissions: ['vouchers.read', 'vouchers.create'] });
  session.company = { id: company, name: 'QA Company' };
  session.grants = [{ scope_type: 'company', scope_id: company, permissions: session.permissions, valid_from: '2020-01-01', valid_to: null }];
  vi.mocked(pageContext).mockResolvedValue({ session, context: companyContextFor() });
});

it.each(['receipt', 'payment'])('opens %s through native kind-bound capture instead of a placeholder', async kind => {
  render(await Page({ params: Promise.resolve({ kind }) }));
  expect(screen.getByText(new RegExp('Native entry ' + company + ' ' + kind.toUpperCase() + ' create'))).toBeVisible();
  expect(screen.queryByText(/not built yet/)).not.toBeInTheDocument();
});
it('opens Purchase through the approved workspace with live owner APIs', async () => {
  render(await Page({ params: Promise.resolve({ kind: 'purchase' }) }));
  expect(screen.getByText('Connected Purchase ' + company + ' create')).toBeVisible();
});

it('opens stock adjustment through the native physical-count profile', async () => {
  render(await Page({params:Promise.resolve({kind:'stock-adjustment'})}));
  expect(screen.getByText(new RegExp('Native entry '+company+' PHYSICAL_STOCK create'))).toBeVisible();
  expect(screen.queryByText(/not built yet/)).not.toBeInTheDocument();
});

it('refuses creation permissions held only for another company', async () => {
  const { session, context } = await pageContext();
  session.grants![0].scope_id = '01990000-0000-7000-8000-000000000002';
  vi.mocked(pageContext).mockResolvedValue({ session, context });
  render(await Page({ params: Promise.resolve({ kind: 'receipt' }) }));
  expect(screen.getByRole('alert')).toHaveTextContent(/access is required/i);
  expect(screen.queryByText(/Native entry/)).not.toBeInTheDocument();
  expect(screen.queryByText(/vouchers.create/)).not.toBeInTheDocument();
});

it.each(['sales', 'purchase', 'receipt', 'payment', 'stock-adjustment'])('denies a new %s to a read-only user before mounting the entry', async kind => {
  const value = await pageContext();
  value.session.permissions = ['vouchers.read'];
  value.session.grants![0].permissions = ['vouchers.read'];
  render(await Page({ params: Promise.resolve({ kind }) }));
  expect(screen.getByRole('alert')).toHaveTextContent(/access is required/i);
  expect(screen.queryByText(/Connected|Native entry/)).not.toBeInTheDocument();
});

it('allows a read-only reviewer to open a saved Purchase', async () => {
  const value = await pageContext();
  value.session.permissions = ['vouchers.read'];
  value.session.grants![0].permissions = ['vouchers.read'];
  render(await Page({ params: Promise.resolve({ kind: 'purchase' }), searchParams: Promise.resolve({ voucher_id: company }) }));
  expect(screen.getByText('Connected Purchase ' + company + ' read')).toBeVisible();
});

it.each(['sales', 'receipt', 'payment', 'stock-adjustment'])('does not bypass %s creation access with a Purchase resume parameter', async kind => {
  const value = await pageContext();
  value.session.permissions = ['vouchers.read']; value.session.grants![0].permissions = ['vouchers.read'];
  render(await Page({ params: Promise.resolve({ kind }), searchParams: Promise.resolve({ voucher_id: company }) }));
  expect(screen.getByRole('alert')).toBeVisible();
  expect(screen.queryByText(/Connected|Native entry/)).not.toBeInTheDocument();
});

it('requires read access even when creation is granted', async () => {
  const value = await pageContext();
  value.session.permissions = ['vouchers.create'];
  value.session.grants![0].permissions = ['vouchers.create'];
  render(await Page({ params: Promise.resolve({ kind: 'purchase' }) }));
  expect(screen.getByRole('alert')).toBeVisible();
  expect(screen.queryByText(/Connected Purchase/)).not.toBeInTheDocument();
});

it('asks for company selection before mounting a new voucher', async () => {
  const value = await pageContext(); value.session.company = { name: 'Select company' };
  render(await Page({ params: Promise.resolve({ kind: 'receipt' }) }));
  expect(screen.getByText(/No company is open/)).toBeVisible();
  expect(screen.queryByText(/Connected|Native entry/)).not.toBeInTheDocument();
});
it('does not open a saved Purchase using another company grant', async () => {
  const value = await pageContext(); value.session.grants![0].scope_id = '01990000-0000-7000-8000-000000000002';
  render(await Page({ params: Promise.resolve({ kind: 'purchase' }), searchParams: Promise.resolve({ voucher_id: company }) }));
  expect(screen.getByRole('alert')).toHaveTextContent(/read access is required/);
  expect(screen.queryByText(/Connected Purchase/)).not.toBeInTheDocument();
});
it('rejects malformed saved Purchase identities and unknown metadata kinds', async () => {
  await expect(Page({ params: Promise.resolve({ kind: 'purchase' }), searchParams: Promise.resolve({ voucher_id: 'bad' }) })).rejects.toThrow('not found');
  await expect(generateMetadata({ params: Promise.resolve({ kind: 'bad' }) })).rejects.toThrow('not found');
});

it('keeps the existing connected Sales route', async () => {
  render(await Page({ params: Promise.resolve({ kind: 'sales' }) }));
  expect(screen.getByText('Connected Sales')).toBeVisible();
});

it('rejects an unoffered voucher kind', async () => {
  await expect(Page({ params: Promise.resolve({ kind: 'arbitrary' }) })).rejects.toThrow('not found');
});

it.each(['receipt', 'payment'])('uses the selected %s kind in the browser title', async kind => {
  expect((await generateMetadata({ params: Promise.resolve({ kind }) })).title).toBe('New ' + kind + ' · KiscoBooks');
});
