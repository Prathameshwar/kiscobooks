/**
 * Builds a `DataTable` column set from the field-set endpoint (docs/identity-schema.md §6.2).
 *
 * **Clients render from the field set; they never hardcode a field list.** A tenant relabels a
 * field, reorders a group, turns one off or adds a custom field, and the table follows without a
 * deploy — that is the whole point of the endpoint, and a screen that lists its own columns quietly
 * stops matching the tenant's configuration (CLAUDE.md §6.15).
 *
 * Three boundaries this helper does *not* cross:
 *
 *  - **It is layout, not authorization.** A field the actor may not read never appears in the field
 *    set at all — `field_policy` removes it server-side, and it stays removed in exports and reports
 *    (docs/field-permissions.md §6). So nothing here is gated: what arrives is what may be shown.
 *    `is_visible: false` is a tenant's *layout* choice, so it becomes a column the reader can turn
 *    back on in the picker, not a column that is refused.
 *  - **Nothing is sortable unless the caller says so.** The allowlisted sort combinations live
 *    server-side (docs/api-conventions.md §2.4); a header that offers a sort the server will reject
 *    with a 422 is worse than no header. Custom fields are refused a sort even when named, because
 *    they live in a JSON bag with no index behind them.
 *  - **A cell type is presentation, never domain.** `currency_amount` renders as money because that
 *    is what it *is*; it does not follow that anything may be priced or posted from it. Domain logic
 *    never reads a custom field (CLAUDE.md §6.14).
 */
import { fieldValue, type CellType, type Column } from './table';

/**
 * The part of `FieldDescriptor` a table needs — structural, so the generated client's own type
 * satisfies it without this package importing `@janso/api-client`.
 *
 * `data_type` is `null` for native fields: the registry describes them by name, and their cell type
 * comes from the screen's `overrides`. Custom fields always carry one (docs/custom-fields.md §4).
 */
export type FieldDescriptorLike = {
  key: string;
  label?: string | null;
  data_type?: string | null;
  group?: string;
  order?: number;
  /** A tenant's layout choice. `false` means "off by default", never "denied". */
  is_visible?: boolean;
  /** `false` marks the field that identifies the row — it cannot be turned off. */
  hideable?: boolean;
  help_text?: string | null;
  /** `native` or `custom`. */
  source?: string;
  choices?: readonly { readonly [key: string]: unknown }[] | null;
};

/** The prefix the field set puts on a custom field's key. */
export const CUSTOM_FIELD_PREFIX = 'custom_field:';

/** Where a list item carries its custom-field values. */
export const CUSTOM_FIELDS_BAG = 'custom_fields';

/**
 * How each custom-field data type reads in a table cell.
 *
 * `integer` is a count, so it renders as a quantity at precision 0 rather than at the configured
 * quantity precision — "14.0000 invoices" is not a thing anyone wants to read. `dynamic_select`
 * holds a code resolved by a server-side source the client cannot call per row, so it renders as a
 * code rather than as a badge with a label it does not have.
 */
const CELL_TYPES: Readonly<Record<string, CellType>> = {
  text: 'text',
  long_text: 'text',
  integer: 'quantity',
  decimal: 'quantity',
  boolean: 'boolean',
  date: 'date',
  datetime: 'datetime',
  currency_amount: 'money',
  select: 'status',
  multi_select: 'chips',
  dynamic_select: 'code',
  auto_number: 'code',
};

export type FieldColumnOptions<Row> = {
  /**
   * The keys this list may be sorted by — the server's allowlist for this resource, stated by the
   * screen. Everything else gets an unpressable header.
   */
  sortable?: readonly string[];
  /** Only these groups, in field-set order. Omit for every group. */
  groups?: readonly string[];
  /**
   * Merged over the derived column, per field key. This is where a native field gets its type, a
   * `link` gets its `href`, and a `status` gets its tone — things the field set does not describe.
   */
  overrides?: Readonly<Record<string, Partial<Column<Row>>>>;
  /** The row field holding custom-field values. Defaults to `custom_fields`. */
  customFieldsKey?: string;
};

