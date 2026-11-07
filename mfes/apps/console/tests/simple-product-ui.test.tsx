import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';

import { SimpleProductDirectory } from '../app/components/SimpleProductDirectory';

import { ProductStructureSettings } from '../app/components/ProductStructureSettings';
import { ProductImport } from '../app/components/ProductImport';

import { useProductMode, type ProductMode } from '../app/components/ProductModeProvider';
import { serviceCall } from '../app/lib/service-call';
import { COMPANY, RECORD, access, fields, response, resetFixtures } from './product-classification-fixtures';
import { entryDefaults } from './product-entry-fixtures';
vi.mock('../app/components/ProductModeProvider', async (original) => ({
  ...(await original<typeof import('../app/components/ProductModeProvider')>()),
  useProductMode: vi.fn(),
}));
vi.mock('../app/lib/service-call', async (original) => ({
  ...(await original<typeof import('../app/lib/service-call')>()),
  serviceCall: vi.fn(),
}));
vi.mock('../app/components/MasterImport', () => ({
  MasterImport: ({
    profile,
  }: {
    profile: { defaultResource: string; resources: { label: string }[] };
  }) => (
    <p>
      Import {profile.defaultResource}:{' '}
      {profile.resources.map((row) => row.label).join(', ')}
    </p>
  ),
}));
const api = vi.mocked(serviceCall);
const product = {
  id: RECORD,
  company_id: COMPANY,
  code: 'TEA',
  name: 'Tea',
  kind: 'GOODS',
  status: 'DRAFT',
  sellable: true,
  purchasable: true,
  description: 'Original',
  revision: 'aggregate-1',
  authoring_version: 1,
  custom_fields: {},
  shared_custom_fields: {},
};
let mode: ReturnType<typeof useProductMode>;
function metadata(update = false) {
  const native = [
    ...fields('catalog.item', update ? 'update' : 'create')
      .filter((field) =>
        ['sku', 'name', 'status', 'sellable', 'purchasable'].includes(field.key),
      )
      .map((field) => ({
        ...field,
        key: field.key === 'sku' ? 'code' : field.key,
        label:
          field.key === 'sku'
            ? 'Product code'
            : field.key === 'name'
              ? 'Product name'
              : field.label,
      })),
    ...fields('catalog.product_family', update ? 'update' : 'create').filter(
      (field) => field.key === 'description',
    ),
  ];
  return {
    company_id: COMPANY,
    authoring_version: 1,
    fields: native,
    native_bindings: {},
  };
}
beforeEach(() => {
  vi.clearAllMocks();
  resetFixtures();
  window.history.replaceState(null, '', '/masters/items');
  mode = {
    company: COMPANY,
    data: {
      company_id: COMPANY,
      product_family_sku_enabled: false,
      row_version: 1,
      policy_generation: 8,
    } as ProductMode,
    loading: false,
    failure: null,
    refresh: vi.fn(),
  };
  vi.mocked(useProductMode).mockImplementation(() => mode);
  api.mockImplementation(async (_, request) => {
    const url = new URL(request.path, 'https://console.invalid');
    if (url.pathname.endsWith('/products/field-set'))
      return metadata(url.searchParams.get('operation') === 'update') as never;
    if (url.pathname.endsWith('/products') && request.method !== 'POST')
      return {
        items: [product],
        page: { limit: 25, has_more: false, next_cursor: null },
      } as never;
    if (url.pathname.includes('/products/')) return product as never;
    if (url.pathname.endsWith('/authoring-defaults'))
      return entryDefaults(url.searchParams) as never;
    return response(request) as never;
  });
});

it('keeps product search and status/sort controls in the shared filter row with inline labels', async () => {
  render(<SimpleProductDirectory company={COMPANY} access={access} />);
  const search = await screen.findByRole('searchbox', { name: 'Search' });
  const row = search.closest('.janso-filter-bar__controls');
  expect(row).not.toBeNull();
  for (const name of ['Status', 'Sort by']) {
    const control = screen.getByRole('combobox', { name });
    expect(control.closest('.janso-select')).toHaveClass('janso-select--inline');
    expect(row).toContainElement(control);
  }
});

