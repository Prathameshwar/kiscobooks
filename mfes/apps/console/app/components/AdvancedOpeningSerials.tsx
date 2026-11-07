'use client';
import { Notice, TextField } from '@janso/ui';
import type { components } from '@janso/api-client/catalog';
import type { OpeningSerial } from '../lib/advanced-product-opening';
import { trimSerialIdentifier } from '../lib/serial-identity';

type Requirement = components['schemas']['IdentifierRequirement'];
export function AdvancedOpeningSerials({ title, requirements, rows, onChange, disabled, maximum = 200, errors = {}, prefix = 'serials' }: {
  title: string; requirements: Requirement[]; rows: OpeningSerial[];
  onChange: (rows: OpeningSerial[]) => void; disabled: boolean; maximum?: number;
  errors?: Record<string, string>; prefix?: string;
}) {
  const fields = requirements.flatMap(rule => Array.from({ length: rule.max_count }, (_, at) => ({ rule, slot: at + 1 })));
  const add = () => onChange([...rows, { key: crypto.randomUUID(), identifiers: [] }]);
  const update = (rowIndex: number, type: 'SERIAL' | 'IMEI', slot: number, value: string) => onChange(rows.map((row, at) => at === rowIndex ? {
    ...row, identifiers: [...row.identifiers.filter(item => item.identifier_type !== type || (item.slot ?? 1) !== slot), ...(value ? [{ identifier_type: type, slot, value }] : [])],
  } : row));
  return <section className="product-wizard__serials" aria-label={title}>
    <div className="product-wizard__section-head"><div><h4>{title}</h4><p>One row for each physical unit. Keep leading zeros. Enter at least one identifier overall; any allowed slot can satisfy a type's minimum count.</p><p>{requirements.map(rule => `${rule.identifier_type}: ${rule.min_count}–${rule.max_count} per unit`).join('; ')}</p></div><button type="button" className="janso-btn janso-btn--secondary" disabled={disabled || rows.length >= maximum} onClick={add}>Add serial unit</button></div>
    {rows.map((row, rowIndex) => {
      const groupPath = `${prefix}.${rowIndex}.identifiers`;
      const native = row.identifiers.filter(item => trimSerialIdentifier(item.value));
      const displayed = new Set(fields.flatMap(({ rule, slot }) => {
        const item = row.identifiers.find(value => value.identifier_type === rule.identifier_type && (value.slot ?? 1) === slot);
        return item ? [`${groupPath}.${row.identifiers.indexOf(item)}.value`, `${groupPath}.${native.indexOf(item)}.value`] : [];
      }));
      return <div className="product-wizard__serial-row" key={row.key}>
        <div className="product-wizard__section-head"><strong>Physical unit {rowIndex + 1}</strong><button type="button" className="janso-link" disabled={disabled} onClick={() => onChange(rows.filter((_, at) => at !== rowIndex))}>Remove unit</button></div>
        <div className="product-wizard__fields">{fields.map(({ rule, slot }) => {
          const item = row.identifiers.find(item => item.identifier_type === rule.identifier_type && (item.slot ?? 1) === slot);
          const index = item ? row.identifiers.indexOf(item) : -1;
          const nativeIndex = item ? native.indexOf(item) : -1;
          const error = errors[`${groupPath}.${index}.value`] ?? errors[`${groupPath}.${nativeIndex}.value`];
          return <div key={`${rule.identifier_type}.${slot}`}><TextField label={`${rule.identifier_type === 'IMEI' ? 'IMEI' : 'Serial number'} ${slot}`} value={item?.value ?? ''} maxLength={240} required={rule.min_count === rule.max_count} disabled={disabled} error={error} onChange={event => update(rowIndex, rule.identifier_type, slot, event.target.value)} />{item && rule.min_count < rule.max_count && <button type="button" className="janso-link" disabled={disabled} aria-label={`Remove ${rule.identifier_type} slot ${slot}, unit ${rowIndex + 1}`} onClick={() => update(rowIndex, rule.identifier_type, slot, '')}>Remove identifier</button>}</div>;
        })}</div>
        {[...new Set(Object.entries(errors).filter(([key]) => key === `${prefix}.${rowIndex}` || key === groupPath || key.startsWith(groupPath + '.') && !displayed.has(key)).map(([, value]) => value))].map(message => <Notice key={message} tone="danger">{message}</Notice>)}
      </div>;
    })}
    {errors[prefix] && <Notice tone="danger">{errors[prefix]}</Notice>}
  </section>;
}
