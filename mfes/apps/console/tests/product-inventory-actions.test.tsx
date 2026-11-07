import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { ProductCatalogDirectory } from '../app/components/ProductCatalogDirectory';

import { SimpleProductDirectory } from '../app/components/SimpleProductDirectory';
import { masterConfig } from '../app/lib/catalog-masters';
import { serviceCall } from '../app/lib/service-call';
import { COMPANY, SOURCE, RECORD, ROOT, access, response, record, resetFixtures } from './product-classification-fixtures';
import { entryConfiguration } from './product-entry-fixtures';

vi.mock('../app/lib/service-call', async (original) => ({
  ...(await original<typeof import('../app/lib/service-call')>()),
  serviceCall: vi.fn(),
}));
const api = vi.mocked(serviceCall);
let enabled: string[],
  lot: boolean | undefined,
  serial: boolean | undefined,
  kind: 'GOODS' | 'SERVICE',
  profile: boolean,
  unavailable: boolean,
  configurationCompany: string, activeSku: boolean;
beforeEach(() => {
  vi.clearAllMocks();
  resetFixtures();
  window.history.replaceState(null, '', '/masters/items');
  enabled = ['inventory', 'batch_tracking', 'serial_tracking'];
  lot = true;
  serial = true;
  kind = 'GOODS';
  profile = true;
  unavailable = false;
  configurationCompany = COMPANY;
  activeSku = false;
  api.mockImplementation(async (_, request) => {
    const url = new URL(request.path, 'https://console.invalid');
    if (url.pathname.endsWith('/products/' + RECORD)) return { id: RECORD, company_id: COMPANY, revision: 'review-1', authoring_version: 1, custom_fields: {}, shared_custom_fields: {} } as never;
    if (url.pathname.endsWith('/products/field-set')) return { company_id: COMPANY, authoring_version: 1, fields: ['code', 'name', 'status'].map(key => ({ key, visible: true, readable: true })), native_bindings: {} } as never;
    if (url.pathname.endsWith('/products')) return { items: [{ id: RECORD, name: 'Standard', code: 'TEA', status: 'ACTIVE' }], page: { limit: 25, has_more: false, next_cursor: null } } as never;
    if (activeSku && url.pathname.endsWith('/items/' + RECORD)) return { ...record('items'), status: 'ACTIVE' } as never;
    if (url.pathname.endsWith('/item-inventory-profiles')) return { items: [{ id: SOURCE, item_id: RECORD, lot_tracking: lot, serial_tracking: serial }], page: { has_more: false } } as never;
    if (activeSku && url.pathname.endsWith('/items')) { const result = response(request) as { items: object[] }; return { ...result, items: result.items.map(row => ({ ...row, status: 'ACTIVE' })) } as never; }
    if (url.pathname.endsWith('/setup-readiness')) {
      if (unavailable) throw { status: 503, message: 'Unavailable' };
      return {
        company_id: configurationCompany,
        features: ['inventory', 'batch_tracking', 'serial_tracking'].map(
          (feature_key) => ({
            feature_key,
            state: enabled.includes(feature_key) ? 'ENABLED' : 'DISABLED',
          }),
        ),
      } as never;
    }
    if (
      url.pathname.endsWith('/configuration') ||
      url.pathname.endsWith('/product-configuration/effective')
    ) {
      const value = entryConfiguration(url.searchParams.get('as_of')!, kind);
      value.profiles.inventory_template_revision_id = profile ? SOURCE : null;
      return value as never;
    }
    if (
      url.pathname.endsWith(
        '/product-configuration/options/inventory-template-revisions',
      )
    )
      return { items: [{ value: SOURCE, parent_id: ROOT }] } as never;
    if (
      url.pathname.endsWith(
        '/inventory-templates/' + ROOT + '/revisions/' + SOURCE,
      )
    )
      return {
        id: SOURCE,
        company_id: COMPANY,
        row_version: 1,
        lot_tracking: lot,
        serial_tracking: serial,
      } as never;
    const value = response(request);
    if (
      url.pathname.endsWith('/product-families') &&
      !url.pathname.includes('/configuration/')
    )
      return {
        ...(value as object),
        items: [{ ...record('product-families'), kind }],
      } as never;
    return value as never;
  });
});
function directory(family = false, overrides: Partial<typeof access> = {}) {
  render(
    <ProductCatalogDirectory
      company={COMPANY}
      config={masterConfig(family ? 'product-families' : 'items')!}
      canManage
      access={{
        ...access,
        inventoryProfiles: true,
        companyConfiguration: true,
        ...overrides,
      }}
    />,
  );
}
async function open(keyboard = false) {
  const trigger = await screen.findByRole('button', {
    name: /Actions for Standard/,
  });
  if (keyboard) {
    trigger.focus();
    await userEvent.keyboard('{ArrowDown}');
  } else await userEvent.click(trigger);
  return trigger;
}
it('does not load per-product configuration for the list until a kebab is opened', async () => {
  directory();
  await screen.findByRole('table');
  expect(
    api.mock.calls.some(([, request]) =>
      /setup-readiness|\/configuration\?|inventory-template-revisions/.test(
        request.path,
      ),
    ),
  ).toBe(false);
  await open(true);
  await screen.findByText('Activate this product before managing stock.');
  expect(
    api.mock.calls.filter(([, request]) =>
      request.path.includes('/items/' + RECORD + '/configuration?'),
    ),
  ).toHaveLength(1);
  expect(
    api.mock.calls.every(
      ([, request]) => !request.method || request.method === 'GET',
    ),
  ).toBe(true);
});
it('hides inventory actions when inventory is disabled without fetching product details', async () => {
  enabled = [];
  directory();
  await open();
  await waitFor(() =>
    expect(
      screen.queryByRole('menuitem', { name: /Manage stock/ }),
    ).not.toBeInTheDocument(),
  );
  expect(
    screen.getByRole('menuitem', { name: /Product ledger/ }),
  ).toHaveAttribute('aria-disabled', 'true');
  expect(
    api.mock.calls.some(([, request]) =>
      request.path.includes('/items/' + RECORD + '/configuration?'),
    ),
  ).toBe(false);
});
it.each([false, true])(
  'does not offer stock operations for a service (%s family)',
  async (family) => {
    kind = 'SERVICE';
    directory(family);
    await open();
    await waitFor(() =>
      expect(
        screen.queryByRole('menuitem', { name: /Manage stock/ }),
      ).not.toBeInTheDocument(),
    );
    expect(
      screen.queryByRole('menuitem', { name: /Manage batches|Manage serials/ }),
    ).not.toBeInTheDocument();
    expect(
      api.mock.calls.some(([, request]) =>
        request.path.includes('/inventory-templates/'),
      ),
    ).toBe(false);
  },
);
it.each([
  'companyConfiguration',
  'configuration',
  'inventoryProfiles',
] as const)(
  'never infers tracking without %s read access',
  async (permission) => {
    directory(false, { [permission]: false });
    await open();
    expect(
      screen.getByRole('menuitem', { name: /Manage stock/ }),
    ).toHaveAttribute('aria-disabled', 'true');
    expect(
      screen.queryByRole('menuitem', { name: /Manage batches|Manage serials/ }),
    ).not.toBeInTheDocument();
    if (permission === 'companyConfiguration')
      expect(
        api.mock.calls.some(([, request]) =>
          request.path.endsWith('/setup-readiness'),
        ),
      ).toBe(false);
  },
);
it.each(['outage', 'other-company', 'protected', 'missing-profile'])(
  'fails closed for %s settings',
  async (scenario) => {
    if (scenario === 'outage') unavailable = true;
    if (scenario === 'other-company') configurationCompany = ROOT;
    if (scenario === 'protected') lot = undefined;
    if (scenario === 'missing-profile') profile = false;
    directory();
    await open();
    const reason =
      scenario === 'missing-profile'
        ? /No inventory profile is configured/
        : scenario === 'protected'
          ? /settings are protected/
          : /Company configuration is unavailable/;
    await screen.findByText(reason);
    expect(
      screen.queryByRole('menuitem', { name: /Manage batches|Manage serials/ }),
    ).not.toBeInTheDocument();
  },
);

