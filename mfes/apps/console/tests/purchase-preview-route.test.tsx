import { render, screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import Page from '../app/vouchers/new/purchase-preview/page';
import { pageContext } from '../app/lib/page-context';
import { companyContextFor, sessionFor } from './helpers';

vi.mock('../app/lib/page-context', () => ({ pageContext: vi.fn() }));
vi.mock('../app/providers', () => ({ Providers: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/components/ConsoleShell', () => ({ ConsoleShell: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/components/NoCompany', () => ({ NoCompany: () => <p>Select a company first</p> }));
vi.mock('../app/components/PurchaseWorkflowWorkspace', () => ({ PurchaseWorkflowWorkspace: ({ permissions, context }: { permissions: { create: boolean; edit: boolean; submit: boolean }; context: { company: string; year: string } }) => <p data-company={context.company} data-year={context.year} data-edit={permissions.edit} data-submit={permissions.submit}>Purchase preview {permissions.create ? 'edit' : 'read only'}</p> }));
const company = '01990000-0000-7000-8000-000000000001';
beforeEach(async () => {
  const session = await sessionFor({ permissions: ['vouchers.read', 'vouchers.create'] });
  session.company = { id: company, name: 'QA Company' };
  session.grants = [{ scope_type: 'company', scope_id: company, permissions: session.permissions, valid_from: '2020-01-01', valid_to: null }];
  vi.mocked(pageContext).mockResolvedValue({ session, context: companyContextFor() });
});
it('mounts an authenticated preview for the selected company', async () => {
  render(await Page()); expect(screen.getByText('Purchase preview edit')).toBeVisible();
});
it('offers review only when create is unavailable', async () => {
  const resolved = await pageContext(); resolved.session.permissions = ['vouchers.read']; resolved.session.grants![0].permissions = ['vouchers.read'];
  render(await Page()); expect(screen.getByText('Purchase preview read only')).toBeVisible();
});
it('does not mount the workspace for grants held only in another company', async () => {
  const resolved = await pageContext(); resolved.session.grants![0].scope_id = '01990000-0000-7000-8000-000000000002';
  render(await Page()); expect(screen.getByText('Purchase access required')).toBeVisible();
  expect(screen.queryByText(/Purchase preview/)).not.toBeInTheDocument();
});
it('requires a company before constructing a draft', async () => {
  const resolved = await pageContext(); resolved.session.company = { name: '' };
  render(await Page()); expect(screen.getByText('Select a company first')).toBeVisible();
});
it('passes edit and submit permissions only for the selected company/year', async () => {
  const resolved = await pageContext();
  resolved.session.grants![0].permissions = ['vouchers.read', 'vouchers.create', 'vouchers.edit', 'vouchers.submit'];
  resolved.context.fiscalYear = { id: 'year-2026', code: '2026-27', startDate: '2026-04-01', endDate: '2027-03-31', current: true, open: true };
  render(await Page());
  const preview = screen.getByText('Purchase preview edit');
  expect(preview).toHaveAttribute('data-company', company);
  expect(preview).toHaveAttribute('data-year', 'year-2026');
  expect(preview).toHaveAttribute('data-edit', 'true'); expect(preview).toHaveAttribute('data-submit', 'true');
});
