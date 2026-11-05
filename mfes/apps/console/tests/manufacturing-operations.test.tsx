import { beforeEach, expect, it, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { masterConfig } from '../app/lib/catalog-masters';
import { allowedProductProfileRequest } from '../app/lib/product-profile-request-policy';
import { ProductProfileRevision } from '../app/components/ProductProfileRevision';
import { ProductProfileEditor } from '../app/components/ProductProfileEditor';
import { ProductProfileDirectory } from '../app/components/ProductProfileDirectory';
import { serviceCall } from '../app/lib/service-call';
import {
  access,
  response,
  revision,
  resetFixtures,
  RECORD as PARENT,
  SOURCE,
  COMPANY as OWNER,
  page as pageMeta,
} from './product-profile-fixtures';

vi.mock('../app/lib/service-call', async (original) => ({
  ...(await original<typeof import('../app/lib/service-call')>()),
  serviceCall: vi.fn(),
}));
vi.mock('../app/lib/navigate', () => ({
  goTo: vi.fn(),
  signInUrl: () => '/sign-in',
}));
const api = vi.mocked(serviceCall);
const operationAccess = { ...access, 'manufacturing-operations': true };
beforeEach(() => {
  vi.clearAllMocks();
  resetFixtures();
  window.history.replaceState(null, '', '/');
  api.mockImplementation(
    async (_endpoint, request) => response(request) as never,
  );
});

const COMPANY = '01990000-0000-7000-8000-000000000001';
const RECORD = '01990000-0000-7000-8000-000000000002';
const REVISION = '01990000-0000-7000-8000-000000000003';
it('registers manufacturing operations and a closed, company-scoped revision boundary', () => {
  expect(masterConfig('manufacturing-operations')?.entity).toBe(
    'catalog.manufacturing_operation',
  );
  const root = '/v1/companies/' + COMPANY + '/manufacturing-operations';
  expect(allowedProductProfileRequest('GET', root + '?limit=50&q=Cut')).toBe(
    true,
  );
  expect(
    allowedProductProfileRequest(
      'POST',
      root + '/' + RECORD + '/revisions/' + REVISION + '/retire',
    ),
  ).toBe(true);
  expect(allowedProductProfileRequest('DELETE', root + '/' + RECORD)).toBe(
    false,
  );
  expect(
    allowedProductProfileRequest('POST', root + '/' + RECORD + '/execute'),
  ).toBe(false);
});

it('provides a searchable operation directory and creation through the shared form layout', async () => {
  const view = render(
    <ProductProfileDirectory
      company={OWNER}
      config={masterConfig('manufacturing-operations')!}
      canManage
      access={operationAccess}
    />,
  );
  expect(
    await screen.findByRole('link', { name: 'New manufacturing operation' }),
  ).toBeVisible();
  expect(
    screen.getByRole('heading', { name: 'Manufacturing operations' }),
  ).toBeVisible();
  view.unmount();
  render(
    <ProductProfileEditor
      company={OWNER}
      config={masterConfig('manufacturing-operations')!}
      access={operationAccess}
    />,
  );
  await userEvent.type(
    await screen.findByRole('textbox', { name: 'Code' }),
    'CUT',
  );
  await userEvent.type(
    screen.getByRole('textbox', { name: 'Name' }),
    'Cutting',
  );
  await userEvent.click(
    screen.getByRole('button', { name: 'Create manufacturing operation' }),
  );
  await waitFor(() =>
    expect(
      api.mock.calls.some(
        ([, r]) =>
          r.method === 'POST' && r.path.endsWith('/manufacturing-operations'),
      ),
    ).toBe(true),
  );
});

it('creates an operation draft using native sections and an attached action footer', async () => {
  render(
    <ProductProfileRevision
      company={OWNER}
      config={masterConfig('manufacturing-operations')!}
      parentId={PARENT}
      canManage
      access={operationAccess}
    />,
  );
  await userEvent.type(
    await screen.findByRole('textbox', { name: 'Specification' }),
    'Cut to approved dimensions.',
  );
  await userEvent.type(
    screen.getByRole('textbox', { name: 'Change reason' }),
    'Initial definition',
  );
  const save = screen.getByRole('button', { name: 'Create draft revision' });
  expect(save.closest('.janso-card__footer')).not.toBeNull();
  await userEvent.click(save);
  expect(
    await screen.findByText(/Draft revision created successfully/),
  ).toBeVisible();
  const write = api.mock.calls.find(
    ([, r]) => r.method === 'POST' && r.path.endsWith('/revisions'),
  )!;
  expect(write[1].body).toMatchObject({
    specification: 'Cut to approved dimensions.',
    change_reason: 'Initial definition',
  });
});

it('publishes the reviewed operation and offers an immutable specification afterward', async () => {
  render(
    <ProductProfileRevision
      company={OWNER}
      config={masterConfig('manufacturing-operations')!}
      parentId={PARENT}
      id={SOURCE}
      canManage
      access={operationAccess}
    />,
  );
  const publish = await screen.findByRole('button', {
    name: 'Publish revision',
  });
  await waitFor(() => expect(publish).toBeEnabled());
  await userEvent.click(publish);
  await userEvent.click(
    within(screen.getByRole('dialog')).getByRole('button', {
      name: 'Publish revision',
    }),
  );
  expect(
    await screen.findByText(/Revision published successfully/),
  ).toBeVisible();
  expect(screen.getByRole('textbox', { name: 'Specification' })).toBeDisabled();
  expect(
    api.mock.calls.find(([, r]) => r.path.endsWith('/publish'))?.[1].body,
  ).toEqual({ expected_version: 4 });
});

it('retires a published operation revision without editing its specification', async () => {
  const published = {
    ...revision('manufacturing-operations'),
    status: 'PUBLISHED',
    published_at: '2026-10-27T10:00:00Z',
  };
  api.mockImplementation(async (_endpoint, request) => {
    if (
      request.path.endsWith('/revisions/' + SOURCE) &&
      (request.method ?? 'GET') === 'GET'
    )
      return published as never;
    if (request.path.endsWith('/retire'))
      return { ...published, status: 'RETIRED', row_version: 5 } as never;
    return response(request) as never;
  });
  render(
    <ProductProfileRevision
      company={OWNER}
      config={masterConfig('manufacturing-operations')!}
      parentId={PARENT}
      id={SOURCE}
      canManage
      access={operationAccess}
    />,
  );
  const retire = await screen.findByRole('button', { name: 'Retire revision' });
  await waitFor(() => expect(retire).toBeEnabled());
  await userEvent.click(retire);
  await userEvent.click(
    within(screen.getByRole('dialog')).getByRole('button', {
      name: 'Retire revision',
    }),
  );
  expect(await screen.findByText(/Revision retired/)).toBeVisible();
  expect(screen.getByRole('textbox', { name: 'Specification' })).toBeDisabled();
  expect(
    api.mock.calls.find(([, r]) => r.path.endsWith('/retire'))?.[1].body,
  ).toEqual({ expected_version: 4 });
});

it('selects an active service SKU through the bounded company reference endpoint', async () => {
  api.mockImplementation(async (_endpoint, request) => {
    if (request.path.includes('/manufacturing-operations/service-options'))
      return {
        items: [
          {
            id: SOURCE,
            name: 'Cutting service',
            sku: 'CUT-SVC',
            status: 'ACTIVE',
          },
        ],
        page: pageMeta,
      } as never;
    if (request.path.endsWith('/items/' + SOURCE))
      return {
        id: SOURCE,
        company_id: OWNER,
        name: 'Cutting service',
        sku: 'CUT-SVC',
        status: 'ACTIVE',
      } as never;
    return response(request) as never;
  });
  render(
    <ProductProfileRevision
      company={OWNER}
      config={masterConfig('manufacturing-operations')!}
      parentId={PARENT}
      canManage
      access={{ ...operationAccess, serviceItems: true }}
    />,
  );
  await userEvent.type(
    await screen.findByRole('textbox', { name: 'Specification' }),
    'Inspect and cut.',
  );
  await userEvent.type(
    screen.getByRole('textbox', { name: 'Change reason' }),
    'Initial service definition',
  );
  await userEvent.click(screen.getByRole('combobox', { name: 'Service SKU' }));
  await userEvent.click(
    await screen.findByRole('option', { name: /Cutting service/ }),
  );
  await userEvent.click(
    screen.getByRole('button', { name: 'Create draft revision' }),
  );
  expect(
    await screen.findByText(/Draft revision created successfully/),
  ).toBeVisible();
  const write = api.mock.calls.find(
    ([, request]) =>
      request.method === 'POST' && request.path.endsWith('/revisions'),
  );
  expect(write?.[1].body).toMatchObject({ service_item_id: SOURCE });
  expect(
    api.mock.calls.some(([, request]) =>
      request.path.includes('/product-configuration'),
    ),
  ).toBe(false);
});

it('keeps publication disabled when generated status is protected for write', async () => {
  api.mockImplementation(async (_endpoint, request) => {
    const result = response(request) as {
      fields?: Array<{ key: string; writable: boolean }>;
    };
    if (request.path.includes('operation=publish') && result.fields)
      result.fields = result.fields.map((field) =>
        field.key === 'status' ? { ...field, writable: false } : field,
      );
    return result as never;
  });
  render(
    <ProductProfileRevision
      company={OWNER}
      config={masterConfig('manufacturing-operations')!}
      parentId={PARENT}
      id={SOURCE}
      canManage
      access={operationAccess}
    />,
  );
  expect(
    await screen.findByRole('button', { name: 'Publish revision' }),
  ).toBeDisabled();
  expect(api.mock.calls.some(([, request]) => request.method === 'POST')).toBe(
    false,
  );
});