it.each(['x', '   ', 'a'.repeat(201)])('does not forward an invalid bookmarked search: %s', async q => {
  render(<SimpleProductDirectory company={COMPANY} access={access} initialQuery={new URLSearchParams({ q }).toString()} />);
  await screen.findByText('Tea');
  const paths = api.mock.calls.map(call => call[1].path).filter(path => path.includes('/products?'));
  expect(paths.length).toBeGreaterThan(0);
  expect(paths.every(path => !new URL(path, 'https://console.invalid').searchParams.has('q'))).toBe(true);
});

it('preserves Next navigation state while changing directory filters', async () => {
  const state = { __NA: true, tree: ['verified-router-state'] };
  window.history.replaceState(state, '', '/masters/items');
  const user = userEvent.setup();
  render(<SimpleProductDirectory company={COMPANY} access={access} />);
  await screen.findByText('Tea');
  await user.selectOptions(screen.getByRole('combobox', { name: 'Sort by' }), '-name');
  expect(window.history.state).toEqual(state);
});

it('does not expose or send a saved filter for a denied status field', async () => {
  const original = api.getMockImplementation()!;
  api.mockImplementation(async (...args) => {
    if (args[1].path.endsWith('/products/field-set')) return { ...metadata(), fields: metadata().fields.filter(field => field.key !== 'status') } as never;
    return original(...args);
  });
  render(<SimpleProductDirectory company={COMPANY} access={access} initialQuery="status=ACTIVE" />);
  await screen.findByText('Tea');
  expect(screen.queryByRole('combobox', { name: 'Status' })).toBeNull();
  expect(screen.queryByRole('columnheader', { name: 'Status' })).toBeNull();
  expect(api.mock.calls.filter(call => call[1].path.includes('/products?')).every(call => !new URL(call[1].path, 'https://console.invalid').searchParams.has('status'))).toBe(true);
});

it('shows a readable variant blocker without a setting save action', async () => {
  const original = api.getMockImplementation()!;
  api.mockImplementation(async (...args) => {
    if (
      args[1].path.includes('company_product_authoring_configuration/field-set')
    )
      return {
        company_id: COMPANY,
        entity_type: 'catalog.company_product_authoring_configuration',
        fields: ['product_family_sku_enabled', 'change_reason'].map((key) => ({
          key,
          writable: true,
        })),
      } as never;
    if (args[1].path.endsWith('/authoring/preview'))
      return {
        ...mode!.data!,
        requested_enabled: true,
        blockers: ['variant_axes'],
        preview_token: 'reviewed',
      } as never;
    return original(...args);
  });
  const user = userEvent.setup();
  render(<ProductStructureSettings company={COMPANY} canManage />);
  await waitFor(() =>
    expect(
      screen.getByRole('checkbox', { name: 'Use product families and SKUs' }),
    ).toBeEnabled(),
  );
  await user.click(
    screen.getByRole('checkbox', { name: 'Use product families and SKUs' }),
  );
  await user.type(
    screen.getByRole('textbox', { name: /Reason for change/ }),
    'Review test',
  );
  await user.click(screen.getByRole('button', { name: 'Review change' }));
  await screen.findByText('Some products still have variant options.');
  expect(
    screen.queryByRole('button', { name: 'Save product structure' }),
  ).not.toBeInTheDocument();
});
const basicAccess = { ...access, initialSetup: false, configuration: false };
it('offers simple creation and links restored product record pages', async () => {
  render(<SimpleProductDirectory company={COMPANY} access={access} />);
  expect(await screen.findByText('Tea')).toBeVisible();
  expect(screen.getByRole('link', { name: 'Tea' })).toHaveAttribute('href', expect.stringContaining('/masters/items/'));
  expect(screen.getByRole('link', { name: 'Create product' })).toHaveAttribute('href', expect.stringContaining('/masters/items/new'));
  expect(screen.queryByText('Product families')).not.toBeInTheDocument();
  expect(screen.getByText('Product code')).toBeVisible();
});

it.each([401, 403, 422, 500, 503])(
  'keeps a failed product directory separate from empty results (%s)',
  async (status) => {
    const original = api.getMockImplementation()!;
    api.mockImplementation(async (...args) => {
      if (/\/products\?/.test(args[1].path))
        throw { status, message: 'Product list unavailable' };
      return original(...args);
    });
    render(<SimpleProductDirectory company={COMPANY} access={access} />);
    await screen.findByText('Product list unavailable');
    expect(screen.queryByText('No products yet')).not.toBeInTheDocument();
    expect(screen.queryByText('Create your first product to get started.')).not.toBeInTheDocument();
  },
);

