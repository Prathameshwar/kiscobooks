/**
 * `columnsFromFieldSet` — the field-set endpoint's layout turned into table columns
 * (docs/identity-schema.md §6.2).
 *
 * The properties worth locking down are the boundaries: what arrives may be shown (the endpoint has
 * already applied field policy, so nothing here re-gates), a tenant's `is_visible: false` is a
 * default rather than a denial, and no header offers a sort the server has not allowlisted — least
 * of all a custom field, which has no index behind it.
 */
import { describe, expect, it } from 'vitest';

import {
  CUSTOM_FIELDS_BAG,
  CUSTOM_FIELD_PREFIX,
  columnsFromFieldSet,
  type FieldDescriptorLike,
} from '../src/lib/field-columns';
import { fieldValue, rawValue } from '../src/lib/table';

type Item = {
  id: string;
  code: string;
  name: string;
  custom_fields?: Record<string, unknown>;
};

const NATIVE: readonly FieldDescriptorLike[] = [
  { key: 'code', label: 'Code', group: 'identity', order: 10, hideable: false },
  { key: 'name', label: 'Name', group: 'identity', order: 20, hideable: true },
  { key: 'notes', label: 'Notes', group: 'detail', order: 30, hideable: true, is_visible: false },
];

const custom = (
  key: string,
  data_type: string,
  extra: Partial<FieldDescriptorLike> = {},
): FieldDescriptorLike => ({
  key: `${CUSTOM_FIELD_PREFIX}${key}`,
  source: 'custom',
  data_type,
  group: 'custom',
  order: 100,
  hideable: true,
  ...extra,
});

describe('fieldValue', () => {
  const row = { code: 'A', 'odd.key': 'kept', custom_fields: { cap: { currency: 'USD' } } };

  it('reads a plain key exactly as written', () => {
    expect(fieldValue(row, 'code')).toBe('A');
    // Every field key is snake_case, and a custom one is prefixed `custom_field:` — so a dot is a
    // path separator here and never part of a name. A key that did contain one reads as a path.
    expect(fieldValue(row, 'odd.key')).toBeUndefined();
  });

  it('walks a dotted key as a path', () => {
    expect(fieldValue(row, 'custom_fields.cap.currency')).toBe('USD');
  });

  it('gives up quietly on a path that runs out', () => {
    expect(fieldValue(row, 'custom_fields.missing.currency')).toBeUndefined();
    expect(fieldValue(row, 'code.length.0')).toBeUndefined();
    expect(fieldValue(null, 'code')).toBeUndefined();
    expect(fieldValue('scalar', 'code')).toBeUndefined();
  });
});

