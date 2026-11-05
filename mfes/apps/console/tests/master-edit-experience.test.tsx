import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';

import { AccountingConfigurationEditor } from '../app/components/AccountingConfigurationEditor';

import { accountingResource } from '../app/lib/accounting-configuration-resources';
import { serviceCall } from '../app/lib/service-call';
import { goTo } from '../app/lib/navigate';
import { COMPANY, RECORD, response as productResponse, resetFixtures } from './product-classification-fixtures';
import { response as accountingResponse } from './accounting-configuration-fixtures';

vi.mock('../app/lib/service-call', async (original) => ({
  ...(await original<typeof import('../app/lib/service-call')>()),
  serviceCall: vi.fn(),
}));
vi.mock('../app/lib/navigate', () => ({
  goTo: vi.fn(),
  signInUrl: () => '/signin',
}));
const api = vi.mocked(serviceCall);
const writes = () =>
  api.mock.calls.filter(([, request]) =>
    ['POST', 'PATCH', 'PUT'].includes(request.method ?? 'GET'),
  );
beforeEach(() => {
  vi.clearAllMocks();
  resetFixtures();
  window.history.replaceState(null, '', '/');
  api.mockImplementation(
    async (_, request) =>
      (request.service === 'accounting'
        ? accountingResponse(request.path, request.method, request.body)
        : productResponse(request)) as never,
  );
});
function party(supplier = false) {
  render(
    <AccountingConfigurationEditor
      company={COMPANY}
      config={accountingResource('parties')!}
      id={RECORD}
      supplier={supplier}
      returnTo="/accounting/suppliers?q=Retail"
    />,
  );
}
it.each(['party'])(
  'clears corrected native validation errors in %s edits',
  async (resource) => {
    const original = api.getMockImplementation()!;
    api.mockImplementation(async (...args) => {
      if (args[1].method === 'PATCH')
        throw {
          status: 422,
          message: 'Check name',
          fields: { name: 'Choose a different display name.' },
        };
      return original(...args);
    });
    party();
    const name = await screen.findByRole('textbox', { name: 'Name' });
    await userEvent.type(name, ' revised');
    await userEvent.click(screen.getByRole('button', { name: 'Save changes' }));
    await waitFor(() => expect(name).toHaveAttribute('aria-invalid', 'true'));
    await userEvent.type(name, ' again');
    expect(name).not.toHaveAttribute('aria-invalid', 'true');
    expect(screen.queryByText('Check name')).not.toBeInTheDocument();
  },
);
it('returns supplier edit cancellation to its detail page and uses edit guidance', async () => {
  party(true);
  await screen.findByRole('textbox', { name: 'Name' });
  expect(
    screen.getByRole('heading', { level: 1, name: 'Edit supplier' }),
  ).toBeVisible();
  expect(
    screen.queryByText('Save the shared party identity.'),
  ).not.toBeInTheDocument();
  const cancel = screen.getByRole('link', { name: 'Cancel' });
  const target = new URL(
    cancel.getAttribute('href')!,
    'https://console.invalid',
  );
  expect(target.pathname).toBe('/accounting/suppliers/' + RECORD);
  expect(target.searchParams.get('returnTo')).toBe(
    '/accounting/suppliers?q=Retail',
  );
  expect(screen.getByRole('region', { name: 'Saved party' })).toBeVisible();
});
it('does not send a version-only party patch for whitespace-only edits', async () => {
  party();
  await userEvent.type(
    await screen.findByRole('textbox', { name: 'Name' }),
    ' ',
  );
  await userEvent.click(screen.getByRole('button', { name: 'Save changes' }));
  expect(await screen.findByText('No changes to save.')).toBeVisible();
  expect(writes()).toHaveLength(0);
  expect(goTo).not.toHaveBeenCalled();
});

it.each(['party'])(
  'protects dirty %s cancellation and retains the detail destination',
  async (resource) => {
    party(true);
    await userEvent.type(
      await screen.findByRole('textbox', { name: 'Name' }),
      ' revised',
    );
    const target = screen
      .getByRole('link', { name: 'Cancel' })
      .getAttribute('href');
    await userEvent.click(screen.getByRole('link', { name: 'Cancel' }));
    expect(await screen.findByRole('dialog')).toBeVisible();
    expect(goTo).not.toHaveBeenCalled();
    await userEvent.click(
      screen.getByRole('button', { name: 'Discard and leave' }),
    );
    expect(goTo).toHaveBeenCalledWith(
      new URL(target!, window.location.origin).href,
    );
    expect(writes()).toHaveLength(0);
  },
);

it.each(['party'])(
  'does not expose an editable %s form after a forbidden read',
  async (resource) => {
    api.mockRejectedValue({
      status: 403,
      message: 'Edit access is no longer available.',
    });
    party();
    await screen.findByText('Edit access is no longer available.');
    expect(
      screen.queryByRole('textbox', { name: 'Name' }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Save changes' }),
    ).not.toBeInTheDocument();
  },
);