it('does not show an empty catalogue when product metadata fails', async () => {
  api.mockRejectedValue({ status: 503, message: 'Product fields unavailable' });
  render(<SimpleProductDirectory company={COMPANY} access={access} />);
  await screen.findByText('Product fields unavailable');
  expect(screen.queryByText('No products yet')).not.toBeInTheDocument();
  expect(api.mock.calls.some(([, request]) => /\/products\?/.test(request.path))).toBe(false);
});

it('retries a failed directory without implying that products need recreating', async () => {
  const user = userEvent.setup();
  const original = api.getMockImplementation()!;
  let unavailable = true;
  api.mockImplementation(async (...args) => {
    if (/\/products\?/.test(args[1].path) && unavailable)
      throw { status: 503, message: 'Product list unavailable' };
    return original(...args);
  });
  render(<SimpleProductDirectory company={COMPANY} access={access} />);
  await screen.findByText('Product list unavailable');
  unavailable = false;
  await user.click(screen.getByRole('button', { name: 'Retry loading' }));
  expect(await screen.findByText('Tea')).toBeVisible();
});

it('distinguishes an unmatched search and clears filters while retaining navigation', async () => {
  const user = userEvent.setup();
  const original = api.getMockImplementation()!;
  api.mockImplementation(async (...args) => {
    if (/\/products\?/.test(args[1].path) && new URL(args[1].path, 'https://console.invalid').searchParams.has('q'))
      return { items: [], page: { limit: 25, has_more: false, next_cursor: null } } as never;
    return original(...args);
  });
  render(<SimpleProductDirectory company={COMPANY} access={access}
    initialQuery="q=missing&status=DRAFT&sort=-name&returnTo=%2Finventory%2Fproducts" />);
  await screen.findByText('No matching products');
  expect(screen.queryByText('No products yet')).not.toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Clear filters' }));
  expect(await screen.findByText('Tea')).toBeVisible();
  const current = new URL(window.location.href);
  expect(current.searchParams.get('returnTo')).toBe('/inventory/products');
  expect(current.searchParams.get('sort')).toBe('-name');
  expect(current.searchParams.has('q')).toBe(false);
  expect(current.searchParams.has('status')).toBe(false);
});

it('describes a successfully empty directory without suggesting creation to a reader', async () => {
  const original = api.getMockImplementation()!;
  api.mockImplementation(async (...args) => {
    if (/\/products\?/.test(args[1].path))
      return { items: [], page: { limit: 25, has_more: false, next_cursor: null } } as never;
    return original(...args);
  });
  render(<SimpleProductDirectory company={COMPANY} access={{ ...access, createProduct: false }} />);
  await screen.findByText('No products yet');
  expect(screen.queryByText('Create your first product to get started.')).not.toBeInTheDocument();
  expect(screen.queryByRole('link', { name: 'New product' })).not.toBeInTheDocument();
});
it('keeps an in-progress import in its original mode when settings change', () => {
  const view = render(<ProductImport company={COMPANY} canManage />);
  expect(screen.getByText('Import simple_product_create: New products')).toBeVisible();
  mode = {
    ...mode!,
    data: { ...mode!.data!, product_family_sku_enabled: true },
  };
  view.rerender(<ProductImport company={COMPANY} canManage />);
  expect(screen.getByText('Import simple_product_create: New products')).toBeVisible();
  expect(screen.getByText(/Your import is preserved/)).toBeVisible();
});
it('reviews a mode change before saving its exact preview', async () => {
  const original = api.getMockImplementation()!;
  api.mockImplementation(async (...args) => {
    const request = args[1];
    if (
      request.path.includes('company_product_authoring_configuration/field-set')
    )
      return {
        company_id: COMPANY,
        entity_type: 'catalog.company_product_authoring_configuration',
        fields: ['product_family_sku_enabled', 'change_reason'].map((key) => ({
          key,
          writable: true,
        })),
      } as never;
    if (request.path.endsWith('/authoring/preview'))
      return {
        ...mode!.data!,
        requested_enabled: true,
        blockers: [],
        preview_token: 'reviewed',
      } as never;
    if (request.path.endsWith('/authoring'))
      return {
        ...mode!.data!,
        row_version: 2,
        product_family_sku_enabled: true,
      } as never;
    return original(...args);
  });
  const user = userEvent.setup();
  render(<ProductStructureSettings company={COMPANY} canManage />);
  await waitFor(() =>
    expect(
      screen.getByRole('checkbox', { name: 'Use product families and SKUs' }),
    ).toBeEnabled(),
  );
  await user.click(
    screen.getByRole('checkbox', { name: 'Use product families and SKUs' }),
  );
  await user.type(
    screen.getByRole('textbox', { name: /Reason for change/ }),
    'We now sell sizes',
  );
  await user.click(screen.getByRole('button', { name: 'Review change' }));
  await user.click(
    await screen.findByRole('button', { name: 'Save product structure' }),
  );
  await screen.findByText('Product structure saved.');
  expect(
    api.mock.calls
      .map((call) => call[1])
      .find((request) => request.method === 'PATCH')?.body,
  ).toMatchObject({
    preview_token: 'reviewed',
    product_family_sku_enabled: true,
    expected_version: 1,
    expected_generation: 8,
    change_reason: 'We now sell sizes',
  });
});

