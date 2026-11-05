import { render, screen, within } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { AccountingConfigurationDirectory } from '../app/components/AccountingConfigurationDirectory';
import { accountingResource } from '../app/lib/accounting-configuration-resources';
import { serviceCall } from '../app/lib/service-call';
import { COMPANY, ID, form, page } from './accounting-configuration-fixtures';

vi.mock('../app/lib/service-call', async original => ({
  ...await original<typeof import('../app/lib/service-call')>(), serviceCall: vi.fn(),
}));
beforeEach(() => { vi.clearAllMocks(); window.history.replaceState(null, '', '/accounting'); });

async function directory(partyType: string | null, roles: string[] | undefined, protectedType = false, supplier = false) {
  vi.mocked(serviceCall).mockImplementation(async (_, request) => {
    if (request.path.includes('/configuration/')) {
      const metadata = form('parties', 'read');
      if (protectedType) metadata.fields.find(field => field.key === 'party_type')!.readable = false;
      return metadata as never;
    }
    return { items: [{ id: ID, company_id: COMPANY, row_version: 1, code: 'ABC', name: 'Sample party',
      status: 'ACTIVE', party_type: partyType, ...(roles === undefined ? {} : { roles }) }], page } as never;
  });
  render(<AccountingConfigurationDirectory company={COMPANY} config={accountingResource('parties')!} canManage={false} supplier={supplier} />);
  return within(await screen.findByRole('table'));
}

it.each([['ORGANISATION', 'Organisation'], ['PERSON', 'Person'], [null, 'Not specified']])(
  'displays a clear party type for %s', async (value, label) => {
    const table = await directory(value, []);
    expect(table.getByRole('columnheader', { name: 'Party type' })).toBeVisible();
    expect(table.getByRole('cell', { name: label! })).toBeVisible();
    expect(table.getByRole('cell', { name: 'No active role' })).toBeVisible();
  },
);
it.each([false, true])('shows all active roles on the party/supplier directory (%s)', async supplier => {
  const table = await directory('ORGANISATION', ['CUSTOMER', 'SUPPLIER', 'OTHER', 'BROKER'], false, supplier);
  expect(table.getByRole('columnheader', { name: 'Active roles' })).toBeVisible();
  for (const role of ['Customer', 'Supplier', 'Other', 'Broker']) expect(table.getByText(role)).toBeVisible();
});
it('does not invent a supplier role or expose a protected type', async () => {
  const table = await directory('PERSON', [], true, true);
  expect(table.queryByRole('columnheader', { name: 'Party type' })).not.toBeInTheDocument();
  expect(table.queryByText('Person')).not.toBeInTheDocument();
  expect(table.getByRole('cell', { name: 'No active role' })).toBeVisible();
});
it('hides the roles column when role data is protected', async () => {
  const table = await directory('PERSON', undefined);
  expect(table.queryByRole('columnheader', { name: 'Active roles' })).not.toBeInTheDocument();
  expect(table.queryByText('No active role')).not.toBeInTheDocument();
});