describe('columnsFromFieldSet — layout', () => {
  it('keeps the field key as the column identity', () => {
    const columns = columnsFromFieldSet<Item>(NATIVE);

    // The key is the picker's identity, the React key, and the field-set key — one value, not three.
    expect(columns.map((column) => column.key)).toEqual(['code', 'name', 'notes']);
  });

  it('orders by the tenant’s display order, with the key breaking a tie', () => {
    const columns = columnsFromFieldSet<Item>([
      { key: 'zebra', order: 5 },
      { key: 'beta', order: 1 },
      { key: 'alpha', order: 1 },
    ]);

    expect(columns.map((column) => column.key)).toEqual(['alpha', 'beta', 'zebra']);
  });

  it('takes the tenant’s label as the heading', () => {
    const [code] = columnsFromFieldSet<Item>([{ key: 'code', label: 'Item code' }]);

    expect(code?.header).toBe('Item code');
  });

  it('reads an unnamed field as prose rather than as a column key', () => {
    const [amount] = columnsFromFieldSet<Item>([{ key: 'total_amount' }]);

    expect(amount?.header).toBe('Total amount');
  });

  it('treats a tenant’s hidden field as a default, not a denial', () => {
    const notes = columnsFromFieldSet<Item>(NATIVE).find((column) => column.key === 'notes');

    // The reader can turn it back on in the picker. A field they may not *read* never arrives here
    // at all — field policy removes it server-side, and it stays removed in exports.
    expect(notes?.hidden).toBe(true);
    expect(notes?.locked).toBeUndefined();
  });

  it('locks the field that identifies the row', () => {
    const columns = columnsFromFieldSet<Item>(NATIVE);

    expect(columns.find((column) => column.key === 'code')?.locked).toBe(true);
    expect(columns.find((column) => column.key === 'name')?.locked).toBeUndefined();
  });

  it('carries the help text as the heading’s explanation', () => {
    const [field] = columnsFromFieldSet<Item>([
      { key: 'margin', help_text: 'Sale price less landed cost' },
    ]);

    expect(field?.description).toBe('Sale price less landed cost');
  });

  it('narrows to the groups a screen asks for', () => {
    const columns = columnsFromFieldSet<Item>(NATIVE, { groups: ['identity'] });

    expect(columns.map((column) => column.key)).toEqual(['code', 'name']);
  });

  it('lets the screen state what the field set cannot describe', () => {
    const columns = columnsFromFieldSet<Item>(NATIVE, {
      overrides: { code: { type: 'link', href: () => '/items/1' }, name: { truncate: true } },
    });

    // A native field has no `data_type`, so its cell type is the screen's to state.
    expect(columns[0]?.type).toBe('link');
    expect(columns[0]?.href?.({ id: '1', code: 'A', name: 'B' })).toBe('/items/1');
    expect(columns[1]?.truncate).toBe(true);
  });
});

describe('columnsFromFieldSet — sorting', () => {
  it('offers no sort at all until the screen names the server’s allowlist', () => {
    const columns = columnsFromFieldSet<Item>(NATIVE);

    // A header that offers a sort the server rejects with 422 is worse than an unpressable one.
    expect(columns.every((column) => column.sortable === undefined)).toBe(true);
  });

  it('offers a sort on exactly the keys named', () => {
    const columns = columnsFromFieldSet<Item>(NATIVE, { sortable: ['code'] });

    expect(columns.find((column) => column.key === 'code')?.sortable).toBe(true);
    expect(columns.find((column) => column.key === 'name')?.sortable).toBeUndefined();
  });

  it('refuses a custom field a sort even when it is named', () => {
    const key = `${CUSTOM_FIELD_PREFIX}warehouse`;
    const [column] = columnsFromFieldSet<Item>([custom('warehouse', 'text')], { sortable: [key] });

    // It lives in a JSON bag with no index behind it; the server has nothing to order by.
    expect(column?.sortable).toBeUndefined();
  });
});

describe('columnsFromFieldSet — cell types', () => {
  const typeOf = (dataType: string) => columnsFromFieldSet<Item>([custom('f', dataType)])[0];

  it('maps each custom data type to how it reads', () => {
    expect(typeOf('text')?.type).toBe('text');
    expect(typeOf('long_text')?.type).toBe('text');
    expect(typeOf('decimal')?.type).toBe('quantity');
    expect(typeOf('boolean')?.type).toBe('boolean');
    expect(typeOf('date')?.type).toBe('date');
    expect(typeOf('datetime')?.type).toBe('datetime');
    expect(typeOf('currency_amount')?.type).toBe('money');
    expect(typeOf('select')?.type).toBe('status');
    expect(typeOf('multi_select')?.type).toBe('chips');
    expect(typeOf('auto_number')?.type).toBe('code');
  });

  it('renders a count as a whole number, not to the quantity precision', () => {
    const column = typeOf('integer');

    // "14.0000 invoices" is not a thing anyone wants to read.
    expect(column?.type).toBe('quantity');
    expect(column?.precision).toBe(0);
  });

  it('clips a long text field rather than letting one field set the row height', () => {
    expect(typeOf('long_text')?.truncate).toBe(true);
  });

  it('falls back to text for a type this client does not know', () => {
    // A genuinely new data type needs a renderer in both clients (docs/custom-fields.md §3); until
    // it has one, showing the stored value is better than showing nothing.
    expect(typeOf('geo_point')?.type).toBe('text');
    expect(columnsFromFieldSet<Item>([{ key: 'name' }])[0]?.type).toBe('text');
  });

  it('reads a dynamic select as a code, because its label needs a server-side resolver', () => {
    expect(typeOf('dynamic_select')?.type).toBe('code');
  });
});

