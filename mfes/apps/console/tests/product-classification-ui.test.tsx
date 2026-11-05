import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { ProductCatalogDirectory } from '../app/components/ProductCatalogDirectory';
import { ProductCatalogEditor } from '../app/components/ProductCatalogEditor';
import { ProductCatalogDetail } from '../app/components/ProductCatalogDetail';
import { ProductTypeRevision } from '../app/components/ProductTypeRevision';
import { masterConfig } from '../app/lib/catalog-masters';
import { serviceCall } from '../app/lib/service-call';
import { goTo } from '../app/lib/navigate';

import { classificationResources, type ClassificationResource } from '../app/lib/product-classification-resources';
import { COMPANY, RECORD, SOURCE, access, fields, record, response, resetFixtures } from './product-classification-fixtures';
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
      ['POST', 'PATCH', 'PUT'].includes(request.method ?? 'GET'),
    );
beforeEach(() => {
  vi.clearAllMocks();
  resetFixtures();
  window.history.replaceState(null, '', '/');
  api.mockImplementation(
    async (_endpoint, request) => response(request) as never,
  );
});
async function choose(label: string, option: string) {
  await userEvent.click(await screen.findByRole('combobox', { name: label }));
  await userEvent.click(
    await screen.findByRole('option', { name: new RegExp(option) }),
  );
}
it('selects a scoped brand using the keyboard and preserves Escape navigation', async () => {
  render(
    <ProductCatalogEditor
      company={COMPANY}
      config={masterConfig('brand-series')!}
      access={access}
    />,
  );
  const combo = await screen.findByRole('combobox', { name: 'Brand' });
  act(() => combo.focus());
  await userEvent.keyboard('{ArrowDown}');
  await screen.findByRole('option', { name: /Standard brand/ });
  await userEvent.keyboard('{ArrowDown}{Enter}');
  expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  expect(combo).toHaveValue('Standard brand');
  await userEvent.click(combo);
  await userEvent.keyboard('{Escape}');
  expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  expect(combo).toHaveFocus();
});
it('shows an honest count on a subsequent cursor page and restores the first-page range', async () => {
  api.mockImplementation(async (_endpoint, request) => {
    const result = response(request);
    return request.path.includes('/brands?')
      ? ({
          ...(result as object),
          page: {
            limit: 25,
            has_more: !request.path.includes('cursor='),
            next_cursor: request.path.includes('cursor=') ? null : 'next',
          },
        } as never)
      : (result as never);
  });
  render(
    <ProductCatalogDirectory
      company={COMPANY}
      config={masterConfig('brands')!}
      access={access}
      canManage
    />,
  );
  await screen.findByText('Showing 1–1');
  await userEvent.click(
    screen.getByRole('button', { name: 'Next page of records' }),
  );
  expect(await screen.findByText('Showing 1 record')).toBeVisible();
  await userEvent.click(
    screen.getByRole('button', { name: 'Previous page of records' }),
  );
  expect(await screen.findByText('Showing 1–1')).toBeVisible();
});
it.each(classificationResources.filter(resource => !['items', 'product-families'].includes(resource)))(
  'opens the %s directory with search and kebab navigation',
  async (resource) => {
    render(
      <ProductCatalogDirectory
        company={COMPANY}
        config={masterConfig(resource)!}
        access={access}
        canManage
      />,
    );
    const row = record(resource);
    await userEvent.click(
      await screen.findByRole('button', { name: 'Actions for ' + row.name }),
    );
    expect(
      screen.getByRole('menuitem', { name: 'View details' }),
    ).toHaveAttribute(
      'href',
      expect.stringContaining(`/masters/${resource}/${RECORD}?returnTo=`),
    );
    expect(
      screen.getByRole('menuitem', { name: 'Edit details' }),
    ).toHaveAttribute('href', expect.stringContaining('/edit?returnTo='));
  },
);
it.each([
  'brands',
  'category-schemes',
  'product-types',
  'brand-series',
  'item-categories',
  'manufacturer-sites',
] as ClassificationResource[])(
  'creates %s with native validation and a saved-record link',
  async (resource) => {
    const config = masterConfig(resource)!;
    render(
      <ProductCatalogEditor
        company={COMPANY}
        config={config}
        access={access}
      />,
    );
    await userEvent.click(
      await screen.findByRole('button', { name: `Create ${config.singular}` }),
    );
    expect(writes()).toHaveLength(0);
    await userEvent.type(screen.getByRole('textbox', { name: 'Code' }), 'NEW');
    await userEvent.type(
      screen.getByRole('textbox', { name: 'Name' }),
      'New record',
    );
    if (resource === 'brand-series') await choose('Brand', 'Standard brand');
    if (resource === 'item-categories')
      await choose('Category scheme', 'Standard category scheme');
    if (resource === 'manufacturer-sites') {
      await choose('Manufacturer', 'General reference');
      await choose('Country', 'India');
    }
    await userEvent.click(
      screen.getByRole('button', { name: `Create ${config.singular}` }),
    );
    expect(
      await screen.findByRole('link', { name: `View ${config.singular}` }),
    ).toHaveAttribute(
      'href',
      expect.stringContaining('/masters/' + resource + '/'),
    );
    expect(writes().at(-1)?.[1].body).toMatchObject({
      code: 'NEW',
      name: 'New record',
    });
  },
);
it('retains an interrupted create and retries the exact body and idempotency key', async () => {
  let interrupted = true;
  api.mockImplementation(async (_endpoint, request) => {
    if (request.method === 'POST' && interrupted) {
      interrupted = false;
      throw { status: 503, message: 'Response interrupted' };
    }
    return response(request) as never;
  });
  render(
    <ProductCatalogEditor
      company={COMPANY}
      config={masterConfig('brands')!}
      access={access}
    />,
  );
  await userEvent.type(
    await screen.findByRole('textbox', { name: 'Code' }),
    'NEW',
  );
  await userEvent.type(screen.getByRole('textbox', { name: 'Name' }), 'Brand');
  await userEvent.click(screen.getByRole('button', { name: 'Create brand' }));
  await userEvent.click(
    await screen.findByRole('button', { name: 'Retry same save' }),
  );
  expect(await screen.findByRole('link', { name: 'View brand' })).toBeVisible();
  expect(writes()[0]![1].key).toBe(writes()[1]![1].key);
  expect(writes()[0]![1].body).toEqual(writes()[1]![1].body);
});
it('saves a partial edit while retaining read-denied brand ownership', async () => {
  api.mockImplementation(async (_endpoint, request) => {
    const value = response(request);
    if (request.path.includes('/field-set'))
      return {
        ...(value as object),
        fields: fields('catalog.brand', 'update').map((field) =>
          field.key === 'owner_party_id'
            ? { ...field, visible: false, writable: false }
            : field,
        ),
      } as never;
    return value as never;
  });
  render(
    <ProductCatalogEditor
      company={COMPANY}
      config={masterConfig('brands')!}
      id={RECORD}
      access={access}
    />,
  );
  const name = await screen.findByRole('textbox', { name: 'Name' });
  await userEvent.clear(name);
  await userEvent.type(name, 'Renamed');
  await userEvent.click(screen.getByRole('button', { name: 'Save changes' }));
  expect(await screen.findByText('Changes saved.')).toBeVisible();
  expect(writes().at(-1)?.[1].body).toEqual({
    expected_version: 4,
    name: 'Renamed',
  });
});
it('freezes product type identity after its first revision', async () => {
  render(
    <ProductCatalogEditor
      company={COMPANY}
      config={masterConfig('product-types')!}
      id={RECORD}
      access={access}
    />,
  );
  expect(await screen.findByRole('textbox', { name: 'Code' })).toBeDisabled();
  expect(screen.getByRole('combobox', { name: 'Kind' })).toBeDisabled();
});
it('creates and saves type requirements with closed native option sets', async () => {
  render(
    <ProductTypeRevision
      company={COMPANY}
      parentId={RECORD}
      canManage
      access={access}
    />,
  );
  await userEvent.click(
    await screen.findByRole('button', { name: 'Save draft requirements' }),
  );
  expect(
    await screen.findByRole('link', { name: 'Review saved draft' }),
  ).toBeVisible();
  expect(writes().at(-1)?.[1].body).toMatchObject({
    inventory_modes: ['NON_STOCK'],
    tracking_modes: ['NONE'],
    unit_dimensions: ['COUNT'],
    allow_variants: true,
  });
});
it('separates publishing from editing and confirms immutable publication', async () => {
  api.mockImplementation(async (_endpoint, request) => {
    const result = response(request);
    if (
      request.path.includes('/field-set') &&
      !request.path.includes('operation=publish')
    )
      return {
        ...(result as object),
        fields: fields('catalog.product_type_revision', 'update').map(
          (field) => ({ ...field, writable: false }),
        ),
      } as never;
    return result as never;
  });
  render(
    <ProductTypeRevision
      company={COMPANY}
      parentId={RECORD}
      id={SOURCE}
      canManage={false}
      access={access}
    />,
  );
  await userEvent.click(
    await screen.findByRole('button', { name: 'Publish requirements' }),
  );
  await userEvent.click(
    within(screen.getByRole('dialog')).getByRole('button', {
      name: 'Publish requirements',
    }),
  );
  expect(await screen.findByText(/Requirements published/)).toBeVisible();
  expect(writes().at(-1)?.[1].body).toEqual({ expected_version: 4 });
  expect(
    screen.queryByRole('button', { name: 'Publish requirements' }),
  ).not.toBeInTheDocument();
});
it('does not offer publication to a manager without publish authority', async () => {
  render(
    <ProductTypeRevision
      company={COMPANY}
      parentId={RECORD}
      id={SOURCE}
      canManage
      access={{ ...access, publish: false }}
    />,
  );
  await screen.findByRole('button', { name: 'Save draft requirements' });
  expect(
    screen.queryByRole('button', { name: 'Publish requirements' }),
  ).not.toBeInTheDocument();
});
it('reviews scheme impact before committing its policy change', async () => {
  render(
    <ProductCatalogDetail
      company={COMPANY}
      config={masterConfig('category-schemes')!}
      id={RECORD}
      canManage
      access={access}
    />,
  );
  await screen.findByRole('textbox', { name: 'Code' });
  await userEvent.click(screen.getByRole('button', { name: 'Record actions' }));
  await userEvent.click(
    screen.getByRole('menuitem', { name: 'Review scheme rules' }),
  );
  await userEvent.click(
    within(screen.getByRole('dialog')).getByRole('button', {
      name: 'Prepare review',
    }),
  );
  expect(await screen.findByText('Affected families')).toBeVisible();
  await userEvent.click(
    within(screen.getByRole('dialog')).getByRole('button', {
      name: 'Confirm change',
    }),
  );
  expect(
    await screen.findByText(/Category scheme rules updated/),
  ).toBeVisible();
  expect(writes().at(-1)?.[1].body).toMatchObject({
    expected_version: 4,
    preview_token: 'review-proof',
    membership_mode: 'SINGLE',
    is_required: false,
  });
});
it.each([401, 403, 422, 500])(
  'renders an actionable %s load failure',
  async (status) => {
    api.mockRejectedValue({ status, message: 'Unable to load classification' });
    render(
      <ProductCatalogDirectory
        company={COMPANY}
        config={masterConfig('brands')!}
        canManage
        access={access}
      />,
    );
    expect(
      await screen.findByText('Unable to load classification'),
    ).toBeVisible();
    expect(
      screen.queryByRole('button', { name: /Actions for/ }),
    ).not.toBeInTheDocument();
  },
);
it('recovers an interrupted service review using the same review request', async () => {
  let interrupted = true;
  api.mockImplementation(async (_endpoint, request) => {
    if (request.path.endsWith('/transition-preview') && interrupted) {
      interrupted = false;
      throw { status: 503, message: 'Review interrupted' };
    }
    return response(request) as never;
  });
  render(
    <ProductCatalogDetail
      company={COMPANY}
      config={masterConfig('category-schemes')!}
      id={RECORD}
      canManage
      access={access}
    />,
  );
  await screen.findByRole('textbox', { name: 'Code' });
  await userEvent.click(screen.getByRole('button', { name: 'Record actions' }));
  await userEvent.click(
    screen.getByRole('menuitem', { name: 'Review scheme rules' }),
  );
  await userEvent.click(
    within(screen.getByRole('dialog')).getByRole('button', {
      name: 'Prepare review',
    }),
  );
  await screen.findAllByText('Review interrupted');
  await userEvent.click(
    within(screen.getByRole('dialog')).getByRole('button', {
      name: 'Retry same review',
    }),
  );
  expect(await screen.findByText('Affected families')).toBeVisible();
  expect(writes()[0]![1].key).toBe(writes()[1]![1].key);
  expect(writes()[0]![1].body).toEqual(writes()[1]![1].body);
});
it('recovers unconfirmed publication after closing the dialog without offering a draft save', async () => {
  api.mockImplementation(async (_endpoint, request) => {
    if (request.path.endsWith('/publish'))
      throw { status: 503, message: 'Publication interrupted' };
    return response(request) as never;
  });
  render(
    <ProductTypeRevision
      company={COMPANY}
      parentId={RECORD}
      id={SOURCE}
      canManage
      access={access}
    />,
  );
  await userEvent.click(
    await screen.findByRole('button', { name: 'Publish requirements' }),
  );
  await userEvent.click(
    within(screen.getByRole('dialog')).getByRole('button', {
      name: 'Publish requirements',
    }),
  );
  await screen.findByText('Publication interrupted');
  await userEvent.click(
    within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancel' }),
  );
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(
    screen.getByRole('button', { name: 'Retry same publication' }),
  ).toBeVisible();
  expect(
    screen.getByRole('button', { name: 'Save draft requirements' }),
  ).toBeDisabled();
});
