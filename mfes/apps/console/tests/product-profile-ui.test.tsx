import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { ProductProfileDirectory } from '../app/components/ProductProfileDirectory';
import { ProductProfileEditor } from '../app/components/ProductProfileEditor';
import { ProductProfileDetail } from '../app/components/ProductProfileDetail';
import { ProductProfileRevision } from '../app/components/ProductProfileRevision';
import { masterConfig } from '../app/lib/catalog-masters';
import { serviceCall } from '../app/lib/service-call';
import {
  productProfileResources,
  type ProductProfileResource,
} from '../app/lib/product-profile-resources';
import {
  COMPANY,
  RECORD,
  SOURCE,
  access,
  fields,
  master,
  response,
  revision,
  resetFixtures,
} from './product-profile-fixtures';
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
const openRevision = (
  resource: ProductProfileResource,
  id?: string,
  manage = true,
  publish = true,
) =>
  render(
    <ProductProfileRevision
      company={COMPANY}
      config={masterConfig(resource)!}
      parentId={RECORD}
      id={id}
      canManage={manage}
      access={{ ...access, publish }}
    />,
  );
it.each(productProfileResources)(
  'has scoped %s directory links and a working action menu',
  async (resource) => {
    render(
      <ProductProfileDirectory
        company={COMPANY}
        config={masterConfig(resource)!}
        canManage
        access={access}
        initialQuery="q=Standard&is_active=true"
      />,
    );
    const menu = await screen.findByRole('button', {
      name: 'Actions for Standard profile',
    });
    await userEvent.click(menu);
    expect(
      screen.getByRole('menuitem', { name: 'View profile and revisions' }),
    ).toHaveAttribute('href', expect.stringContaining('returnTo='));
    expect(
      screen.getByRole('link', {
        name: 'New ' + masterConfig(resource)!.singular,
      }),
    ).toHaveAttribute('href', expect.stringContaining('/new?returnTo='));
    expect(
      api.mock.calls.some(
        ([, request]) =>
          request.path.includes('q=Standard') &&
          request.path.includes('is_active=true'),
      ),
    ).toBe(true);
  },
);
it.each(productProfileResources)(
  'creates a %s identity and navigates to revisions',
  async (resource) => {
    render(
      <ProductProfileEditor
        company={COMPANY}
        config={masterConfig(resource)!}
        access={access}
      />,
    );
    await userEvent.type(
      await screen.findByRole('textbox', { name: 'Code' }),
      'NEW',
    );
    await userEvent.type(
      screen.getByRole('textbox', { name: 'Name' }),
      'New profile',
    );
    await userEvent.click(
      screen.getByRole('button', { name: 'Create profile' }),
    );
    expect(await screen.findByText(/created successfully/)).toBeVisible();
    expect(writes()[0]?.[1].body).toEqual({ code: 'NEW', name: 'New profile' });
    expect(
      screen.getByRole('link', { name: 'View profile and revisions' }),
    ).toHaveAttribute(
      'href',
      expect.stringContaining('/masters/' + resource + '/'),
    );
  },
);
it('locks a profile code once revisions exist while allowing a name edit', async () => {
  render(
    <ProductProfileEditor
      company={COMPANY}
      config={masterConfig('handling-profiles')!}
      id={RECORD}
      access={access}
    />,
  );
  expect(await screen.findByRole('textbox', { name: 'Code' })).toBeDisabled();
  const name = screen.getByRole('textbox', { name: 'Name' });
  await userEvent.clear(name);
  await userEvent.type(name, 'Cold handling');
  await userEvent.click(screen.getByRole('button', { name: 'Save changes' }));
  await screen.findByText(/updated successfully/);
  expect(writes()[0]?.[1].body).toEqual({
    expected_version: 4,
    name: 'Cold handling',
  });
});
it.each(productProfileResources)(
  'opens %s history and confirms availability changes',
  async (resource) => {
    render(
      <ProductProfileDetail
        company={COMPANY}
        config={masterConfig(resource)!}
        id={RECORD}
        canManage
        access={access}
      />,
    );
    expect(
      await screen.findByRole('link', { name: 'New draft revision' }),
    ).toHaveAttribute('href', expect.stringContaining('/revisions/new'));
    await userEvent.click(
      screen.getByRole('button', { name: 'Profile actions' }),
    );
    await userEvent.click(screen.getByRole('menuitem', { name: 'Deactivate' }));
    expect(writes()).toHaveLength(0);
    await userEvent.click(
      within(screen.getByRole('dialog')).getByRole('button', {
        name: 'Deactivate',
      }),
    );
    await screen.findByText(/deactivated successfully/);
    expect(writes()[0]?.[1].path).toContain('/' + RECORD + '/deactivate');
    expect(writes()[0]?.[1].body).toEqual({ expected_version: 4 });
    expect(
      screen.queryByRole('link', { name: 'New draft revision' }),
    ).not.toBeInTheDocument();
  },
);
it.each(productProfileResources)(
  'creates a native %s draft',
  async (resource) => {
    openRevision(resource);
    const create = await screen.findByRole('button', {
      name: 'Create draft revision',
    });
    await waitFor(() => expect(create).toBeEnabled());
    if (resource === 'warranty-policies')
      await userEvent.type(
        screen.getByRole('textbox', { name: 'Duration' }),
        '24',
      );
    await userEvent.click(create);
    await screen.findByText(/Draft revision created successfully/);
    expect(writes()[0]?.[1].path).toContain('/' + RECORD + '/revisions');
    expect(writes()[0]?.[1].body).not.toHaveProperty('expected_version');
    expect(
      screen.getByRole('link', { name: 'View saved revision' }),
    ).toHaveAttribute('href', expect.stringContaining('/revisions/'));
  },
);
it('saves exact temperature text, its unit and multiline instructions', async () => {
  openRevision('handling-profiles');
  const min = await screen.findByRole('textbox', {
    name: 'Minimum temperature',
  });
  await userEvent.type(min, '-273.1500');
  await userEvent.type(
    screen.getByRole('textbox', { name: 'Maximum temperature' }),
    '4.1234',
  );
  await userEvent.type(
    screen.getByRole('textbox', { name: 'Instructions' }),
    'Cold storage.\nKeep dry.',
  );
  await userEvent.click(
    screen.getByRole('button', { name: 'Create draft revision' }),
  );
  await screen.findByText(/Draft revision created successfully/);
  expect(writes()[0]?.[1].body).toMatchObject({
    temperature_min: '-273.1500',
    temperature_max: '4.1234',
    temperature_unit: 'CELSIUS',
    instructions: 'Cold storage.\nKeep dry.',
  });
});
it('replaces a complete return condition set and permits a zero-day window', async () => {
  openRevision('return-policies', SOURCE);
  const unused = await screen.findByRole('checkbox', { name: 'Unused' });
  await waitFor(() => expect(unused).toBeChecked());
  await userEvent.click(unused);
  await userEvent.click(
    screen.getByRole('checkbox', { name: 'Proof of purchase' }),
  );
  const window = screen.getByRole('textbox', { name: 'Window days' });
  await userEvent.clear(window);
  await userEvent.type(window, '0');
  await userEvent.click(
    screen.getByRole('button', { name: 'Save draft changes' }),
  );
  await screen.findByText(/Draft revision updated successfully/);
  expect(writes()[0]?.[1].body).toEqual({
    expected_version: 4,
    window_days: 0,
    condition_codes: ['UNDAMAGED', 'PROOF_OF_PURCHASE'],
  });
});
it.each(productProfileResources)(
  'allows a publisher-only reader to publish %s with confirmation',
  async (resource) => {
    api.mockImplementation(async (_endpoint, request) => {
      const result = response(request) as Record<string, unknown>;
      if (
        request.path.includes('/field-set') &&
        !request.path.includes('operation=publish')
      )
        result.fields = (result.fields as ReturnType<typeof fields>).map(
          (field) => ({ ...field, writable: false }),
        );
      return result as never;
    });
    openRevision(resource, SOURCE, false);
    const publish = await screen.findByRole('button', {
      name: 'Publish revision',
    });
    await waitFor(() => expect(publish).toBeEnabled());
    expect(
      screen.queryByRole('button', { name: 'Save draft changes' }),
    ).toBeDisabled();
    await userEvent.click(publish);
    expect(writes()).toHaveLength(0);
    await userEvent.click(
      within(screen.getByRole('dialog')).getByRole('button', {
        name: 'Publish revision',
      }),
    );
    await screen.findByText(/Revision published successfully/);
    expect(writes()[0]?.[1].body).toEqual({ expected_version: 4 });
    expect(writes()[0]?.[1].path).toContain('/' + SOURCE + '/publish');
  },
);
it('disables publication while draft values are unsaved and warns on navigation', async () => {
  openRevision('warranty-policies', SOURCE);
  const duration = await screen.findByRole('textbox', { name: 'Duration' });
  await userEvent.clear(duration);
  await userEvent.type(duration, '24');
  expect(
    screen.getByRole('button', { name: 'Publish revision' }),
  ).toBeDisabled();
  await userEvent.click(
    screen.getByRole('link', { name: 'Handling profiles' }),
  );
  expect(
    screen.getByRole('dialog', { name: 'Discard unsaved changes?' }),
  ).toBeVisible();
  expect(writes()).toHaveLength(0);
});
it.each(productProfileResources)(
  'blocks %s creation when parent-link write access is denied',
  async (resource) => {
    api.mockImplementation(async (_endpoint, request) => {
      const result = response(request) as Record<string, unknown>;
      if (request.path.includes('_revision/field-set'))
        result.fields = (result.fields as ReturnType<typeof fields>).map(
          (field) => ({
            ...field,
            writable:
              field.writable &&
              !['template_id', 'policy_id', 'profile_id'].includes(field.key),
          }),
        );
      return result as never;
    });
    openRevision(resource);
    const create = await screen.findByRole('button', {
      name: 'Create draft revision',
    });
    expect(create).toBeDisabled();
    expect(writes()).toHaveLength(0);
  },
);
it('respects publication field write denies', async () => {
  api.mockImplementation(async (_endpoint, request) => {
    const result = response(request) as Record<string, unknown>;
    if (request.path.includes('operation=publish'))
      result.fields = (result.fields as ReturnType<typeof fields>).map(
        (field) => ({
          ...field,
          writable: field.writable && field.key !== 'fragile',
        }),
      );
    return result as never;
  });
  openRevision('handling-profiles', SOURCE);
  const publish = await screen.findByRole('button', {
    name: 'Publish revision',
  });
  await screen.findByRole('textbox', { name: 'Instructions' });
  expect(publish).toBeDisabled();
  expect(writes()).toHaveLength(0);
});
it('does not confirm a publication with an unrelated receipt', async () => {
  let attempt = 0;
  api.mockImplementation(async (_endpoint, request) => {
    if (request.path.endsWith('/publish') && ++attempt === 1)
      return {
        ...revision('handling-profiles'),
        profile_id: SOURCE,
        published_at: '2026-10-25T10:00:00Z',
      } as never;
    return response(request) as never;
  });
  openRevision('handling-profiles', SOURCE);
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
  await screen.findByRole('button', { name: 'Retry same publication' });
  expect(
    screen.queryByText(/Revision published successfully/),
  ).not.toBeInTheDocument();
  await userEvent.click(
    screen.getByRole('button', { name: 'Retry same publication' }),
  );
  await screen.findByText(/Revision published successfully/);
  expect(writes()[0]?.[1].key).toBe(writes()[1]?.[1].key);
  expect(writes()[0]?.[1].body).toEqual(writes()[1]?.[1].body);
});
it('does not fetch protected identifier references while saving another inventory term', async () => {
  api.mockImplementation(async (_endpoint, request) => {
    const result = response(request);
    return request.path.endsWith('/revisions/' + SOURCE)
      ? ({
          ...(result as object),
          serial_tracking: true,
          identifier_profile_id: RECORD,
        } as never)
      : (result as never);
  });
  render(
    <ProductProfileRevision
      company={COMPANY}
      config={masterConfig('inventory-templates')!}
      parentId={RECORD}
      id={SOURCE}
      canManage
      access={{ ...access, identifiers: false }}
    />,
  );
  await screen.findByRole('textbox', { name: 'Identifier profile' });
  expect(
    api.mock.calls.some(([, request]) =>
      request.path.includes('/identifier-profiles'),
    ),
  ).toBe(false);
  await userEvent.selectOptions(
    screen.getByRole('combobox', { name: 'Negative stock policy' }),
    'WARN',
  );
  await userEvent.click(
    screen.getByRole('button', { name: 'Save draft changes' }),
  );
  await screen.findByText(/Draft revision updated successfully/);
  expect(writes()[0]?.[1].body).toEqual({
    expected_version: 4,
    negative_stock_policy: 'WARN',
  });
});
it('removes inaccessible directory filters and explains the adjustment', async () => {
  api.mockImplementation(async (_endpoint, request) => {
    const result = response(request) as Record<string, unknown>;
    if (request.path.includes('/field-set'))
      result.fields = (result.fields as ReturnType<typeof fields>).filter(
        (field) => field.key !== 'name',
      );
    return result as never;
  });
  render(
    <ProductProfileDirectory
      company={COMPANY}
      config={masterConfig('handling-profiles')!}
      canManage
      access={access}
      initialQuery="q=cold&sort=name&is_active=true"
    />,
  );
  await screen.findByText(
    /Unavailable search, filter or sort settings were removed/,
  );
  expect(window.location.search).not.toContain('q=');
  expect(window.location.search).not.toContain('sort=name');
  expect(window.location.search).toContain('is_active=true');
});
it('uses calendar-unit duration limits in warranty field hints', async () => {
  openRevision('warranty-policies');
  await screen.findByRole('textbox', { name: 'Duration' });
  expect(screen.getByText('Whole number from 1 to 1200.')).toBeVisible();
  await userEvent.selectOptions(
    screen.getByRole('combobox', { name: 'Duration unit' }),
    'YEARS',
  );
  expect(screen.getByText('Whole number from 1 to 100.')).toBeVisible();
});
it('renders published revisions as immutable', async () => {
  api.mockImplementation(async (_endpoint, request) => {
    const result = response(request);
    return (
      request.path.endsWith('/revisions/' + SOURCE)
        ? { ...(result as object), published_at: '2026-10-25T10:00:00Z' }
        : result
    ) as never;
  });
  openRevision('handling-profiles', SOURCE);
  expect(
    await screen.findByText(/This published revision is immutable/),
  ).toBeVisible();
  expect(screen.getByRole('textbox', { name: 'Instructions' })).toBeDisabled();
  expect(
    screen.queryByRole('button', { name: 'Publish revision' }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole('button', { name: 'Save draft changes' }),
  ).not.toBeInTheDocument();
});
it('blocks incomplete return-condition aggregates', async () => {
  api.mockImplementation(async (_endpoint, request) => {
    const result = response(request);
    return (
      request.path.includes('/conditions?')
        ? { items: [], page: { limit: 5, has_more: true, next_cursor: 'more' } }
        : result
    ) as never;
  });
  openRevision('return-policies', SOURCE);
  expect(
    await screen.findByText(
      /complete return condition set could not be verified/,
    ),
  ).toBeVisible();
  expect(
    screen.getByRole('button', { name: 'Publish revision' }),
  ).toBeDisabled();
  expect(writes()).toHaveLength(0);
});
it('retains hidden conditions while editing another return term', async () => {
  api.mockImplementation(async (_endpoint, request) => {
    const result = response(request) as Record<string, unknown>;
    if (request.path.includes('return_policy_condition/field-set'))
      result.fields = [];
    return result as never;
  });
  openRevision('return-policies', SOURCE);
  const window = await screen.findByRole('textbox', { name: 'Window days' });
  await userEvent.clear(window);
  await userEvent.type(window, '14');
  expect(
    screen.getByRole('button', { name: 'Publish revision' }),
  ).toBeDisabled();
  await userEvent.click(
    screen.getByRole('button', { name: 'Save draft changes' }),
  );
  await screen.findByText(/Draft revision updated successfully/);
  expect(writes()[0]?.[1].body).toEqual({
    expected_version: 4,
    window_days: 14,
  });
  expect(
    api.mock.calls.some(([, request]) => request.path.includes('/conditions?')),
  ).toBe(false);
});
it.each([401, 403, 422])(
  'shows %s errors and preserves an editable draft on validation failure',
  async (status) => {
    api.mockImplementation(async (_endpoint, request) => {
      if (request.method === 'POST')
        throw {
          status,
          message:
            status === 422
              ? 'Review the temperature'
              : 'Profile access unavailable',
          fields:
            status === 422
              ? { instructions: 'Review this instruction' }
              : undefined,
        };
      return response(request) as never;
    });
    openRevision('handling-profiles');
    await screen.findByRole('textbox', { name: 'Instructions' });
    await userEvent.click(
      screen.getByRole('button', { name: 'Create draft revision' }),
    );
    await screen.findByText(
      status === 422 ? 'Review the temperature' : 'Profile access unavailable',
    );
    if (status === 401)
      expect(screen.getByRole('link', { name: 'Sign in again' })).toBeVisible();
    if (status === 422)
      expect(screen.getByText('Review this instruction')).toHaveClass(
        'janso-error',
      );
    if (status === 422)
      expect(
        screen.getByRole('textbox', { name: 'Instructions' }),
      ).toBeEnabled();
    expect(writes()).toHaveLength(1);
  },
);
it('replays an unconfirmed save with the same exact body and key', async () => {
  let attempt = 0;
  api.mockImplementation(async (_endpoint, request) => {
    if (request.method === 'POST' && ++attempt === 1)
      throw { status: 503, message: 'Unavailable' };
    return response(request) as never;
  });
  openRevision('handling-profiles');
  const instructions = await screen.findByRole('textbox', {
    name: 'Instructions',
  });
  await userEvent.type(instructions, 'Keep dry.');
  await userEvent.click(
    screen.getByRole('button', { name: 'Create draft revision' }),
  );
  await screen.findByRole('button', { name: 'Retry same save' });
  expect(instructions).toBeDisabled();
  await userEvent.click(
    screen.getByRole('button', { name: 'Retry same save' }),
  );
  await screen.findByText(/Draft revision created successfully/);
  expect(writes()[0]?.[1].key).toBe(writes()[1]?.[1].key);
  expect(writes()[0]?.[1].body).toEqual(writes()[1]?.[1].body);
});
it('retains a conflicting edit until a confirmed reload', async () => {
  api.mockImplementation(async (_endpoint, request) => {
    if (request.method === 'PATCH')
      throw { status: 409, message: 'Revision version changed' };
    return response(request) as never;
  });
  openRevision('warranty-policies', SOURCE);
  const duration = await screen.findByRole('textbox', { name: 'Duration' });
  await userEvent.clear(duration);
  await userEvent.type(duration, '24');
  await userEvent.click(
    screen.getByRole('button', { name: 'Save draft changes' }),
  );
  await screen.findByText(/Revision version changed/);
  expect(duration).toHaveValue('24');
  await userEvent.click(
    screen.getByRole('button', { name: 'Reload and review' }),
  );
  expect(
    screen.getByRole('dialog', { name: 'Reload and discard this draft?' }),
  ).toBeVisible();
  await userEvent.click(
    within(screen.getByRole('dialog')).getByRole('button', { name: 'Reload' }),
  );
  await waitFor(() =>
    expect(screen.getByRole('textbox', { name: 'Duration' })).toHaveValue('12'),
  );
});
