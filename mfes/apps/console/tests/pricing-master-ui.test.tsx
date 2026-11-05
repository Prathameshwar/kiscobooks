import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { PricingMasterDirectory } from '../app/components/PricingMasterDirectory';
import { PricingMasterEditor } from '../app/components/PricingMasterEditor';
import { PricingMasterDetail } from '../app/components/PricingMasterDetail';
import { PricingCurrency } from '../app/components/PricingMasterCommon';
import { masterConfig } from '../app/lib/catalog-masters';
import { serviceCall } from '../app/lib/service-call';
import {
  COMPANY,
  RECORD,
  SOURCE,
  fields,
  response,
  row,
  access,
  resetFixtures,
} from './pricing-master-fixtures';
vi.mock('../app/lib/service-call', async (original) => ({
  ...(await original<typeof import('../app/lib/service-call')>()),
  serviceCall: vi.fn(),
}));
vi.mock('../app/lib/navigate', () => ({
  goTo: vi.fn(),
  signInUrl: () => '/sign-in',
}));
const api = vi.mocked(serviceCall),
  writes = () =>
    api.mock.calls.filter(([, request]) =>
      ['POST', 'PATCH'].includes(request.method ?? 'GET'),
    );
beforeEach(() => {
  vi.clearAllMocks();
  resetFixtures();
  window.history.replaceState(null, '', '/');
  api.mockImplementation(
    async (_endpoint, request) => response(request) as never,
  );
});
const editor = (resource: string, id?: string) =>
  render(
    <PricingMasterEditor
      company={COMPANY}
      config={masterConfig(resource)!}
      id={id}
      access={access}
    />,
  );
