import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { AttributeMasterDirectory } from '../app/components/AttributeMasterDirectory';
import { AttributeMasterEditor } from '../app/components/AttributeMasterEditor';
import { masterConfig } from '../app/lib/catalog-masters';
import { serviceCall } from '../app/lib/service-call';
import {
  COMPANY,
  RECORD,
  SOURCE,
  FRESH,
  access,
  fields,
  response,
  definition,
  page,
} from './attribute-master-fixtures';
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
  window.history.replaceState(null, '', '/');
});
it('offers and saves a typed-value edit when names and codes are read-only', async () => {
  api.mockImplementation(async (_endpoint, request) =>
    request.path.includes('attribute_option/field-set')
      ? ({
          company_id: COMPANY,
          entity_type: 'catalog.attribute_option',
          fields: fields(
            'attribute_option',
            request.path.includes('update') ? 'update' : 'create',
          ).map((field) => ({
            ...field,
            writable: field.key === 'value_text',
          })),
        } as never)
      : (response(request) as never),
  );
  const view = render(
    <AttributeMasterDirectory
      company={COMPANY}
      config={masterConfig('attribute-options')!}
      canManage
      access={access}
    />,
  );
  await userEvent.click(
    await screen.findByRole('button', { name: 'Actions for Test attribute' }),
  );
  expect(screen.getByRole('menuitem', { name: 'Edit details' })).toBeVisible();
  view.unmount();
  render(
    <AttributeMasterEditor
      company={COMPANY}
      config={masterConfig('attribute-options')!}
      id={RECORD}
      access={access}
    />,
  );
  const input = await screen.findByRole('textbox', { name: 'Text value' });
  await userEvent.clear(input);
  await userEvent.type(input, 'Red');
  await userEvent.click(screen.getByRole('button', { name: 'Save changes' }));
  await screen.findByText(/updated successfully/);
  expect(writes()[0]![1].body).toEqual({
    expected_version: 4,
    value_text: 'Red',
  });
});
it('supports a measured-unit-only edit while preserving the exact scalar', async () => {
  const original = {
    id: RECORD,
    company_id: COMPANY,
    name: 'Weight',
    code: 'WEIGHT',
    value_type: 'DECIMAL',
    definition_id: SOURCE,
    value_decimal: '1.0000',
    unit_id: SOURCE,
    is_active: true,
    row_version: 4,
  };
  api.mockImplementation(async (_endpoint, request) => {
    if (request.path.includes('attribute_option/field-set'))
      return {
        company_id: COMPANY,
        entity_type: 'catalog.attribute_option',
        fields: fields('attribute_option', 'update').map((field) => ({
          ...field,
          writable: field.key === 'unit_id',
        })),
      } as never;
    if (request.path.endsWith('/attribute-options/' + RECORD))
      return {
        ...original,
        ...(request.body as object),
        row_version: request.method === 'PATCH' ? 5 : 4,
      } as never;
    if (request.path.endsWith('/attribute-definitions/' + SOURCE))
      return {
        ...definition('DECIMAL'),
        measurement_dimension: 'MASS',
      } as never;
    if (request.path.includes('/units')) {
      const unit = {
        id: request.path.includes('?') ? FRESH : request.path.split('/').at(-1),
        company_id: COMPANY,
        name: 'Kilogram',
        code: 'KG',
        dimension: 'MASS',
        is_active: true,
      };
      return request.path.includes('?')
        ? ({ items: [unit], page } as never)
        : (unit as never);
    }
    return response(request) as never;
  });
  render(
    <AttributeMasterEditor
      company={COMPANY}
      config={masterConfig('attribute-options')!}
      id={RECORD}
      access={access}
    />,
  );
  await waitFor(() => {
    expect(
      screen.getByRole('combobox', { name: 'Measurement unit' }),
    ).toHaveValue('Kilogram');
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeEnabled();
  });
  await userEvent.click(
    screen.getByRole('button', { name: 'Toggle Measurement unit options' }),
  );
  await userEvent.click(
    await screen.findByRole('option', { name: /Kilogram/ }),
  );
  await userEvent.click(screen.getByRole('button', { name: 'Save changes' }));
  await screen.findByText(/updated successfully/);
  expect(writes()[0]![1].body).toEqual({ expected_version: 4, unit_id: FRESH });
});
