'use client';
import { Select, TextField } from '@janso/ui';
import type { components } from '@janso/api-client/catalog';
import type { ProductSkuValues } from '../lib/advanced-product-draft';
import { AdvancedProductChoice } from './AdvancedProductChoice';

type Member = components['schemas']['AdvancedAttributeMember'];
type Selection = ProductSkuValues['attributes'][number];
const fields = { TEXT: 'value_text', INTEGER: 'value_integer', DECIMAL: 'value_decimal', BOOLEAN: 'value_boolean', DATE: 'value_date' } as const;

export function AdvancedRequiredAttributes({ company, sku, members, axes, onChange, disabled, errors, prefix }: { company: string; sku: ProductSkuValues; members: Member[]; axes: string[]; onChange: (sku: ProductSkuValues) => void; disabled: boolean; errors: Record<string, string>; prefix: string }) {
  const update = (definitionId: string, next: Selection | null) => onChange({ ...sku, attributes: [...sku.attributes.filter(row => row.definition_id !== definitionId), ...(next ? [next] : [])] });
  const relevant = members.filter(row => row.is_required && !axes.includes(row.definition_id));
  if (!relevant.length) return null;
  return <section className="product-wizard__section product-wizard__attributes" aria-label="Required Product Type attributes"><h4>Required Product Type attributes</h4><p>Choose a published value, or enter the typed value when this definition permits it. Each SKU needs its own value.</p>
    {relevant.map(member => {
      const current = sku.attributes.find(row => row.definition_id === member.definition_id);
      const scalarField = fields[member.value_type];
      const scalar = current?.[scalarField];
      const error = errors[`${prefix}attributes.${member.definition_id}`];
      const selection = (patch: Partial<Selection>): Selection => ({ definition_id: member.definition_id, value_type: member.value_type, ...patch });
      return <div className="product-wizard__unit-row" key={member.definition_id}><strong>{member.name}</strong><div className="product-wizard__fields">
        <AdvancedProductChoice company={company} resource="attribute_options" parent={member.definition_id} label={`${member.name} published choice`} value={current?.option_id ?? ''} disabled={disabled} error={error} onChange={id => update(member.definition_id, id ? selection({ option_id: id }) : null)} />
        {member.value_type === 'BOOLEAN' ? <Select label={`Or enter ${member.name}`} value={scalar === true ? 'true' : scalar === false ? 'false' : ''} disabled={disabled} error={error} placeholder="Choose a value" options={[{ value: 'true', label: 'Yes' }, { value: 'false', label: 'No' }]} onChange={value => update(member.definition_id, value ? selection({ value_boolean: value === 'true' }) : null)} /> : <TextField label={`Or enter ${member.name}`} type={member.value_type === 'DATE' ? 'date' : 'text'} inputMode={member.value_type === 'DECIMAL' || member.value_type === 'INTEGER' ? 'decimal' : undefined} value={typeof scalar === 'string' ? scalar : ''} disabled={disabled} error={error} onChange={event => update(member.definition_id, event.target.value ? selection({ [scalarField]: event.target.value }) : null)} />}
        {member.measurement_dimension && !current?.option_id && <AdvancedProductChoice company={company} resource="units" label={`${member.name} unit`} value={current?.unit_id ?? ''} disabled={disabled} onChange={id => update(member.definition_id, current ? { ...current, unit_id: id || null } : selection({ unit_id: id || null }))} />}
      </div></div>;
    })}
  </section>;
}