const fill = async () => {
  const code = await screen.findByRole('textbox', { name: 'Code' });
  await userEvent.type(code, 'NEW');
  await userEvent.type(
    screen.getByRole('textbox', { name: 'Name' }),
    'New pricing',
  );
};
it.each(['sales-channels', 'price-levels', 'price-plans'])(
  'has a named %s directory action menu and safe links',
  async (resource) => {
    render(
      <PricingMasterDirectory
        company={COMPANY}
        config={masterConfig(resource)!}
        canManage
        access={access}
      />,
    );
    await userEvent.click(
      await screen.findByRole('button', { name: 'Actions for Test pricing' }),
    );
    expect(
      screen.getByRole('menuitem', { name: 'View details' }),
    ).toBeVisible();
    expect(
      screen.getByRole('menuitem', { name: 'Edit details' }),
    ).toBeVisible();
    expect(
      screen.getByRole('link', {
        name: 'New ' + masterConfig(resource)!.singular,
      }),
    ).toHaveAttribute(
      'href',
      expect.stringContaining('/masters/' + resource + '/new?returnTo='),
    );
  },
);
it.each(['sales-channels', 'price-levels', 'price-plans'])(
  'creates %s with native fields and a verified success',
  async (resource) => {
    editor(resource);
    await fill();
    if (resource === 'price-plans') {
      await userEvent.click(
        screen.getByRole('button', {
          name: 'Toggle Sales price level options',
        }),
      );
      await userEvent.click(
        await screen.findByRole('option', { name: /Test pricing/ }),
      );
      const currency = screen.getByRole('combobox', { name: 'Currency' });
      if (!(currency as HTMLInputElement).value) {
        await userEvent.click(
          screen.getByRole('button', { name: 'Toggle Currency options' }),
        );
        await userEvent.click(
          await screen.findByRole('option', { name: /Indian Rupee/ }),
        );
      }
    }
    await userEvent.click(
      screen.getByRole('button', {
        name: 'Create ' + masterConfig(resource)!.singular,
      }),
    );
    await screen.findByText(/created successfully/);
    expect(writes()[0]![1].body).toMatchObject({
      code: 'NEW',
      name: 'New pricing',
    });
    if (resource === 'price-levels')
      expect(writes()[0]![1].body).toMatchObject({ ordinal: 4 });
    if (resource === 'price-plans')
      expect(writes()[0]![1].body).toMatchObject({
        purpose: 'SALE',
        price_level_id: RECORD,
        currency: 'INR',
        tax_basis: 'EXCLUSIVE',
      });
  },
);
it.each(['sales-channels', 'price-levels', 'price-plans'])(
  'edits %s with its native patch contract',
  async (resource) => {
    editor(resource, RECORD);
    const name = await screen.findByRole('textbox', { name: 'Name' });
    await userEvent.clear(name);
    await userEvent.type(name, 'Updated');
    await userEvent.click(screen.getByRole('button', { name: 'Save changes' }));
    await screen.findByText(/updated successfully/);
    expect(writes()[0]![1].body).toEqual({
      expected_version: 4,
      name: 'Updated',
      ...(resource === 'price-levels' ? { is_active: true } : {}),
    });
  },
);
it('requires valid labels and a reserved-free level number, focusing the first error', async () => {
  editor('price-levels');
  await userEvent.click(
    await screen.findByRole('button', { name: 'Create price level' }),
  );
  await waitFor(() =>
    expect(screen.getByRole('textbox', { name: 'Code' })).toHaveFocus(),
  );
  expect(writes()).toHaveLength(0);
  await userEvent.type(screen.getByRole('textbox', { name: 'Code' }), 'PRICE1');
  await userEvent.type(
    screen.getByRole('textbox', { name: 'Name' }),
    'Price one',
  );
  await userEvent.click(
    screen.getByRole('button', { name: 'Create price level' }),
  );
  await screen.findByText(/Baseline codes are reserved/);
  expect(writes()).toHaveLength(0);
});
it('sets up baseline levels only after confirmation', async () => {
  render(
    <PricingMasterDirectory
      company={COMPANY}
      config={masterConfig('price-levels')!}
      canManage
      access={access}
    />,
  );
  await userEvent.click(
    await screen.findByRole('button', { name: 'Set up baseline price levels' }),
  );
  expect(writes()).toHaveLength(0);
  await userEvent.click(
    within(screen.getByRole('dialog')).getByRole('button', {
      name: 'Set up levels',
    }),
  );
  await screen.findByText(/Baseline price levels are ready/);
  expect(writes()[0]![1]).toMatchObject({
    path: '/v1/companies/' + COMPANY + '/pricing/bootstrap',
    method: 'POST',
    body: {},
  });
});
it.each(['sales-channels', 'price-levels'])(
  'uses confirmed native %s deactivation',
  async (resource) => {
    render(
      <PricingMasterDetail
        company={COMPANY}
        config={masterConfig(resource)!}
        id={RECORD}
        canManage
        access={access}
      />,
    );
    await userEvent.click(
      await screen.findByRole('button', {
        name: masterConfig(resource)!.singular + ' actions',
      }),
    );
    await userEvent.click(screen.getByRole('menuitem', { name: 'Deactivate' }));
    expect(writes()).toHaveLength(0);
    await userEvent.click(
      within(screen.getByRole('dialog')).getByRole('button', {
        name: 'Deactivate',
      }),
    );
    await screen.findByText(/deactivated successfully/);
    expect(writes()[0]![1]).toMatchObject({
      method: resource === 'price-levels' ? 'PATCH' : 'POST',
      body: {
        expected_version: 4,
        ...(resource === 'price-levels'
          ? { name: 'Test pricing', is_active: false }
          : {}),
      },
    });
  },
);
it('omits plan lifecycle and links a readable sales level', async () => {
  render(
    <PricingMasterDetail
      company={COMPANY}
      config={masterConfig('price-plans')!}
      id={RECORD}
      canManage
      access={access}
    />,
  );
  await screen.findByRole('link', { name: 'Price 1' });
  await userEvent.click(
    screen.getByRole('button', { name: 'price plan actions' }),
  );
  expect(screen.queryByRole('menuitem', { name: 'Deactivate' })).toBeNull();
});
it('protects the baseline price level from retirement', async () => {
  render(
    <PricingMasterDetail
      company={COMPANY}
      config={masterConfig('price-levels')!}
      id={SOURCE}
      canManage
      access={access}
    />,
  );
  await userEvent.click(
    await screen.findByRole('button', { name: 'price level actions' }),
  );
  expect(screen.queryByRole('menuitem', { name: 'Deactivate' })).toBeNull();
});
it('keeps plan identity read-only and offers purchase purpose only with scoped authority', async () => {
  const view = editor('price-plans', RECORD);
  expect(await screen.findByRole('textbox', { name: 'Code' })).toBeDisabled();
  expect(screen.getByRole('textbox', { name: 'Currency' })).toBeDisabled();
  view.unmount();
  render(
    <PricingMasterEditor
      company={COMPANY}
      config={masterConfig('price-plans')!}
      access={{ ...access, purchaseManage: false }}
    />,
  );
  const purpose = await screen.findByRole('combobox', { name: 'Purpose' });
  expect(
    within(purpose).queryByRole('option', { name: 'Purchase' }),
  ).toBeNull();
});
it('creates a purchase plan without a sale level', async () => {
  editor('price-plans');
  await fill();
  await userEvent.selectOptions(
    screen.getByRole('combobox', { name: 'Purpose' }),
    'PURCHASE',
  );
  await userEvent.click(
    screen.getByRole('button', { name: 'Create price plan' }),
  );
  await screen.findByText(/created successfully/);
  expect(writes()[0]![1].body).toMatchObject({
    purpose: 'PURCHASE',
    price_level_id: null,
  });
});
it('retains a rejected draft and focuses the server field error', async () => {
  api.mockImplementation(async (_endpoint, request) => {
    if (request.method === 'POST')
      throw {
        status: 422,
        message: 'Check inputs',
        fields: { code: 'Code already used' },
      };
    return response(request) as never;
  });
  editor('sales-channels');
  await fill();
  await userEvent.click(
    screen.getByRole('button', { name: 'Create sales channel' }),
  );
  await screen.findByText('Code already used');
  expect(screen.getByRole('textbox', { name: 'Code' })).toHaveFocus();
  expect(screen.getByRole('textbox', { name: 'Name' })).toHaveValue(
    'New pricing',
  );
});
it('freezes an uncertain pricing save and retries the same body and key', async () => {
  let fail = true;
  api.mockImplementation(async (_endpoint, request) => {
    if (request.method === 'POST' && fail) {
      fail = false;
      throw { status: 503, message: 'Offline' };
    }
    return response(request) as never;
  });
  editor('price-levels');
  await fill();
  await userEvent.click(
    screen.getByRole('button', { name: 'Create price level' }),
  );
  await screen.findByRole('button', { name: 'Retry same save' });
  expect(screen.getByRole('textbox', { name: 'Name' })).toBeDisabled();
  await userEvent.click(
    screen.getByRole('button', { name: 'Retry same save' }),
  );
  await screen.findByText(/created successfully/);
  expect(writes()[1]![1].key).toBe(writes()[0]![1].key);
  expect(writes()[1]![1].body).toEqual(writes()[0]![1].body);
});
it('treats a lost post-save read as uncertain and recovers through the same receipt', async () => {
  let readFails = true;
  api.mockImplementation(async (_endpoint, request) => {
    const result = response(request);
    if (
      request.path.includes('/price-levels/') &&
      (request.method ?? 'GET') === 'GET' &&
      readFails
    ) {
      readFails = false;
      throw { status: 503, message: 'Read unavailable' };
    }
    return result as never;
  });
  editor('price-levels');
  await fill();
  await userEvent.click(
    screen.getByRole('button', { name: 'Create price level' }),
  );
  await userEvent.click(
    await screen.findByRole('button', { name: 'Retry same save' }),
  );
  await screen.findByText(/created successfully/);
  expect(writes()[1]![1].key).toBe(writes()[0]![1].key);
});
it('requires confirmation before replacing a conflicting draft', async () => {
  api.mockImplementation(async (_endpoint, request) => {
    if (request.method === 'PATCH')
      throw { status: 409, message: 'Stale version' };
    return response(request) as never;
  });
  editor('price-levels', RECORD);
  const name = await screen.findByRole('textbox', { name: 'Name' });
  await userEvent.clear(name);
  await userEvent.type(name, 'Draft');
  await userEvent.click(screen.getByRole('button', { name: 'Save changes' }));
  await userEvent.click(
    await screen.findByRole('button', { name: 'Reload and review' }),
  );
  expect(screen.getByRole('textbox', { name: 'Name' })).toHaveValue('Draft');
  await userEvent.click(
    within(screen.getByRole('dialog')).getByRole('button', {
      name: 'Discard and reload',
    }),
  );
  await waitFor(() =>
    expect(screen.getByRole('textbox', { name: 'Name' })).toHaveValue(
      'Test pricing',
    ),
  );
});
it('guards unsaved back navigation', async () => {
  editor('sales-channels');
  await fill();
  await userEvent.click(
    screen.getByRole('link', { name: 'Back to previous page' }),
  );
  expect(
    screen.getByRole('dialog', { name: 'Discard unsaved changes?' }),
  ).toBeVisible();
  expect(writes()).toHaveLength(0);
});
it('removes unreadable filters and withholds protected edit fields', async () => {
  api.mockImplementation(async (_endpoint, request) =>
    request.path.includes('/field-set')
      ? ({
          company_id: COMPANY,
          entity_type: 'catalog.price_plan',
          fields: fields('price_plan').filter(
            (field) => !['code', 'name', 'currency'].includes(field.key),
          ),
        } as never)
      : (response(request) as never),
  );
  render(
    <PricingMasterDirectory
      company={COMPANY}
      config={masterConfig('price-plans')!}
      canManage
      access={access}
      initialQuery="q=Test&currency=INR"
    />,
  );
  await screen.findByText(/Unavailable search/);
  expect(
    screen.queryByRole('textbox', { name: /Search price plans/ }),
  ).toBeNull();
  await userEvent.click(screen.getByRole('button', { name: /Actions for/ }));
  expect(screen.queryByRole('menuitem', { name: 'Edit details' })).toBeNull();
});
it('offers no authoring actions for read-only access', async () => {
  render(
    <PricingMasterDirectory
      company={COMPANY}
      config={masterConfig('price-levels')!}
      canManage={false}
      access={access}
    />,
  );
  await screen.findByRole('table');
  expect(
    screen.queryByRole('button', { name: 'Set up baseline price levels' }),
  ).toBeNull();
  expect(screen.queryByRole('link', { name: 'New price level' })).toBeNull();
});
it('shows a saved compound code sort as its matching directory control', async () => {
  render(
    <PricingMasterDirectory
      company={COMPANY}
      config={masterConfig('price-plans')!}
      canManage
      access={access}
      initialQuery="sort=code%2Cid"
    />,
  );
  await waitFor(() =>
    expect(screen.getByRole('combobox', { name: 'Sort' })).toHaveValue('code'),
  );
  expect(window.location.search).toContain('sort=code');
});
it('validates required descriptive custom fields before creating a reference book', async () => {
  api.mockImplementation(async (_endpoint, request) => {
    const result = response(request);
    if (request.path.includes('/field-set'))
      (result as { fields: unknown[] }).fields.push({
        key: 'custom_field:cf_note',
        label: 'Note',
        source: 'custom',
        order: 90,
        visible: true,
        writable: true,
        required: true,
        conditional_access: false,
        custom: {
          key: 'cf_note',
          data_type: 'text',
          is_active: true,
          is_immutable_after_create: false,
          validation: { required: true, max_length: 20 },
          choices: [],
        },
      });
    return result as never;
  });
  editor('price-plans');
  await fill();
  await userEvent.selectOptions(
    screen.getByRole('combobox', { name: 'Purpose' }),
    'REFERENCE_RETAIL',
  );
  await userEvent.click(
    screen.getByRole('button', { name: 'Create price plan' }),
  );
  await screen.findByText('Note is required.');
  expect(writes()).toHaveLength(0);
  await userEvent.type(
    screen.getByRole('textbox', { name: 'Note' }),
    'Retail reference',
  );
  await userEvent.click(
    screen.getByRole('button', { name: 'Create price plan' }),
  );
  await screen.findByText(/created successfully/);
  expect(writes()[0]![1].body).toMatchObject({
    custom_fields: { cf_note: 'Retail reference' },
    price_level_id: null,
  });
});
it('supports descriptive-field-only edits without changing a protected name', async () => {
  api.mockImplementation(async (_endpoint, request) => {
    const result = response(request);
    if (request.path.includes('/field-set'))
      (result as { fields: unknown[] }).fields = [
        ...fields('price_plan', 'update').map((field) => ({
          ...field,
          writable: false,
        })),
        {
          key: 'custom_field:cf_note',
          label: 'Note',
          source: 'custom',
          order: 90,
          visible: true,
          writable: true,
          required: false,
          conditional_access: false,
          custom: {
            key: 'cf_note',
            data_type: 'text',
            is_active: true,
            is_immutable_after_create: false,
            validation: { required: false, max_length: 20 },
            choices: [],
          },
        },
      ];
    return result as never;
  });
  editor('price-plans', RECORD);
  await userEvent.type(
    await screen.findByRole('textbox', { name: 'Note' }),
    'Reviewed',
  );
  expect(screen.getByRole('textbox', { name: 'Name' })).toBeDisabled();
  await userEvent.click(screen.getByRole('button', { name: 'Save changes' }));
  await screen.findByText(/updated successfully/);
  expect(writes()[0]![1].body).toEqual({
    expected_version: 4,
    name: 'Test pricing',
    custom_fields: { cf_note: 'Reviewed' },
  });
});
it('allows correcting a duplicate create without discarding the draft', async () => {
  let fail = true;
  api.mockImplementation(async (_endpoint, request) => {
    if (request.method === 'POST' && fail) {
      fail = false;
      throw { status: 409, message: 'Duplicate code' };
    }
    return response(request) as never;
  });
  editor('sales-channels');
  await fill();
  await userEvent.click(
    screen.getByRole('button', { name: 'Create sales channel' }),
  );
  await screen.findByText(/Duplicate code/);
  await userEvent.type(screen.getByRole('textbox', { name: 'Code' }), '2');
  expect(screen.getByRole('textbox', { name: 'Name' })).toHaveValue(
    'New pricing',
  );
  await userEvent.click(
    screen.getByRole('button', { name: 'Create sales channel' }),
  );
  await screen.findByText(/created successfully/);
  expect(writes()[1]![1].body).toMatchObject({ code: 'NEW2' });
});
it('recovers failed currency choices and keeps selection searchable', async () => {
  let fail = true;
  api.mockImplementation(async (_endpoint, request) => {
    if (request.path === '/v1/reference/currencies' && fail) {
      fail = false;
      throw { status: 503, message: 'Currency service offline' };
    }
    return response(request) as never;
  });
  const change = vi.fn();
  render(<PricingCurrency company={COMPANY} value={null} onChange={change} />);
  await userEvent.click(
    await screen.findByRole('button', { name: 'Retry currency choices' }),
  );
  await waitFor(() =>
    expect(screen.getByRole('combobox', { name: 'Currency' })).toBeEnabled(),
  );
  await userEvent.click(
    screen.getByRole('button', { name: 'Toggle Currency options' }),
  );
  await userEvent.click(
    await screen.findByRole('option', { name: /Indian Rupee/ }),
  );
  expect(change).toHaveBeenCalledWith('INR');
});
it('keeps an unconfirmed baseline setup bound to its original key', async () => {
  let fail = true;
  api.mockImplementation(async (_endpoint, request) => {
    if (request.path.endsWith('/pricing/bootstrap') && fail) {
      fail = false;
      throw { status: 503, message: 'Offline' };
    }
    return response(request) as never;
  });
  render(
    <PricingMasterDirectory
      company={COMPANY}
      config={masterConfig('price-levels')!}
      canManage
      access={access}
    />,
  );
  await userEvent.click(
    await screen.findByRole('button', { name: 'Set up baseline price levels' }),
  );
  await userEvent.click(
    within(screen.getByRole('dialog')).getByRole('button', {
      name: 'Set up levels',
    }),
  );
  await userEvent.click(
    await screen.findByRole('button', { name: 'Retry same setup' }),
  );
  await screen.findByText(/Baseline price levels are ready/);
  expect(writes()[1]![1].key).toBe(writes()[0]![1].key);
  expect(writes()[1]![1].body).toEqual({});
});
