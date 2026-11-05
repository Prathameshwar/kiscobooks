/** Exact, presentation-only condition evaluation. The API remains authoritative. */
export type CustomDefinition = {
  key: string; data_type: string; is_active: boolean; is_searchable?: boolean;
  is_immutable_after_create: boolean; default_value?: unknown;
  validation: { required: boolean; min?: string | null; max?: string | null;
    min_length?: number; max_length: number; decimal_places?: number; regex?: string | null; regex_message?: string | null;
    unique_within?: string; case_sensitive?: boolean };
  choices: { value: string; label: string; is_active: boolean }[];
  option_source_key?: string | null; depends_on_key?: string | null;
  visibility?: Record<string, unknown> | null;
  sequence_config?: { prefix: string; padding: number; start: number; reset: string } | null;
};
export type CustomField = {
  key: string; source: string; label: string; visible: boolean; required: boolean; writable: boolean;
  help_text?: string | null; placeholder?: string | null; custom?: CustomDefinition | null;
};

function decimal(value: unknown): bigint {
  if ((typeof value !== 'string' && typeof value !== 'number') ||
      !/^[+-]?\d+(?:\.\d{1,4})?$/.test(String(value))) throw new Error('Invalid decimal');
  const text = String(value), negative = text.startsWith('-');
  const [whole, fraction = ''] = text.replace(/^[+-]/, '').split('.');
  return (negative ? -1n : 1n) * (BigInt(whole ?? '0') * 10000n + BigInt(fraction.padEnd(4, '0')));
}

export function customCondition(tree: Record<string, unknown> | null | undefined,
  values: Record<string, unknown>, numeric: ReadonlySet<string> = new Set()): boolean {
  if (!tree) return true;
  if (tree.op) {
    const rules = tree.rules as Record<string, unknown>[];
    return tree.op === 'and' ? rules.every(rule => customCondition(rule, values, numeric))
      : tree.op === 'or' ? rules.some(rule => customCondition(rule, values, numeric)) : tree.op === 'not' && rules.length === 1 ? !customCondition(rules[0]!, values, numeric) : false;
  }
  const key = String(tree.field), actual = values[key] ?? null, expected = tree.value;
  const empty = actual === undefined || actual === null || actual === '' || (Array.isArray(actual) && !actual.length);
  if (tree.cmp === 'empty') return empty;
  if (tree.cmp === 'not_empty') return !empty;
  const normalize = (value: unknown): unknown => {
    if (value == null) return value;
    if (!key.startsWith('cf_') && typeof actual === 'string' && /^\d{4}-\d\d-\d\dT/.test(actual) && typeof value === 'string') {
      const parsed = Date.parse(value);
      if (!Number.isFinite(parsed) || !/(?:Z|[+-]\d\d:\d\d)$/.test(value)) throw new Error('Invalid timestamp');
      const fraction = /\.(\d{1,6})/.exec(value)?.[1] ?? '';
      return BigInt(parsed) * 1000n + BigInt(fraction.padEnd(6, '0').slice(3));
    }
    if (numeric.has(key) || typeof actual === 'number') return decimal(value);
    if (!key.startsWith('cf_') && key.endsWith('_id') && typeof actual === 'string' && /^[0-9a-f-]{36}$/i.test(actual)) {
      if (typeof value !== 'string' || !/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(value)) throw new Error('Invalid UUID');
      return value.toLowerCase();
    }
    return value;
  };
  try {
    const left = normalize(actual);
    const equal = (value: unknown) => {
      const right = normalize(value);
      return Array.isArray(left) && Array.isArray(right) ? JSON.stringify(left) === JSON.stringify(right) : left === right;
    };
    if (tree.cmp === 'eq') return equal(expected);
    if (tree.cmp === 'ne') return !equal(expected);
    if (tree.cmp === 'in' || tree.cmp === 'not_in') {
      const found = Array.isArray(expected) && expected.some(equal);
      return tree.cmp === 'in' ? found : !found;
    }
    if (tree.cmp === 'matches') {
      if (typeof actual !== 'string' || typeof expected !== 'string' || expected.length > 256 || /[()|+*?]/.test(expected)) return false;
      const expression = expected.replace(/\\d/g, '\\p{Nd}').replace(/\\w/g, '[\\p{L}\\p{N}_]');
      return new RegExp(`^(?:${expression})$`, 'u').test(actual);
    }
    const right = normalize(expected);
    if ((typeof left !== 'bigint' && typeof left !== 'string') || typeof left !== typeof right) return false;
    const comparison = typeof left === 'bigint' && typeof right === 'bigint' ? (left < right ? -1 : left > right ? 1 : 0) : (String(left) < String(right) ? -1 : String(left) > String(right) ? 1 : 0);
    return tree.cmp === 'gt' ? comparison > 0 : tree.cmp === 'gte' ? comparison >= 0
      : tree.cmp === 'lt' ? comparison < 0 : tree.cmp === 'lte' ? comparison <= 0 : false;
  } catch { return false; }
}

export function customValue(definition: CustomDefinition, value: unknown): unknown {
  if (value === '' || value === null || value === undefined) return null;
  if (definition.data_type === 'integer') {
    const result = Number(value);
    if (!/^-?\d+$/.test(String(value)) || !Number.isSafeInteger(result)) throw new Error('Enter a whole number within the supported form range.');
    return result;
  }
  if (definition.data_type === 'decimal') { decimal(value); return String(value); }
  return value;
}

export function customPatch(fields: readonly CustomField[], values: Record<string, unknown>, previous: Record<string, unknown>): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const field of fields) {
    if (!field.custom || !field.writable || !field.custom.is_active || !(field.key in values)) continue;
    if (JSON.stringify(values[field.key]) !== JSON.stringify(previous[field.key])) result[field.key] = customValue(field.custom, values[field.key]);
  }
  return result;
}
