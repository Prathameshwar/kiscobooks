import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { AttributeMasterDirectory } from '../app/components/AttributeMasterDirectory';
import { AttributeMasterEditor } from '../app/components/AttributeMasterEditor';
import { AttributeMasterDetail } from '../app/components/AttributeMasterDetail';
import { AttributeSetRevision } from '../app/components/AttributeSetRevision';
import { AttributeReference } from '../app/components/AttributeMasterCommon';
import { masterConfig } from '../app/lib/catalog-masters';
import { serviceCall } from '../app/lib/service-call';
import { attributeResources } from '../app/lib/attribute-resources';
import {
  COMPANY,
  RECORD,
  SOURCE,
  FRESH,
  access,
  fields,
  response,
  definition,
  revisionRow,
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
      ['POST', 'PATCH', 'PUT'].includes(request.method ?? 'GET'),
    );
beforeEach(() => {
  vi.clearAllMocks();
  window.history.replaceState(null, '', '/');
  api.mockImplementation(
    async (_endpoint, request) => response(request) as never,
  );
});
async function fill() {
  await userEvent.type(
    await screen.findByRole('textbox', { name: 'Code' }),
    'NEW',
  );
  await userEvent.type(
    screen.getByRole('textbox', { name: 'Name' }),
    'New attribute',
  );
}
async function choose(label: string, option: string) {
  await userEvent.click(await screen.findByRole('combobox', { name: label }));
  await userEvent.click(
    await screen.findByRole('option', { name: new RegExp(option) }),
  );
}
it.each(attributeResources)(
  'opens %s directory and preserves callers',
  async (resource) => {
    render(
      <AttributeMasterDirectory
        company={COMPANY}
        config={masterConfig(resource)!}
        access={access}
        canManage={false}
        initialQuery="returnTo=%2Fmasters%2Fitems"
      />,
    );
    expect(await screen.findByRole('table')).toBeVisible();
    await screen.findAllByRole('link', { name: /Test attribute|Colour/ });
    expect(screen.getByText('Read-only access.')).toBeVisible();
    expect(
      screen.queryByRole('link', { name: /New attribute/ }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: 'Back to previous page' }),
    ).toHaveAttribute('href', '/masters/items');
  },
);
it.each(attributeResources)('creates %s using metadata', async (resource) => {
  render(
    <AttributeMasterEditor
      company={COMPANY}
      config={masterConfig(resource)!}
      definitionId={SOURCE}
      access={access}
    />,
  );
  await fill();
  if (resource === 'attribute-options')
    await userEvent.type(
      screen.getByRole('textbox', { name: 'Text value' }),
      'Blue',
    );
  await userEvent.click(
    screen.getByRole('button', {
      name: 'Create ' + masterConfig(resource)!.singular,
    }),
  );
  expect(await screen.findByText(/created successfully/)).toBeVisible();
  expect(writes()).toHaveLength(1);
  expect(writes()[0]![1].body).toMatchObject({
    code: 'NEW',
    name: 'New attribute',
  });
  expect(
    screen.getByRole('link', {
      name: 'View ' + masterConfig(resource)!.singular,
    }),
  ).toHaveAttribute('href', expect.stringContaining(FRESH));
});
it.each(attributeResources)(
  'validates %s before sending and focuses the error',
  async (resource) => {
    render(
      <AttributeMasterEditor
        company={COMPANY}
        config={masterConfig(resource)!}
        definitionId={SOURCE}
        access={access}
      />,
    );
    const code = await screen.findByRole('textbox', { name: 'Code' });
    await userEvent.type(code, 'lower');
    await userEvent.click(
      screen.getByRole('button', {
        name: 'Create ' + masterConfig(resource)!.singular,
      }),
    );
    expect(
      await screen.findByText(/uppercase code with up to 30/),
    ).toBeVisible();
    expect(code).toHaveFocus();
    expect(writes()).toHaveLength(0);
  },
);
it.each([
  ['INTEGER', 'Whole number value', '9007199254740993', 'value_integer'],
  ['DECIMAL', 'Decimal value', '0.0001', 'value_decimal'],
  ['DATE', 'Date value', '2026-10-25', 'value_date'],
])('authors exact %s options', async (type, label, value, key) => {
  api.mockImplementation(async (_endpoint, request) =>
    request.path.endsWith('/attribute-definitions/' + SOURCE)
      ? (definition(type) as never)
      : (response(request) as never),
  );
  render(
    <AttributeMasterEditor
      company={COMPANY}
      config={masterConfig('attribute-options')!}
      definitionId={SOURCE}
      access={access}
    />,
  );
  await fill();
  const input = screen.getByLabelText(label, { exact: false });
  await userEvent.type(input, value);
  await userEvent.click(
    screen.getByRole('button', { name: 'Create attribute option' }),
  );
  await screen.findByText(/created successfully/);
  expect(writes()[0]![1].body).toMatchObject({
    [key]: value,
    value_type: type,
  });
});
it('preserves false as an explicit boolean option value', async () => {
  api.mockImplementation(async (_endpoint, request) =>
    request.path.endsWith('/attribute-definitions/' + SOURCE)
      ? (definition('BOOLEAN') as never)
      : (response(request) as never),
  );
  render(
    <AttributeMasterEditor
      company={COMPANY}
      config={masterConfig('attribute-options')!}
      definitionId={SOURCE}
      access={access}
    />,
  );
  await fill();
  await userEvent.selectOptions(
    screen.getByRole('combobox', { name: 'Boolean value' }),
    'false',
  );
  await userEvent.click(
    screen.getByRole('button', { name: 'Create attribute option' }),
  );
  await screen.findByText(/created successfully/);
  expect(writes()[0]![1].body).toMatchObject({ value_boolean: false });
});
it('requires a compatible measurement unit and filters the selector', async () => {
  api.mockImplementation(async (_endpoint, request) =>
    request.path.endsWith('/attribute-definitions/' + SOURCE)
      ? ({ ...definition('DECIMAL'), measurement_dimension: 'MASS' } as never)
      : request.path.includes('/units?')
        ? ({
            items: [
              {
                id: RECORD,
                name: 'Kilogram',
                code: 'KG',
                dimension: 'MASS',
                is_active: true,
              },
            ],
            page,
          } as never)
        : (response(request) as never),
  );
  render(
    <AttributeMasterEditor
      company={COMPANY}
      config={masterConfig('attribute-options')!}
      definitionId={SOURCE}
      access={access}
    />,
  );
  await fill();
  await userEvent.type(
    screen.getByRole('textbox', { name: 'Decimal value' }),
    '1.0000',
  );
  await userEvent.click(
    screen.getByRole('button', { name: 'Create attribute option' }),
  );
  expect(
    await screen.findByText(/Choose an available measurement unit/),
  ).toBeVisible();
  await choose('Measurement unit', 'Kilogram');
  expect(
    api.mock.calls.some(([, request]) =>
      request.path.includes('dimension=MASS'),
    ),
  ).toBe(true);
  await userEvent.click(
    screen.getByRole('button', { name: 'Create attribute option' }),
  );
  await screen.findByText(/created successfully/);
  expect(writes()[0]![1].body).toMatchObject({ unit_id: RECORD });
});
it('blocks creation without definition or unit read authority', async () => {
  render(
    <AttributeMasterEditor
      company={COMPANY}
      config={masterConfig('attribute-options')!}
      definitionId={SOURCE}
      access={{ ...access, 'attribute-definitions': false }}
    />,
  );
  expect(
    await screen.findByRole('button', { name: 'Create attribute option' }),
  ).toBeDisabled();
  expect(
    api.mock.calls.some(([, request]) =>
      request.path.endsWith('/attribute-definitions/' + SOURCE),
    ),
  ).toBe(false);
});
it('retains changed-field editing without reading an option value', async () => {
  api.mockImplementation(async (_endpoint, request) =>
    request.path.includes('/field-set') &&
    request.path.includes('attribute_option')
      ? ({
          company_id: COMPANY,
          entity_type: 'catalog.attribute_option',
          fields: fields('attribute_option', 'update').filter(
            (field) =>
              !field.key.startsWith('value_') && field.key !== 'definition_id',
          ),
        } as never)
      : (response(request) as never),
  );
  render(
    <AttributeMasterEditor
      company={COMPANY}
      config={masterConfig('attribute-options')!}
      id={RECORD}
      access={{ ...access, 'attribute-definitions': false }}
    />,
  );
  const input = await screen.findByRole('textbox', { name: 'Name' });
  await userEvent.clear(input);
  await userEvent.type(input, 'Renamed');
  await userEvent.click(screen.getByRole('button', { name: 'Save changes' }));
  await screen.findByText(/updated successfully/);
  expect(writes()[0]![1].body).toEqual({
    expected_version: 4,
    name: 'Renamed',
  });
});
it('freezes an unconfirmed save and reuses its body and idempotency key', async () => {
  let failed = false;
  api.mockImplementation(async (_endpoint, request) => {
    if (request.method === 'POST' && !failed) {
      failed = true;
      throw { status: 503, message: 'Unavailable' };
    }
    return response(request) as never;
  });
  render(
    <AttributeMasterEditor
      company={COMPANY}
      config={masterConfig('attribute-sets')!}
      access={access}
    />,
  );
  await fill();
  await userEvent.click(
    screen.getByRole('button', { name: 'Create attribute set' }),
  );
  expect(await screen.findByText(/save could not be confirmed/)).toBeVisible();
  expect(screen.getByRole('textbox', { name: 'Name' })).toBeDisabled();
  await userEvent.click(
    screen.getByRole('button', { name: 'Retry same save' }),
  );
  await screen.findByText(/created successfully/);
  expect(writes()[0]![1].body).toEqual(writes()[1]![1].body);
  expect(writes()[0]![1].key).toBe(writes()[1]![1].key);
});
it('keeps a rejected draft editable and reports server field errors', async () => {
  let failed = false;
  api.mockImplementation(async (_endpoint, request) => {
    if (request.method === 'POST' && !failed) {
      failed = true;
      throw {
        status: 422,
        message: 'Check the name',
        fields: { name: 'This name is invalid.' },
      };
    }
    return response(request) as never;
  });
  render(
    <AttributeMasterEditor
      company={COMPANY}
      config={masterConfig('attribute-sets')!}
      access={access}
    />,
  );
  await fill();
  await userEvent.click(
    screen.getByRole('button', { name: 'Create attribute set' }),
  );
  expect(await screen.findByText('This name is invalid.')).toBeVisible();
  expect(screen.getByRole('textbox', { name: 'Name' })).toBeEnabled();
  await userEvent.type(screen.getByRole('textbox', { name: 'Name' }), ' fixed');
  await userEvent.click(
    screen.getByRole('button', { name: 'Create attribute set' }),
  );
  await screen.findByText(/created successfully/);
});
it('requires confirmation before discarding a conflicting draft', async () => {
  api.mockImplementation(async (_endpoint, request) => {
    if (request.method === 'PATCH')
      throw { status: 409, message: 'Stale version' };
    return response(request) as never;
  });
  render(
    <AttributeMasterEditor
      company={COMPANY}
      config={masterConfig('attribute-sets')!}
      id={RECORD}
      access={access}
    />,
  );
  const name = await screen.findByRole('textbox', { name: 'Name' });
  await userEvent.type(name, ' changed');
  await userEvent.click(screen.getByRole('button', { name: 'Save changes' }));
  await userEvent.click(
    await screen.findByRole('button', { name: 'Reload and review' }),
  );
  expect(screen.getByRole('dialog')).toBeVisible();
  await userEvent.click(
    within(screen.getByRole('dialog')).getByRole('button', {
      name: 'Reload and review',
    }),
  );
  await waitFor(() =>
    expect(screen.getByRole('textbox', { name: 'Name' })).toHaveValue(
      'Test attribute',
    ),
  );
});
it.each(attributeResources)(
  'shows %s lifecycle actions and confirms retirement',
  async (resource) => {
    render(
      <AttributeMasterDetail
        company={COMPANY}
        config={masterConfig(resource)!}
        id={RECORD}
        access={access}
        canManage
      />,
    );
    await userEvent.click(
      await screen.findByRole('button', {
        name: masterConfig(resource)!.singular + ' actions',
      }),
    );
    await userEvent.click(screen.getByRole('menuitem', { name: 'Deactivate' }));
    await userEvent.click(
      within(screen.getByRole('dialog')).getByRole('button', {
        name: 'Deactivate',
      }),
    );
    await screen.findByText(/deactivated successfully/);
    expect(writes()[0]![1].body).toEqual({ expected_version: 4 });
  },
);
it('links definitions to options and templates to revision history', async () => {
  const view = render(
    <AttributeMasterDetail
      company={COMPANY}
      config={masterConfig('attribute-definitions')!}
      id={RECORD}
      access={access}
      canManage={false}
    />,
  );
  expect(
    await screen.findByRole('link', {
      name: 'View options for this definition',
    }),
  ).toHaveAttribute('href', expect.stringContaining('definition_id=' + RECORD));
  view.unmount();
  render(
    <AttributeMasterDetail
      company={COMPANY}
      config={masterConfig('attribute-sets')!}
      id={RECORD}
      access={access}
      canManage
    />,
  );
  expect(
    await screen.findByRole('link', { name: 'New draft revision' }),
  ).toHaveAttribute('href', expect.stringContaining('/revisions/new'));
  expect(await screen.findByRole('link', { name: 'Revision 1' })).toBeVisible();
});
it('authors a template draft and prevents add/remove controls from submitting', async () => {
  render(
    <AttributeSetRevision
      company={COMPANY}
      setId={RECORD}
      access={access}
      canManage
    />,
  );
  await userEvent.click(
    await screen.findByRole('button', { name: 'Add attribute definition' }),
  );
  expect(writes()).toHaveLength(0);
  await choose('Attribute 1: definition', 'Colour');
  await userEvent.click(
    screen.getByRole('checkbox', { name: 'Attribute 1: required' }),
  );
  await userEvent.click(
    screen.getByRole('button', { name: 'Save draft revision' }),
  );
  expect(
    await screen.findByText(/Draft revision saved successfully/),
  ).toBeVisible();
  expect(writes()[0]![1].body).toEqual({
    members: [
      {
        definition_id: SOURCE,
        position: 0,
        is_required: true,
        allow_variant_axis: false,
      },
    ],
  });
  expect(
    screen.getByRole('link', { name: 'View draft revision' }),
  ).toHaveAttribute('href', expect.stringContaining(FRESH));
});
it('publishes only a saved draft and freezes its requirements', async () => {
  render(
    <AttributeSetRevision
      company={COMPANY}
      setId={RECORD}
      id={FRESH}
      access={access}
      canManage
    />,
  );
  await waitFor(() =>
    expect(
      screen.getByRole('checkbox', { name: 'Attribute 1: allow variant axis' }),
    ).toBeEnabled(),
  );
  await userEvent.click(
    screen.getByRole('button', { name: 'Publish revision' }),
  );
  expect(writes()).toHaveLength(0);
  await userEvent.click(
    within(screen.getByRole('dialog')).getByRole('button', {
      name: 'Publish revision',
    }),
  );
  expect(await screen.findByText(/published successfully/)).toBeVisible();
  expect(writes()[0]![1].body).toEqual({ expected_version: 4 });
  expect(
    await screen.findByText(/Published revisions are immutable/),
  ).toBeVisible();
  expect(
    screen.queryByRole('button', { name: 'Save draft revision' }),
  ).not.toBeInTheDocument();
});
it('requires saving changed membership before publication', async () => {
  render(
    <AttributeSetRevision
      company={COMPANY}
      setId={RECORD}
      id={FRESH}
      access={access}
      canManage
    />,
  );
  await waitFor(() =>
    expect(
      screen.getByRole('checkbox', { name: 'Attribute 1: required' }),
    ).toBeEnabled(),
  );
  await userEvent.click(
    screen.getByRole('checkbox', { name: 'Attribute 1: required' }),
  );
  expect(
    screen.getByRole('button', { name: 'Publish revision' }),
  ).toBeDisabled();
  await userEvent.click(
    screen.getByRole('button', { name: 'Save draft revision' }),
  );
  await screen.findByText(/Draft revision saved successfully/);
  expect(writes()[0]![1].body).toMatchObject({
    expected_version: 4,
    members: [
      {
        definition_id: SOURCE,
        position: 0,
        is_required: false,
        allow_variant_axis: true,
      },
    ],
  });
});
it.each(['read', 'write', 'partial-page'])(
  'blocks incomplete %s membership replacement',
  async (mode) => {
    api.mockImplementation(async (_endpoint, request) => {
      if (request.path.includes('attribute_set_member/field-set'))
        return {
          company_id: COMPANY,
          entity_type: 'catalog.attribute_set_member',
          fields: fields(
            'attribute_set_member',
            request.path.includes('publish') ? 'publish' : 'update',
          ).flatMap((field) =>
            field.key === 'is_required'
              ? mode === 'read'
                ? []
                : [{ ...field, writable: false }]
              : [field],
          ),
        } as never;
      if (mode === 'partial-page' && request.path.includes('/members?'))
        return { items: [], page: { ...page, has_more: true } } as never;
      return response(request) as never;
    });
    render(
      <AttributeSetRevision
        company={COMPANY}
        setId={RECORD}
        id={FRESH}
        access={access}
        canManage
      />,
    );
    await waitFor(() =>
      expect(
        screen.queryByText(/Loading template revision/),
      ).not.toBeInTheDocument(),
    );
    expect(
      screen.queryByRole('button', { name: 'Save draft revision' }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Publish revision' }),
    ).not.toBeInTheDocument();
    expect(writes()).toHaveLength(0);
  },
);
it('does not give managers publication without publish permission', async () => {
  render(
    <AttributeSetRevision
      company={COMPANY}
      setId={RECORD}
      id={FRESH}
      access={{ ...access, publish: false }}
      canManage
    />,
  );
  expect(
    await screen.findByRole('button', { name: 'Save draft revision' }),
  ).toBeEnabled();
  expect(
    screen.queryByRole('button', { name: 'Publish revision' }),
  ).not.toBeInTheDocument();
});
it('shows reference load errors without replacing the saved identity', async () => {
  api.mockRejectedValue({ status: 403, message: 'Reference denied' });
  render(
    <AttributeReference
      company={COMPANY}
      value={SOURCE}
      label="Definition"
      onChange={vi.fn()}
    />,
  );
  expect(await screen.findByText('Reference denied')).toBeVisible();
  expect(screen.getByRole('combobox', { name: 'Definition' })).toBeVisible();
});
it('accepts a canonical numeric no-op without entering uncertain recovery', async () => {
  api.mockImplementation(async (_endpoint, request) =>
    request.path.endsWith('/attribute-options/' + RECORD)
      ? ({
          id: RECORD,
          company_id: COMPANY,
          name: 'Numeric',
          code: 'NUM',
          value_type: 'DECIMAL',
          value_decimal: '1.0000',
          is_active: true,
          row_version: 4,
        } as never)
      : request.method === 'PATCH'
        ? ({ ...(response(request) as object), row_version: 4 } as never)
        : (response(request) as never),
  );
  // GET and PATCH share a route; distinguish the receipt explicitly.
  const prior = api.getMockImplementation()!;
  api.mockImplementation(async (endpoint, request, subject) =>
    request.method === 'PATCH'
      ? ({ id: RECORD, company_id: COMPANY, row_version: 4 } as never)
      : prior(endpoint, request, subject),
  );
  render(
    <AttributeMasterEditor
      company={COMPANY}
      config={masterConfig('attribute-options')!}
      id={RECORD}
      access={access}
    />,
  );
  const value = await screen.findByRole('textbox', { name: 'Decimal value' });
  await userEvent.clear(value);
  await userEvent.type(value, '1');
  await userEvent.click(screen.getByRole('button', { name: 'Save changes' }));
  expect(await screen.findByText(/updated successfully/)).toBeVisible();
  expect(
    screen.queryByRole('button', { name: 'Retry same save' }),
  ).not.toBeInTheDocument();
});
it('recovers an unconfirmed membership write with identical body and key', async () => {
  let failed = false;
  api.mockImplementation(async (_endpoint, request) => {
    if (request.method === 'PUT' && !failed) {
      failed = true;
      throw { status: 503, message: 'Unavailable' };
    }
    return response(request) as never;
  });
  render(
    <AttributeSetRevision
      company={COMPANY}
      setId={RECORD}
      id={FRESH}
      access={access}
      canManage
    />,
  );
  await waitFor(() =>
    expect(
      screen.getByRole('checkbox', { name: 'Attribute 1: allow variant axis' }),
    ).toBeEnabled(),
  );
  await userEvent.click(
    screen.getByRole('checkbox', { name: 'Attribute 1: required' }),
  );
  await userEvent.click(
    screen.getByRole('button', { name: 'Save draft revision' }),
  );
  await userEvent.click(
    await screen.findByRole('button', { name: 'Retry same save' }),
  );
  expect(
    await screen.findByText(/Draft revision saved successfully/),
  ).toBeVisible();
  expect(writes()[0]![1].body).toEqual(writes()[1]![1].body);
  expect(writes()[0]![1].key).toBe(writes()[1]![1].key);
});
it('clears an optional measurement dimension when the definition changes', async () => {
  render(
    <AttributeMasterEditor
      company={COMPANY}
      config={masterConfig('attribute-definitions')!}
      access={access}
    />,
  );
  await fill();
  await userEvent.selectOptions(
    screen.getByRole('combobox', { name: 'Value type' }),
    'DECIMAL',
  );
  const dimension = screen.getByRole('combobox', {
    name: 'Measurement dimension',
  });
  await userEvent.selectOptions(dimension, 'MASS');
  await userEvent.selectOptions(dimension, '');
  expect(dimension).toHaveValue('');
  await userEvent.click(
    screen.getByRole('button', { name: 'Create attribute definition' }),
  );
  await screen.findByText(/created successfully/);
  expect(writes()[0]![1].body).toMatchObject({
    measurement_dimension: null,
    value_type: 'DECIMAL',
  });
});
it('allows correcting duplicate values while retaining a new master draft', async () => {
  let first = true;
  api.mockImplementation(async (_endpoint, request) => {
    if (request.method === 'POST' && first) {
      first = false;
      throw { status: 409, message: 'Code already exists' };
    }
    return response(request) as never;
  });
  render(
    <AttributeMasterEditor
      company={COMPANY}
      config={masterConfig('attribute-definitions')!}
      access={access}
    />,
  );
  await fill();
  await userEvent.click(
    screen.getByRole('button', { name: 'Create attribute definition' }),
  );
  expect(
    await screen.findByText(/Correct duplicate values and save again/),
  ).toBeVisible();
  expect(screen.getByRole('textbox', { name: 'Name' })).toHaveValue(
    'New attribute',
  );
  await userEvent.type(screen.getByRole('textbox', { name: 'Code' }), '2');
  await userEvent.click(
    screen.getByRole('button', { name: 'Create attribute definition' }),
  );
  await screen.findByText(/created successfully/);
  expect(writes()[1]![1].body).toMatchObject({
    code: 'NEW2',
    name: 'New attribute',
  });
  expect(writes()[0]![1].key).not.toBe(writes()[1]![1].key);
});
it('resolves readable definition and measurement labels in option details', async () => {
  api.mockImplementation(async (_endpoint, request) =>
    request.path.endsWith('/units/' + FRESH)
      ? ({
          id: FRESH,
          company_id: COMPANY,
          name: 'Kilogram',
          code: 'KG',
        } as never)
      : request.path.endsWith('/attribute-options/' + RECORD)
        ? ({
            id: RECORD,
            company_id: COMPANY,
            definition_id: SOURCE,
            value_type: 'DECIMAL',
            value_decimal: '1.0000',
            unit_id: FRESH,
            row_version: 4,
            is_active: true,
          } as never)
        : (response(request) as never),
  );
  render(
    <AttributeMasterDetail
      company={COMPANY}
      config={masterConfig('attribute-options')!}
      id={RECORD}
      access={access}
      canManage={false}
    />,
  );
  expect(await screen.findByText('Kilogram')).toBeVisible();
  expect(await screen.findByRole('link', { name: 'Colour' })).toHaveAttribute(
    'href',
    expect.stringContaining('/attribute-definitions/' + SOURCE),
  );
});
it.each(attributeResources)(
  'names each %s action menu using readable fields',
  async (resource) => {
    render(
      <AttributeMasterDirectory
        company={COMPANY}
        config={masterConfig(resource)!}
        canManage={false}
        access={access}
      />,
    );
    const label =
      resource === 'attribute-definitions' ? 'Colour' : 'Test attribute';
    expect(
      await screen.findByRole('button', { name: 'Actions for ' + label }),
    ).toBeVisible();
  },
);
