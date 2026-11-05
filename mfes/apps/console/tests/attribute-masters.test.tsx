import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { AttributeMasters } from '../app/components/AttributeMasters';
import { productFieldRequest } from '../app/lib/product-fields';
vi.mock('../app/lib/product-fields', () => ({ productFieldRequest: vi.fn() }));
vi.mock('@janso/ui', async (original) => ({
  ...(await original<typeof import('@janso/ui')>()),
  SearchSelect: ({
    label,
    onChange,
    disabled,
    loadOptions,
  }: {
    label: string;
    onChange: (id: string | null) => void;
    disabled: boolean;
    loadOptions: (args: unknown) => Promise<{ items: { id: string }[] }>;
  }) => (
    <>
      <button
        type="button"
        disabled={disabled}
        onClick={() =>
          void loadOptions({
            q: 'Size',
            cursor: 'next',
            signal: new AbortController().signal,
          }).then((page) => onChange(page.items[0]?.id ?? null))
        }
      >
        {label}
      </button>
      <button type="button" disabled={disabled} onClick={() => onChange(null)}>
        Clear {label}
      </button>
    </>
  ),
}));
const api = vi.mocked(productFieldRequest);
let definition: {
  id: string;
  code: string;
  name: string;
  value_type: string;
  measurement_dimension: string | null;
  is_variant_capable: boolean;
  is_active: boolean;
  row_version: number;
};
let protectedValue = false;
const fields = (keys: string[]) => ({
  fields: keys.map((key, order) => ({
    key,
    label: key,
    order,
    source: 'native',
    visible: true,
    writable: !(protectedValue && key === 'value_integer'),
    required: ['code', 'name'].includes(key),
  })),
});
beforeEach(() => {
  definition = {
    id: 'size',
    code: 'SIZE',
    name: 'Size',
    value_type: 'INTEGER',
    measurement_dimension: null,
    is_variant_capable: true,
    is_active: true,
    row_version: 1,
  };
  protectedValue = false;
  api.mockReset();
  api.mockImplementation(async (_s, method, path, body) => {
    if (path.includes('/attribute-definitions?'))
      return { items: [definition], page: { next_cursor: null } };
    if (path.includes('/attribute-options?'))
      return { items: [{ id: 'large', name: 'Large', code: 'L' }], page: { next_cursor: null } };
    if (path.includes('field-set'))
      return fields(
        path.includes('attribute_definition')
          ? [
              'code',
              'name',
              'is_active',
              'row_version',
              'value_type',
              'measurement_dimension',
              'is_variant_capable',
            ]
          : [
              'code',
              'name',
              'is_active',
              'row_version',
              'definition_id',
              'value_type',
              'value_integer',
              'unit_id',
            ],
      );
    if (method === 'GET' && path.endsWith('/size')) return definition;
    if (method === 'GET' && path.endsWith('/large'))
      return {
        id: 'large',
        code: 'L',
        name: 'Large',
        is_active: true,
        row_version: 2,
        definition_id: 'size',
        value_type: 'INTEGER',
        value_integer: '9223372036854775807',
      };
    if (method !== 'GET') return { id: 'saved', ...(body as object) };
    throw new Error('Unexpected ' + path);
  });
});
async function select() {
  render(<AttributeMasters company="company" />);
  fireEvent.click(screen.getByRole('button', { name: 'Find attribute definition' }));
  await screen.findByRole('button', { name: 'Edit Size' });
}
it('creates a definition using provided metadata and exact declared types', async () => {
  render(<AttributeMasters company="company" />);
  fireEvent.click(screen.getByRole('button', { name: 'New attribute definition' }));
  fireEvent.change(await screen.findByLabelText('code'), { target: { value: 'WEIGHT' } });
  fireEvent.change(screen.getByLabelText('name'), { target: { value: 'Weight' } });
  fireEvent.change(screen.getByLabelText('value_type'), { target: { value: 'DECIMAL' } });
  fireEvent.change(screen.getByLabelText('measurement_dimension'), { target: { value: 'MASS' } });
  fireEvent.change(screen.getByLabelText('is_variant_capable'), { target: { value: 'true' } });
  fireEvent.submit(screen.getByRole('form'));
  await waitFor(() =>
    expect(screen.getByRole('status', { name: 'Master result' })).toHaveTextContent('saved'),
  );
  expect(api.mock.calls.find((c) => c[1] === 'POST')?.[3]).toEqual({
    code: 'WEIGHT',
    name: 'Weight',
    value_type: 'DECIMAL',
    measurement_dimension: 'MASS',
    is_variant_capable: true,
  });
});
it('edits an existing definition and keeps the version on retry', async () => {
  await select();
  fireEvent.click(screen.getByRole('button', { name: 'Edit Size' }));
  const save = await screen.findByRole('button', { name: 'Save attribute definition' });
  expect(save.closest('.janso-card__footer')).not.toBeNull();
  expect(save.closest('form')?.querySelector('.janso-card__body')).not.toBeNull();
  fireEvent.change(await screen.findByLabelText('name'), { target: { value: 'Clothing size' } });
  const fallback = api.getMockImplementation()!;
  let first = true;
  api.mockImplementation(async (...args) => {
    if (args[1] === 'PATCH' && first) {
      first = false;
      throw new Error('Retry');
    }
    return fallback(...args);
  });
  fireEvent.submit(screen.getByRole('form'));
  expect(await screen.findByRole('status', { name: 'Master result' })).toHaveTextContent('Retry');
  fireEvent.submit(screen.getByRole('form'));
  await waitFor(() =>
    expect(screen.getByRole('status', { name: 'Master result' })).toHaveTextContent('saved'),
  );
  const writes = api.mock.calls.filter((c) => c[1] === 'PATCH');
  expect(writes[0][4]).toBe(writes[1][4]);
  expect(writes[1][3]).toMatchObject({ expected_version: 1, name: 'Clothing size' });
});
it('creates an exact integer option and rejects empty or inexact values', async () => {
  await select();
  fireEvent.click(screen.getByRole('button', { name: 'New Size option' }));
  fireEvent.change(await screen.findByLabelText('code'), { target: { value: 'L' } });
  fireEvent.change(screen.getByLabelText('name'), { target: { value: 'Large' } });
  fireEvent.submit(screen.getByRole('form'));
  expect(await screen.findByRole('status', { name: 'Master result' })).toHaveTextContent(
    'enter one value',
  );
  fireEvent.change(screen.getByLabelText('Option value'), { target: { value: '1.5' } });
  fireEvent.submit(screen.getByRole('form'));
  await waitFor(() =>
    expect(screen.getByRole('status', { name: 'Master result' })).toHaveTextContent('whole number'),
  );
  fireEvent.change(screen.getByLabelText('Option value'), {
    target: { value: '9223372036854775807' },
  });
  fireEvent.submit(screen.getByRole('form'));
  await waitFor(() =>
    expect(screen.getByRole('status', { name: 'Master result' })).toHaveTextContent('saved'),
  );
  expect(api.mock.calls.find((c) => c[1] === 'POST')?.[3]).toMatchObject({
    definition_id: 'size',
    value_type: 'INTEGER',
    value_integer: '9223372036854775807',
  });
});
it('edits an option without resending immutable definition and type fields', async () => {
  await select();
  fireEvent.click(screen.getByRole('button', { name: 'Find Size option' }));
  fireEvent.change(await screen.findByLabelText('name'), { target: { value: 'Extra large' } });
  fireEvent.submit(screen.getByRole('form'));
  await waitFor(() =>
    expect(screen.getByRole('status', { name: 'Master result' })).toHaveTextContent('saved'),
  );
  const body = api.mock.calls.find((c) => c[1] === 'PATCH')?.[3] as Record<string, unknown>;
  expect(body.expected_version).toBe(2);
  expect(body).not.toHaveProperty('definition_id');
  expect(body).not.toHaveProperty('value_type');
});
it.each([true, false])('uses a single lifecycle command, active=%s', async (active) => {
  definition.is_active = active;
  await select();
  fireEvent.click(screen.getByRole('button', { name: 'Edit Size' }));
  const button = await screen.findByRole('button', {
    name: (active ? 'Deactivate' : 'Activate') + ' attribute definition',
  });
  await userEvent.click(button);
  await waitFor(() =>
    expect(screen.getByRole('status', { name: 'Master result' })).toHaveTextContent('saved'),
  );
  const writes = api.mock.calls.filter((c) => c[1] !== 'GET');
  expect(writes).toHaveLength(1);
  expect(writes[0][2]).toContain(active ? '/deactivate' : '/activate');
  expect(writes[0][3]).toEqual({ expected_version: 1 });
});
it('cancels without submitting and clears the selected definition', async () => {
  await select();
  fireEvent.click(screen.getByRole('button', { name: 'Edit Size' }));
  await userEvent.click(await screen.findByRole('button', { name: 'Cancel master edit' }));
  expect(screen.queryByRole('form')).not.toBeInTheDocument();
  expect(api.mock.calls.every((c) => c[1] === 'GET')).toBe(true);
  fireEvent.click(screen.getByRole('button', { name: 'Clear Find attribute definition' }));
  expect(screen.queryByRole('button', { name: 'Edit Size' })).not.toBeInTheDocument();
});
it('locks a protected option value and reports failed master loads', async () => {
  protectedValue = true;
  await select();
  fireEvent.click(screen.getByRole('button', { name: 'Find Size option' }));
  expect(await screen.findByLabelText('Option value')).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'Cancel master edit' }));
  api.mockRejectedValueOnce(new Error('Access denied'));
  fireEvent.click(screen.getByRole('button', { name: 'Edit Size' }));
  expect(await screen.findByRole('status', { name: 'Master result' })).toHaveTextContent(
    'Access denied',
  );
});