describe('columnsFromFieldSet — custom field values', () => {
  const row: Item = {
    id: '1',
    code: 'A',
    name: 'Bolt',
    custom_fields: {
      warehouse: 'WH-2',
      cap: { amount: '1500.0000', currency: 'USD' },
    },
  };

  it('reads a custom field out of the bag, not off the top level', () => {
    const [column] = columnsFromFieldSet<Item>([custom('warehouse', 'text')]);

    expect(rawValue(column!, row)).toBe('WH-2');
  });

  it('reads the bag the screen names when a list item carries a different one', () => {
    const [column] = columnsFromFieldSet<Item>([custom('warehouse', 'text')], {
      customFieldsKey: 'extras',
    });

    expect(rawValue(column!, { ...row, extras: { warehouse: 'WH-9' } } as Item)).toBe('WH-9');
    expect(CUSTOM_FIELDS_BAG).toBe('custom_fields');
  });

  it('keeps a currency amount with its own currency, which travels inside the value', () => {
    const [column] = columnsFromFieldSet<Item>([custom('cap', 'currency_amount')]);

    // A decimal string, never a number — and the sibling code is a path into the same stored object,
    // so an amount in USD cannot be rendered with the company's own symbol (CLAUDE.md §6.1).
    expect(rawValue(column!, row)).toBe('1500.0000');
    expect(column?.currencyKey).toBe('custom_fields.cap.currency');
    expect(fieldValue(row, column!.currencyKey!)).toBe('USD');
  });

  it('survives a row with no bag at all', () => {
    const [column] = columnsFromFieldSet<Item>([custom('warehouse', 'text')]);

    expect(rawValue(column!, { id: '1', code: 'A', name: 'Bolt' })).toBeUndefined();
  });

  it('names a custom field from its own label, prefix stripped when there is none', () => {
    const [labelled] = columnsFromFieldSet<Item>([
      custom('warehouse', 'text', { label: 'Warehouse' }),
    ]);
    const [unlabelled] = columnsFromFieldSet<Item>([custom('lead_time', 'text')]);

    expect(labelled?.header).toBe('Warehouse');
    expect(unlabelled?.header).toBe('Lead time');
  });

  it('treats a key carrying the prefix as custom even without the source flag', () => {
    const [column] = columnsFromFieldSet<Item>([
      { key: `${CUSTOM_FIELD_PREFIX}warehouse`, data_type: 'text' },
    ]);

    expect(rawValue(column!, row)).toBe('WH-2');
  });
});

describe('columnsFromFieldSet — choices', () => {
  const withChoices = custom('grade', 'select', {
    choices: [
      { value: 'a', label: 'Grade A' },
      { value: 'b', label: 'Grade B', is_active: false },
    ],
  });

  it('labels a stored code from the choices the field set inlines', () => {
    const [column] = columnsFromFieldSet<Item>([withChoices]);

    expect(column?.label?.('a', {} as Item)).toBe('Grade A');
  });

  it('still labels a deactivated choice, because a stored value must render', () => {
    const [column] = columnsFromFieldSet<Item>([withChoices]);

    // Choices deactivate rather than delete (rule 4.12) — the row that holds `b` predates the change.
    expect(column?.label?.('b', {} as Item)).toBe('Grade B');
  });

  it('falls back to the raw code for a value no choice describes', () => {
    const [column] = columnsFromFieldSet<Item>([withChoices]);

    expect(column?.label?.('c', {} as Item)).toBe('c');
  });

  it('ignores a malformed choice rather than trusting it', () => {
    const [column] = columnsFromFieldSet<Item>([
      custom('grade', 'select', { choices: [{ value: 1, label: 'One' }, { label: 'No value' }] }),
    ]);

    expect(column?.label?.('1', {} as Item)).toBe('1');
  });
});