/** A choice list is `[{value, label, is_active}]`; anything else is ignored rather than trusted. */
function choiceLabels(field: FieldDescriptorLike): Map<string, string> {
  const labels = new Map<string, string>();
  for (const choice of field.choices ?? []) {
    const value = choice['value'];
    const label = choice['label'];
    if (typeof value === 'string' && typeof label === 'string') labels.set(value, label);
  }
  return labels;
}

/**
 * The heading, when the tenant has not named the field: `total_amount` → `Total amount`. One
 * sentence-case word group, not Title Case — headings read as prose in this design system.
 */
function humanize(key: string): string {
  const words = key.replace(CUSTOM_FIELD_PREFIX, '').replace(/[_.]+/g, ' ').trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export function columnsFromFieldSet<Row>(
  fields: readonly FieldDescriptorLike[],
  options: FieldColumnOptions<Row> = {},
): Column<Row>[] {
  const { sortable = [], groups, overrides = {}, customFieldsKey = CUSTOM_FIELDS_BAG } = options;
  const allowed = new Set(sortable);

  const wanted = groups
    ? fields.filter((field) => groups.includes(field.group ?? ''))
    : [...fields];

  // The endpoint already sorts by `(order, key)`; doing it again keeps the helper correct for a
  // caller that filtered or concatenated field sets before handing them over.
  wanted.sort((left, right) => (left.order ?? 0) - (right.order ?? 0) || left.key.localeCompare(right.key));

  return wanted.map((field) => {
    const custom = field.source === 'custom' || field.key.startsWith(CUSTOM_FIELD_PREFIX);
    const name = field.key.slice(field.key.startsWith(CUSTOM_FIELD_PREFIX) ? CUSTOM_FIELD_PREFIX.length : 0);
    const dataType = field.data_type ?? '';
    const type = CELL_TYPES[dataType] ?? 'text';
    const path = custom ? `${customFieldsKey}.${name}` : field.key;

    const column: Column<Row> = {
      key: field.key,
      header: field.label ?? humanize(field.key),
      type,
      // A custom field's value lives in the bag, not at the top level of the list item.
      ...(custom ? { value: (row: Row) => fieldValue(row, path) } : {}),
      // Hidden is a default the reader can overturn in the picker; locked is the row's identity.
      ...(field.is_visible === false ? { hidden: true } : {}),
      ...(field.hideable === false ? { locked: true } : {}),
      ...(field.help_text ? { description: field.help_text } : {}),
      // A JSON bag has no index behind it, so a custom field is never a sort key however the
      // screen names it — the server would answer 422 (docs/api-conventions.md §2.4).
      ...(allowed.has(field.key) && !custom ? { sortable: true } : {}),
      ...(dataType === 'long_text' ? { truncate: true } : {}),
      ...(dataType === 'integer' ? { precision: 0 } : {}),
      /*
       * The sibling currency travels *inside* the stored value (docs/custom-fields.md §4.1), so the
       * column reads the amount and points `currencyKey` at the code beside it. Both are paths.
       */
      ...(type === 'money' && custom
        ? {
            value: (row: Row) => fieldValue(row, `${path}.amount`),
            currencyKey: `${path}.currency`,
          }
        : {}),
      ...(type === 'status' || type === 'chips'
        ? { label: labelFrom(choiceLabels(field)) }
        : {}),
      ...overrides[field.key],
    };

    return column;
  });
}

/**
 * A choice's label, falling back to the stored code. A choice that has been deactivated keeps its
 * label — a value already stored on a record must still render (CLAUDE.md §6.11, rule 4.12).
 */
function labelFrom(labels: Map<string, string>): (value: string) => string {
  return (value: string) => labels.get(value) ?? value;
}
