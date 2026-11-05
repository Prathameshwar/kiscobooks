import { render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { pageContext } from '../app/lib/page-context';
import { companyContextFor, sessionFor } from './helpers';
import Page from '../app/vouchers/[voucherId]/print/page';

vi.mock('../app/lib/page-context', () => ({ pageContext: vi.fn() }));
vi.mock('../app/providers', () => ({ Providers: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/components/ConsoleShell', () => ({ ConsoleShell: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/components/PurchasePrintPreview', () => ({ PurchasePrintPreview: (props: unknown) => <p>Print {JSON.stringify(props)}</p> }));

const id = '01990000-0000-7000-8000-000000000001';
const required = ['vouchers.read', 'vouchers.artifact.create', 'vouchers.artifact.read', 'accounting.account.read'];
async function setup(permissions = required, scope = id) {
  const session = await sessionFor({ permissions });
  session.company = { id, name: 'Print company' };
  session.grants = [{ scope_type: 'company', scope_id: scope, permissions, valid_from: '2020-01-01', valid_to: null }];
  vi.mocked(pageContext).mockResolvedValue({ session, context: companyContextFor() });
}
const props = { params: Promise.resolve({ voucherId: id }), searchParams: Promise.resolve({ revision: id, version: '2' }) };

it('opens one saved Purchase print under the selected company', async () => {
  await setup();
  render(await Page(props));
  expect(screen.getByText(/^Print /)).toHaveTextContent(JSON.stringify({ company: id, voucherId: id, revisionId: id, version: 2 }));
});
it.each(required)('requires %s as well as the other print permissions', async missing => {
  await setup(required.filter(key => key !== missing));
  render(await Page(props));
  expect(screen.queryByText(/^Print /)).not.toBeInTheDocument();
});
it('refuses another company grant and an unidentified revision', async () => {
  await setup(required, '01990000-0000-7000-8000-000000000002');
  const view = render(await Page(props));
  expect(screen.queryByText(/^Print /)).not.toBeInTheDocument();
  view.unmount();
  await setup();
  render(await Page({ ...props, searchParams: Promise.resolve({ revision: '../invalid', version: '2' }) }));
  expect(screen.queryByText(/^Print /)).not.toBeInTheDocument();
});
