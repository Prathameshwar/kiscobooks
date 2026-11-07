import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { expect, it, vi } from 'vitest';
import {
  AttributeValueInput,
  attributeValue,
  type NativeAttributeField,
  type NativeAttributeValue,
} from '../src/components/AttributeValueInput';
vi.mock('../src/components/SearchSelect', () => ({
  SearchSelect: ({
    label,
    value,
    onChange,
    disabled,
    options,
    selected,
  }: {
    label: string;
    value: string | null;
    onChange: (id: string | null) => void;
    disabled: boolean;
    options?: { id: string; label: string; disabled?: boolean }[];
    selected?: { label: string };
  }) => (
    <div>
      <span>{selected?.label}</span>
      <select
        aria-label={label}
        disabled={disabled}
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value || null)}
      >
        <option value="">Clear</option>
        {(options ?? [{ id: 'choice', label: 'Chosen' }]).map((o) => (
          <option disabled={o.disabled} key={o.id} value={o.id}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  ),
}));
const field: NativeAttributeField = {
  definition_id: 'definition',
  label: 'Material',
  value_type: 'TEXT',
  measurement_dimension: null,
  is_axis: false,
  is_required: false,
  writable: true,
  allowed_options: [],
};
function Form({
  patch = {},
  initial = null,
  optionMode = false,
}: {
  patch?: Partial<NativeAttributeField>;
  initial?: NativeAttributeValue | null;
  optionMode?: boolean;
}) {
  const [value, set] = useState(initial);
  return (
    <>
      <AttributeValueInput
        field={{ ...field, value: initial, ...patch }}
        value={value}
        onChange={set}
        loadOptions={optionMode ? async () => ({ items: [], nextCursor: null }) : undefined}
      />
      <output data-testid="value">{JSON.stringify(value)}</output>
    </>
  );
}
it('uses the shared accessible field group for attribute values', () => {
  render(<Form patch={{ is_required: true }} />);
  const group = screen.getByRole('group', { name: 'Material (required before activation)' });
  expect(group).toHaveClass('janso-fieldgroup');
  expect(screen.getByLabelText('Material', { selector: 'input, select' }).closest('.janso-fieldgroup__fields')).not.toBeNull();
});
it.each([
  ['TEXT', 'cotton', 'value_text'],
  ['INTEGER', '9223372036854775807', 'value_integer'],
  ['DECIMAL', '123.0001', 'value_decimal'],
  ['DATE', '2026-09-15', 'value_date'],
])('edits and clears exact %s values', (type, value, key) => {
  render(<Form patch={{ value_type: type, is_required: true }} />);
  fireEvent.change(screen.getByLabelText('Material', { selector: 'input, select' }), { target: { value } });
  expect(screen.getByTestId('value')).toHaveTextContent(
    JSON.stringify({ definition_id: 'definition', value_type: type, [key]: value, unit_id: null }),
  );
  fireEvent.change(screen.getByLabelText('Material', { selector: 'input, select' }), { target: { value: '' } });
  expect(screen.getByTestId('value')).toHaveTextContent('null');
});
it('preserves false and distinguishes unset boolean', () => {
  render(<Form patch={{ value_type: 'BOOLEAN' }} />);
  fireEvent.change(screen.getByLabelText('Material', { selector: 'input, select' }), { target: { value: 'false' } });
  expect(screen.getByTestId('value')).toHaveTextContent('"value_boolean":false');
  fireEvent.change(screen.getByLabelText('Material', { selector: 'input, select' }), { target: { value: 'true' } });
  expect(screen.getByTestId('value')).toHaveTextContent('"value_boolean":true');
  fireEvent.change(screen.getByLabelText('Material', { selector: 'input, select' }), { target: { value: '' } });
  expect(screen.getByTestId('value')).toHaveTextContent('null');
});
it('supports measured values and retains the unit when the number changes', () => {
  render(<Form patch={{ value_type: 'INTEGER', measurement_dimension: 'COUNT' }} />);
  fireEvent.change(screen.getByLabelText('Material unit'), { target: { value: 'choice' } });
  fireEvent.change(screen.getByLabelText('Material', { selector: 'input, select' }), { target: { value: '3' } });
  expect(screen.getByTestId('value')).toHaveTextContent('"unit_id":"choice"');
});
it('uses family choices for variant axes, labels saved values and disables retired options', () => {
  render(
    <Form
      patch={{
        is_axis: true,
        allowed_options: [
          { id: 'choice', label: 'Blue', is_active: true },
          { id: 'old', label: 'Retired', is_active: false },
        ],
      }}
      initial={{ definition_id: 'definition', value_type: 'TEXT', option_id: 'choice' }}
    />,
  );
  expect(screen.getByRole('option', { name: 'Retired' })).toBeDisabled();
  expect(screen.getByText('Blue', { selector: 'span' })).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Material', { selector: 'input, select' }), { target: { value: '' } });
  expect(screen.getByTestId('value')).toHaveTextContent('null');
  fireEvent.change(screen.getByLabelText('Material', { selector: 'input, select' }), { target: { value: 'choice' } });
  expect(screen.getByTestId('value')).toHaveTextContent('"option_id":"choice"');
});
it('switches between free values and lookup options with an explicit clear', () => {
  render(<Form optionMode />);
  fireEvent.change(screen.getByLabelText('Material', { selector: 'input, select' }), { target: { value: 'old' } });
  fireEvent.change(screen.getByLabelText('Material entry'), { target: { value: 'option' } });
  expect(screen.getByTestId('value')).toHaveTextContent('null');
  fireEvent.change(screen.getByLabelText('Material', { selector: 'input, select' }), { target: { value: 'choice' } });
  expect(screen.getByTestId('value')).toHaveTextContent('"option_id":"choice"');
  fireEvent.change(screen.getByLabelText('Material entry'), { target: { value: 'scalar' } });
  expect(screen.getByTestId('value')).toHaveTextContent('null');
});
it('locks protected values and displays resolved historical labels', () => {
  render(
    <Form
      patch={{ writable: false, option_label: 'Historic' }}
      initial={{ definition_id: 'definition', value_type: 'TEXT', option_id: 'choice' }}
      optionMode
    />,
  );
  expect(screen.getByLabelText('Material', { selector: 'input, select' })).toBeDisabled();
  expect(screen.getByText('Historic')).toBeInTheDocument();
});
it('renders a saved measured unit label and can clear it', () => {
  render(
    <Form
      patch={{ value_type: 'DECIMAL', measurement_dimension: 'MASS', unit_label: 'Kilogram' }}
      initial={{
        definition_id: 'definition',
        value_type: 'DECIMAL',
        value_decimal: '2',
        unit_id: 'choice',
      }}
    />,
  );
  expect(screen.getByText('Kilogram')).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Material unit'), { target: { value: '' } });
  expect(screen.getByTestId('value')).toHaveTextContent('"unit_id":null');
});
it.each(['1.1', '01', '1e3', '9223372036854775808', '-9223372036854775809'])(
  'rejects invalid or inexact integer %s',
  (value) => {
    expect(() =>
      attributeValue({ definition_id: 'd', value_type: 'INTEGER', value_integer: value }),
    ).toThrow();
  },
);
it.each(['1.00001', '1000000000000000', '1e2'])('rejects out of contract decimal %s', (value) => {
  expect(() =>
    attributeValue({ definition_id: 'd', value_type: 'DECIMAL', value_decimal: value }),
  ).toThrow();
});
it('accepts signed bounds, decimals, false and options', () => {
  for (const value of [
    { value_type: 'INTEGER', value_integer: '-9223372036854775808' },
    { value_type: 'INTEGER', value_integer: '9223372036854775807' },
    { value_type: 'DECIMAL', value_decimal: '-999999999999999.9999' },
    { value_type: 'BOOLEAN', value_boolean: false },
    { value_type: 'TEXT', option_id: 'o' },
  ])
    expect(attributeValue({ definition_id: 'd', ...value })).toEqual({
      definition_id: 'd',
      ...value,
    });
});
it('rejects empty, mixed and wrong typed selections', () => {
  for (const value of [
    { value_type: 'TEXT', unit_id: 'unit' },
    { value_type: 'TEXT', value_text: '' },
    { value_type: 'TEXT', value_boolean: false },
    { value_type: 'TEXT', option_id: 'o', value_text: 'x' },
    { value_type: 'TEXT', option_id: 'o', unit_id: 'u' },
  ])
    expect(() => attributeValue({ definition_id: 'd', ...value })).toThrow();
});

it('uses the newly selected option label instead of the saved label', () => {
  const change = vi.fn();
  render(
    <AttributeValueInput
      field={{
        ...field,
        is_axis: true,
        value: { definition_id: 'definition', value_type: 'TEXT', option_id: 'blue' },
        option_label: 'Blue',
        allowed_options: [
          { id: 'blue', label: 'Blue', is_active: true },
          { id: 'red', label: 'Red', is_active: true },
        ],
      }}
      value={{ definition_id: 'definition', value_type: 'TEXT', option_id: 'red' }}
      onChange={change}
    />,
  );
  expect(screen.getByText('Red', { selector: 'span' })).toBeInTheDocument();
  expect(screen.queryByText('Blue', { selector: 'span' })).not.toBeInTheDocument();
});

it("hides the unit control when the caller's metadata hides it", () => {
  render(
    <Form
      patch={{ value_type: 'INTEGER', measurement_dimension: 'COUNT', unit_visible: false }}
      initial={{
        definition_id: 'definition',
        value_type: 'INTEGER',
        value_integer: '3',
        unit_id: 'choice',
      }}
    />,
  );
  expect(screen.queryByLabelText('Material unit')).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Material', { selector: 'input, select' }), { target: { value: '4' } });
  expect(screen.getByTestId('value')).toHaveTextContent('"unit_id":"choice"');
});