it('keeps the product setting read-only without management access', () => {
  render(<ProductStructureSettings company={COMPANY} canManage={false} />);
  expect(
    screen.getByRole('checkbox', { name: 'Use product families and SKUs' }),
  ).toBeDisabled();
  expect(
    screen.getByText('You have read-only access to this setting.'),
  ).toBeVisible();
});

it('preserves useful directory state and drops family filters from API reads', async () => {
  render(
    <SimpleProductDirectory
      company={COMPANY}
      access={access}
      initialQuery={'family_id=' + RECORD + '&status=ACTIVE&sort=-name'}
    />,
  );
  await screen.findByText('Tea');
  const paths = api.mock.calls
    .map((call) => call[1].path)
    .filter((path) => path.includes('/products?'));
  expect(paths.at(-1)).toContain('status=ACTIVE');
  expect(paths.at(-1)).toContain('sort=-name');
  expect(paths.at(-1)).not.toContain('family_id');
  expect(screen.getByRole('combobox', { name: 'Sort by' })).toHaveValue(
    '-name',
  );
});

it('retries an unconfirmed settings review unchanged after another operator changes the saved mode', async () => {
  const original = api.getMockImplementation()!;
  let reviews = 0;
  api.mockImplementation(async (...args) => {
    if (
      args[1].path.includes('company_product_authoring_configuration/field-set')
    )
      return {
        company_id: COMPANY,
        entity_type: 'catalog.company_product_authoring_configuration',
        fields: ['product_family_sku_enabled', 'change_reason'].map((key) => ({
          key,
          writable: true,
        })),
      } as never;
    if (args[1].path.endsWith('/authoring/preview')) {
      reviews++;
      throw {
        status: reviews === 1 ? 503 : 409,
        message:
          reviews === 1
            ? 'Review response lost'
            : 'Settings changed; review again.',
      };
    }
    return original(...args);
  });
  const user = userEvent.setup();
  const view = render(<ProductStructureSettings company={COMPANY} canManage />);
  await waitFor(() =>
    expect(
      screen.getByRole('checkbox', { name: 'Use product families and SKUs' }),
    ).toBeEnabled(),
  );
  await user.click(
    screen.getByRole('checkbox', { name: 'Use product families and SKUs' }),
  );
  await user.type(
    screen.getByRole('textbox', { name: /Reason for change/ }),
    'Add sizes',
  );
  await user.click(screen.getByRole('button', { name: 'Review change' }));
  await screen.findByRole('button', { name: 'Retry same review' });
  mode = {
    ...mode!,
    data: {
      ...mode!.data!,
      row_version: 2,
      policy_generation: 9,
      product_family_sku_enabled: true,
    },
  };
  view.rerender(<ProductStructureSettings company={COMPANY} canManage />);
  await user.click(screen.getByRole('button', { name: 'Retry same review' }));
  await screen.findByText('Settings changed; review again.');
  expect(screen.getByRole('button', { name: 'Retry same review' })).toBeVisible();
  expect(screen.queryByRole('button', { name: 'Refresh review' })).toBeNull();
  const calls = api.mock.calls
    .map((call) => call[1])
    .filter((request) => request.path.endsWith('/authoring/preview'));
  expect(calls).toHaveLength(2);
  expect(calls[0]!.body).toEqual(calls[1]!.body);
  expect(calls[0]!.key).toBe(calls[1]!.key);
  expect(calls[1]!.body).toMatchObject({
    expected_version: 1,
    expected_generation: 8,
  });
});