it('creates a measured option through a dimension-filtered unit lookup', async () => {
  definition.measurement_dimension = 'COUNT';
  const fallback = api.getMockImplementation()!;
  api.mockImplementation(async (...args) => {
    if (args[2].includes('/units?'))
      return { items: [{ id: 'piece', name: 'Piece' }], page: { next_cursor: null } };
    return fallback(...args);
  });
  await select();
  fireEvent.click(screen.getByRole('button', { name: 'New Size option' }));
  fireEvent.change(await screen.findByLabelText('code'), { target: { value: 'PACK' } });
  fireEvent.change(screen.getByLabelText('name'), { target: { value: 'Pack count' } });
  fireEvent.change(screen.getByLabelText('Option value'), { target: { value: '3' } });
  fireEvent.change(screen.getByRole('combobox', { name: 'Option value unit' }), {
    target: { value: 'Pi' },
  });
  fireEvent.click(await screen.findByRole('option', { name: 'Piece' }));
  fireEvent.submit(screen.getByRole('form'));
  await waitFor(() =>
    expect(screen.getByRole('status', { name: 'Master result' })).toHaveTextContent('saved'),
  );
  expect(api.mock.calls.find((c) => c[2].includes('/units?'))?.[2]).toContain('dimension=COUNT');
  expect(api.mock.calls.find((c) => c[1] === 'POST')?.[3]).toMatchObject({
    value_integer: '3',
    unit_id: 'piece',
  });
});