it('links stock-authorised active SKUs to warehouse balances', async () => {
  activeSku = true;
  directory(false, { stock: true });
  await open();
  expect(await screen.findByRole('menuitem', { name: 'Manage stock' })).toHaveAttribute('href', '/inventory/stock?item_id=' + RECORD);
});

it.each([false, true])('keeps stock and restored tracking actions (simple %s)', async simple => {
  activeSku = true;
  const granted = { ...access, companyConfiguration: true, inventoryProfiles: true, stock: true, openingStock: true, batches: true, serials: true };
  if (simple) render(<SimpleProductDirectory company={COMPANY} access={granted} />);
  else directory(false, granted);
  await open();
  expect(await screen.findByRole('menuitem', { name: 'Record opening stock' })).toHaveAttribute('href', '/inventory/stock/opening?item_id=' + RECORD);
  expect(screen.getByRole('menuitem', { name: 'Manage batches' })).toHaveAttribute('href', '/inventory/batches?item_id=' + RECORD);
  if (!simple) expect(screen.getByRole('menuitem', { name: 'View details' })).toHaveAttribute('href', expect.stringContaining('/masters/items/' + RECORD));
  for (const name of ['View product', 'Edit product']) expect(screen.queryByRole('menuitem', { name })).toBeNull();
  expect(screen.queryByRole('link', { name: 'New product' })).toBeNull();
});
