/** Native discovery determines types; decimal and date values remain strings. */
export type ReportParameter = { type?: string; format?: string; title?: string; enum?: string[]; default?: unknown; anyOf?: ReportParameter[]; pattern?: string; items?: ReportParameter; minimum?: number; maximum?: number; minItems?: number; maxItems?: number };
export const parameterType = (field: ReportParameter): ReportParameter => field.anyOf?.find(item => item.type !== 'null') ?? field;
export const parameterText = (value: unknown): string => value === undefined || value === null ? '' : Array.isArray(value) ? value.join(', ') : String(value);
export function reportParameters(properties: Record<string, ReportParameter>, values: Record<string, string>): Record<string, string | number | boolean | number[]> {
  return Object.fromEntries(Object.entries(values).filter(([key, value]) => value !== '' && !(key === 'currency' && properties.basis && values.basis !== 'TRANSACTION')).map(([key, value]) => {
    const field = parameterType(properties[key] ?? {}), label = properties[key]?.title ?? key.replaceAll('_', ' ');
    const integer = (text: string): number => {
      if (!/^-?\d+$/.test(text.trim()) || !Number.isSafeInteger(Number(text))) throw new Error(label + ' requires a whole number within its supported range.');
      return Number(text);
    };
    if (field.type === 'boolean') {
      if (!['true', 'false'].includes(value)) throw new Error('Choose whether to include ' + label.toLowerCase() + '.');
      return [key, value === 'true'];
    }
    if (field.type === 'integer') return [key, integer(value)];
    if (field.type === 'array') {
      if (field.items?.type !== 'integer') throw new Error(label + ' uses an unsupported list type.');
      const entries = value.split(',');
      if (entries.length > (field.maxItems ?? 200)) throw new Error(label + ' exceeds the supported list size.');
      return [key, entries.map(integer)];
    }
    return [key, value];
  }));
}