it('renames an option without requiring its read-protected typed value', async () => {
  const fallback = api.getMockImplementation()!;
  api.mockImplementation(async (...args) => {
    const result = await fallback(...args);
    if (args[2].includes('catalog.attribute_option/field-set'))
      return fields(['code', 'name', 'is_active', 'row_version', 'definition_id', 'value_type']);
    if (args[1] === 'GET' && args[2].endsWith('/large')) {
      const row = { ...(result as Record<string, unknown>) };
      delete row.value_integer;
      return row;
    }
    return result;
  });
  await select();
  fireEvent.click(screen.getByRole('button', { name: 'Find Size option' }));
  fireEvent.change(await screen.findByLabelText('name'), { target: { value: 'Large label' } });
  fireEvent.submit(screen.getByRole('form'));
  await waitFor(() =>
    expect(screen.getByRole('status', { name: 'Master result' })).toHaveTextContent('saved'),
  );
  expect(api.mock.calls.find((call) => call[1] === 'PATCH')?.[3]).toEqual({
    expected_version: 2,
    name: 'Large label',
  });
});

it("displays a measured option's saved unit label", async () => {
  definition.measurement_dimension = 'COUNT';
  const fallback = api.getMockImplementation()!;
  api.mockImplementation(async (...args) => {
    if (args[1] === 'GET' && args[2].endsWith('/units/piece'))
      return { id: 'piece', name: 'Piece' };
    const result = await fallback(...args);
    if (args[1] === 'GET' && args[2].endsWith('/large'))
      return { ...(result as object), unit_id: 'piece' };
    return result;
  });
  await select();
  fireEvent.click(screen.getByRole('button', { name: 'Find Size option' }));
  expect(await screen.findByRole('combobox', { name: 'Option value unit' })).toHaveValue('Piece');
});

