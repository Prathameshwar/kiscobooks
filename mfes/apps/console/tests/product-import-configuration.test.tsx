import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { ProductImport } from '../app/components/ProductImport';
import { useProductMode } from '../app/components/ProductModeProvider';
import { serviceCall } from '../app/lib/service-call';
import { downloadProductImport } from '../app/lib/product-import';
import { COMPANY, template, importResponse } from './product-import-fixtures';

vi.mock('../app/components/ProductModeProvider', () => ({
  useProductMode: vi.fn(),
}));
vi.mock('../app/lib/service-call', async (original) => ({
  ...(await original<typeof import('../app/lib/service-call')>()),
  serviceCall: vi.fn(),
}));
vi.mock('../app/lib/product-import', async (original) => ({
  ...(await original<typeof import('../app/lib/product-import')>()),
  downloadProductImport: vi.fn(),
}));
const TYPE = '01990000-0000-7000-8000-000000000010',
  GROUP = '01990000-0000-7000-8000-000000000011';
function mode(advanced: boolean) {
  vi.mocked(useProductMode).mockReturnValue({
    company: COMPANY,
    data: {
      company_id: COMPANY,
      product_family_sku_enabled: advanced,
      row_version: 1,
      policy_generation: 8,
    },
    loading: false,
    failure: null,
    refresh: vi.fn(),
  });
}
beforeEach(() => {
  vi.clearAllMocks();
  mode(true);
  window.history.replaceState(null, '', '/masters/items/import');
  vi.mocked(serviceCall).mockImplementation(async (_, request) => {
    if (request.path.includes('/product-configuration/options/'))
      return {
        items: [
          {
            value: request.path.includes('/groups?') ? GROUP : TYPE,
            label: request.path.includes('/groups?')
              ? 'Retail group'
              : 'Published service type',
          },
        ],
        page: { next_cursor: null },
      } as never;
    if (request.path.includes('/import-templates'))
      return {
        ...template,
        snapshot: {
          ...template.snapshot,
          schemas: {
            ...(template.snapshot.schemas as Record<string, unknown>),
            'simple_product:CREATE': {
              properties: {
                code: { title: 'Product code', type: 'string' },
                name: { title: 'Product name', type: 'string' },
              },
              required: ['code', 'name'],
            },
            'simple_product:UPDATE': {
              properties: { name: { type: 'string' } },
            },
          },
          product_configuration: {
            kind: 'SERVICE',
            as_of: '2026-01-01',
            inventory_profile: false,
            options: [
              { key: 'brand', label: 'Brands', mode: 'DISABLED' },
              { key: 'barcode', label: 'Barcodes', mode: 'REQUIRED' },
            ],
            note: 'Required options must be completed before activation.',
          },
        },
      } as never;
    return importResponse(request.path) as never;
  });
});
it('prepares an advanced product template with selected kind, date, published type and group', async () => {
  const user = userEvent.setup();
  render(<ProductImport company={COMPANY} canManage />);
  await user.selectOptions(
    await screen.findByRole('combobox', { name: 'Product kind' }),
    'SERVICE',
  );
  await user.clear(screen.getByLabelText('Configuration date'));
  await user.type(screen.getByLabelText('Configuration date'), '2026-01-01');
  await user.type(
    screen.getByRole('combobox', {
      name: 'Published product type for template',
    }),
    'Pu',
  );
  await user.click(
    await screen.findByRole('option', { name: 'Published service type' }),
  );
  await user.type(
    screen.getByRole('combobox', { name: 'Product group for template' }),
    'Re',
  );
  await user.click(await screen.findByRole('option', { name: 'Retail group' }));
  await user.click(screen.getByRole('button', { name: 'Download template' }));
  await waitFor(() => expect(downloadProductImport).toHaveBeenCalled());
  const call = vi
    .mocked(serviceCall)
    .mock.calls.find(
      ([, request]) =>
        request.method === 'POST' && request.path.endsWith('/import-templates'),
    )![1];
  expect(call.body).toEqual({
    definition: 'products',
    parameters: {
      resource: 'product_family',
      kind: 'SERVICE',
      as_of: '2026-01-01',
      product_type_revision_id: TYPE,
      group_id: GROUP,
    },
  });
  expect(
    vi
      .mocked(serviceCall)
      .mock.calls.filter(([, request]) =>
        request.path.includes('/product-configuration/options/'),
      )
      .every(([, request]) => request.path.includes('kind=SERVICE')),
  ).toBe(true);
  await user.click(screen.getByText('Template column guide'));
  expect(
    screen.getByRole('heading', {
      name: 'Product configuration for this template',
    }),
  ).toBeVisible();
  expect(screen.getByText('Disabled', { exact: true })).toBeVisible();
  expect(
    screen.getByText('Required before activation', { exact: true }),
  ).toBeVisible();
});
it('offers only the supported update operation for existing advanced SKUs', async () => {
  mode(true);
  const user = userEvent.setup();
  render(<ProductImport company={COMPANY} canManage />);
  await user.selectOptions(
    await screen.findByRole('combobox', { name: 'Import content' }),
    'item',
  );
  expect(
    screen.getByRole('combobox', { name: 'Import operation' }),
  ).toHaveValue('UPDATE_ONLY');
  expect(
    screen.getByRole('option', { name: 'Create new products only' }),
  ).toBeDisabled();
  expect(screen.queryByLabelText('Configuration date')).not.toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Download template' }));
  await waitFor(() => expect(downloadProductImport).toHaveBeenCalled());
  expect(vi.mocked(downloadProductImport).mock.calls[0]![0].path).toContain(
    'action=UPDATE',
  );
});
it('locks template context while a file is selected and preserves it after a mode change', async () => {
  const user = userEvent.setup();
  const view = render(<ProductImport company={COMPANY} canManage />);
  await user.click(
    await screen.findByRole('button', { name: 'Download template' }),
  );
  await waitFor(() => expect(downloadProductImport).toHaveBeenCalled());
  await user.upload(
    document.querySelector<HTMLInputElement>('input[type=file]')!,
    new File(
      [
        '_import_schema_version,1\n_key,_set,_resource,_action,name\nr,g,simple_product,AUTO,Product',
      ],
      'products.csv',
      { type: 'text/csv' },
    ),
  );
  expect(screen.getByLabelText('Configuration date')).toBeDisabled();
  mode(false);
  view.rerender(<ProductImport company={COMPANY} canManage />);
  expect(screen.getByText(/Your import is preserved/)).toBeVisible();
  expect(screen.getByText('products.csv', { exact: true })).toBeVisible();
  expect(
    screen.getByRole('button', { name: 'Upload and prepare validation' }),
  ).toBeDisabled();
});
it.each([409, 410])(
  'refreshes an outdated template after download status %s while retaining the selected file',
  async (status) => {
    const user = userEvent.setup();
    render(<ProductImport company={COMPANY} canManage />);
    const download = await screen.findByRole('button', {
      name: 'Download template',
    });
    await user.click(download);
    await waitFor(() => expect(downloadProductImport).toHaveBeenCalledTimes(1));
    await user.upload(
      document.querySelector<HTMLInputElement>('input[type=file]')!,
      new File(
        [
          '_import_schema_version,1\n_key,_set,_resource,_action,name\nr,g,simple_product,AUTO,Product',
        ],
        'products.csv',
        { type: 'text/csv' },
      ),
    );
    vi.mocked(downloadProductImport).mockRejectedValueOnce({
      status,
      message: 'Prepare a current product template.',
    });
    await user.click(download);
    await user.click(
      await screen.findByRole('button', { name: 'Reload and review' }),
    );
    expect(screen.getByText('products.csv', { exact: true })).toBeVisible();
    expect(screen.getByLabelText('Configuration date')).toBeDisabled();
    await user.click(
      await screen.findByRole('button', { name: 'Download template' }),
    );
    await waitFor(() => expect(downloadProductImport).toHaveBeenCalledTimes(3));
    expect(
      vi
        .mocked(serviceCall)
        .mock.calls.filter(
          ([, request]) =>
            request.method === 'POST' &&
            request.path.endsWith('/import-templates'),
        ),
    ).toHaveLength(2);
    expect(
      screen.queryByRole('button', { name: 'Reload and review' }),
    ).not.toBeInTheDocument();
  },
);
