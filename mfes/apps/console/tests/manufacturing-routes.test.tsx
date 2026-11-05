import { beforeEach, expect, it, vi } from 'vitest';
import { render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ProductProfileRevision } from '../app/components/ProductProfileRevision';
import { masterConfig } from '../app/lib/catalog-masters';
import { allowedProductProfileRequest } from '../app/lib/product-profile-request-policy';
import {
  routeStepBody,
  verifyRouteSteps,
  type RouteStep,
} from '../app/lib/manufacturing-routes';
import { serviceCall } from '../app/lib/service-call';
import {
  access,
  response,
  resetFixtures,
  COMPANY,
  RECORD,
  SOURCE,
  page,
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
const OPERATION = '01990000-0000-7000-8000-000000000005';
const STEP = '01990000-0000-7000-8000-000000000006';
const routeAccess = {
  ...access,
  'manufacturing-routes': true,
  'manufacturing-operations': true,
};
const step: RouteStep & { id: string } = {
  id: STEP,
  sequence: 1,
  operation_revision_id: OPERATION,
  setup_minutes: '0.0000',
  run_minutes: '0.1250',
  lead_time_minutes: '0.0000',
  time_basis: 'PER_OUTPUT_UNIT',
  quantity_basis: '1.0000',
};
const reference = {
  id: OPERATION,
  operation_id: RECORD,
  code: 'CUT',
  name: 'Cutting',
  revision: 1,
  status: 'PUBLISHED',
  is_active: true,
};
beforeEach(() => {
  vi.clearAllMocks();
  resetFixtures();
  window.history.replaceState(null, '', '/');
  api.mockImplementation(async (_endpoint, request) => {
    if (request.path.includes('/operation-options'))
      return { items: [reference], page } as never;
    if (request.path.includes('/operation-references/'))
      return reference as never;
    if (request.path.includes('/steps?'))
      return { items: [{ ...step, revision_id: SOURCE }], page } as never;
    return response(request) as never;
  });
});
const open = (id?: string, options = routeAccess) =>
  render(
    <ProductProfileRevision
      company={COMPANY}
      config={masterConfig('manufacturing-routes')!}
      parentId={RECORD}
      id={id}
      canManage
      access={options}
    />,
  );

it('keeps route collections and reference reads inside a closed company boundary', () => {
  const root = '/v1/companies/' + COMPANY + '/manufacturing-routes';
  expect(
    allowedProductProfileRequest(
      'GET',
      root +
        '/' +
        RECORD +
        '/revisions/' +
        SOURCE +
        '/steps?limit=50&sort=sequence',
    ),
  ).toBe(true);
  expect(
    allowedProductProfileRequest(
      'POST',
      root + '/' + RECORD + '/revisions/' + SOURCE + '/steps',
    ),
  ).toBe(false);
  expect(
    allowedProductProfileRequest(
      'GET',
      root + '/operation-options?q=Cut&limit=50',
    ),
  ).toBe(true);
  expect(
    allowedProductProfileRequest(
      'GET',
      root + '/operation-references/' + OPERATION,
    ),
  ).toBe(true);
  expect(
    allowedProductProfileRequest(
      'GET',
      root + '/operation-options?status=DRAFT',
    ),
  ).toBe(false);
  expect(
    allowedProductProfileRequest('POST', root + '/' + RECORD + '/execute'),
  ).toBe(false);
});

it('rejects inexact times and partial or foreign route-step collections', () => {
  expect(
    routeStepBody([{ ...step, run_minutes: '0.00001' }]).errors,
  ).toHaveProperty('steps.0.run_minutes');
  expect(
    routeStepBody([{ ...step, quantity_basis: '0' }]).errors,
  ).toHaveProperty('steps.0.quantity_basis');
  expect(() =>
    verifyRouteSteps(
      {
        items: [{ ...step, revision_id: SOURCE }],
        page: { ...page, has_more: true },
      },
      SOURCE,
      1,
    ),
  ).toThrow();
  expect(() =>
    verifyRouteSteps(
      { items: [{ ...step, revision_id: RECORD }], page },
      SOURCE,
      1,
    ),
  ).toThrow();
  expect(
    verifyRouteSteps(
      { items: [{ ...step, revision_id: SOURCE }], page },
      SOURCE,
      1,
    )[0]?.run_minutes,
  ).toBe('0.1250');
});

it('authors a route with a published operation and sends exact time strings', async () => {
  open();
  await userEvent.type(
    await screen.findByRole('textbox', { name: 'Specification' }),
    'Cut then pack.',
  );
  await userEvent.type(
    screen.getByRole('textbox', { name: 'Change reason' }),
    'Initial route',
  );
  const add = screen.getByRole('button', { name: 'Add step' });
  await waitFor(() => expect(add).toBeEnabled());
  await userEvent.click(add);
  const section = within(screen.getByRole('region', { name: 'Route step 1' }));
  await userEvent.click(
    section.getByRole('combobox', { name: 'Operation revision' }),
  );
  await userEvent.click(await screen.findByRole('option', { name: /Cutting/ }));
  await userEvent.clear(
    section.getByRole('textbox', { name: 'Run time (minutes)' }),
  );
  await userEvent.type(
    section.getByRole('textbox', { name: 'Run time (minutes)' }),
    '0.1250',
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
  expect(write?.[1].body).toMatchObject({
    steps: [
      { sequence: 1, operation_revision_id: OPERATION, run_minutes: '0.1250' },
    ],
  });
  expect(JSON.stringify(write?.[1].body)).not.toContain('_key');
});

it('requires a complete reviewed step set and confirms publication', async () => {
  open(SOURCE);
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
  expect(
    screen.getByRole('textbox', { name: 'Run time (minutes)' }),
  ).toBeDisabled();
});

it('retains existing references when operation read access is unavailable', async () => {
  open(SOURCE, { ...routeAccess, 'manufacturing-operations': false });
  const specification = await screen.findByRole('textbox', {
    name: 'Specification',
  });
  await waitFor(() => expect(specification).toBeEnabled());
  await userEvent.clear(specification);
  await userEvent.type(specification, 'Reviewed unchanged step sequence.');
  await userEvent.click(
    screen.getByRole('button', { name: 'Save draft changes' }),
  );
  expect(
    await screen.findByText(/Draft revision updated successfully/),
  ).toBeVisible();
  const write = api.mock.calls.find(
    ([, request]) => request.method === 'PATCH',
  );
  expect(write?.[1].body).not.toHaveProperty('steps');
  expect(
    api.mock.calls.some(([, request]) =>
      request.path.includes('/operation-references/'),
    ),
  ).toBe(false);
});

it('keeps the chosen operation label visible while its exact reference loads', async () => {
  api.mockImplementation(async (_endpoint, request) => {
    if (request.path.includes('/operation-options'))
      return { items: [reference], page } as never;
    if (request.path.includes('/operation-references/'))
      return new Promise<never>(() => {});
    return response(request) as never;
  });
  open();
  const add = await screen.findByRole('button', { name: 'Add step' });
  await waitFor(() => expect(add).toBeEnabled());
  await userEvent.click(add);
  const select = screen.getByRole('combobox', { name: 'Operation revision' });
  await userEvent.click(select);
  await userEvent.click(await screen.findByRole('option', { name: /Cutting/ }));
  await waitFor(() => expect(select).toHaveValue('Cutting — revision 1'));
});