it('disables unit selection when unit metadata denies writes', async () => {
  definition.measurement_dimension = 'COUNT';
  const fallback = api.getMockImplementation()!;
  api.mockImplementation(async (...args) => {
    if (args[2].includes('catalog.attribute_option/field-set'))
      return {
        fields: fields(['code', 'name', 'value_integer', 'unit_id']).fields.map((f) => ({
          ...f,
          writable: f.key !== 'unit_id',
        })),
      };
    return fallback(...args);
  });
  await select();
  fireEvent.click(screen.getByRole('button', { name: 'New Size option' }));
  expect(await screen.findByRole('combobox', { name: 'Option value unit' })).toBeDisabled();
});

it('hides a measurement unit when field metadata hides it', async () => {
  definition.measurement_dimension = 'COUNT';
  const fallback = api.getMockImplementation()!;
  api.mockImplementation(async (...args) => {
    if (args[2].includes('catalog.attribute_option/field-set'))
      return {
        fields: fields(['code', 'name', 'value_integer', 'unit_id']).fields.map((f) => ({
          ...f,
          visible: f.key !== 'unit_id',
        })),
      };
    return fallback(...args);
  });
  await select();
  fireEvent.click(screen.getByRole('button', { name: 'New Size option' }));
  await screen.findByLabelText('Option value');
  expect(screen.queryByRole('combobox', { name: 'Option value unit' })).not.toBeInTheDocument();
});

it('retains a readable unit identity if its optional label lookup is denied', async () => {
  definition.measurement_dimension = 'COUNT';
  const fallback = api.getMockImplementation()!;
  api.mockImplementation(async (...args) => {
    if (args[1] === 'GET' && args[2].endsWith('/units/piece'))
      throw new Error('Unit name is protected');
    const result = await fallback(...args);
    if (args[1] === 'GET' && args[2].endsWith('/large'))
      return { ...(result as object), unit_id: 'piece' };
    return result;
  });
  await select();
  fireEvent.click(screen.getByRole('button', { name: 'Find Size option' }));
  expect(await screen.findByRole('combobox', { name: 'Option value unit' })).toHaveValue('piece');
  fireEvent.change(screen.getByLabelText('name'), { target: { value: 'Renamed' } });
  fireEvent.submit(screen.getByRole('form'));
  await waitFor(() =>
    expect(screen.getByRole('status', { name: 'Master result' })).toHaveTextContent('saved'),
  );
  expect(api.mock.calls.find((call) => call[1] === 'PATCH')?.[3]).toEqual({
    expected_version: 2,
    name: 'Renamed',
  });
});
