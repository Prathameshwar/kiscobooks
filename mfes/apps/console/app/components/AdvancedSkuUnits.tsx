'use client';
import { TextField } from '@janso/ui';
import type { ProductSkuValues } from '../lib/advanced-product-draft';
import { AdvancedProductChoice } from './AdvancedProductChoice';

export function AdvancedSkuUnits({ company, sku, onChange, disabled, errors, prefix, mode }: { company: string; sku: ProductSkuValues; onChange: (sku: ProductSkuValues) => void; disabled: boolean; errors: Record<string, string>; prefix: string; mode?: string }) {
  if (mode === 'DISABLED') return null;
  const update = (index: number, changes: Partial<ProductSkuValues['units'][number]>) => onChange({ ...sku, units: sku.units.map((row, at) => at === index ? { ...row, ...changes } : row) });
  return <section className="product-wizard__units" aria-label="Alternate units"><div className="product-wizard__section-head"><div><h4>Alternate units and packs</h4><p>Use exact whole-number conversion ratios to the base unit.</p></div><button type="button" className="janso-btn janso-btn--secondary" disabled={disabled || sku.units.length >= 7} onClick={() => onChange({ ...sku, units: [...sku.units, { key: crypto.randomUUID(), code: '', unit_id: '', role: 'BOTH', pack_type_id: '', numerator: '1', denominator: '1', quantity_decimal_places: '0', quantity_increment: '1' }] })}>Add unit</button></div>
    {errors[prefix + 'units'] && <p role="alert">{errors[prefix + 'units']}</p>}
    {sku.units.map((row, index) => <div className="product-wizard__unit-row" key={row.key}><div className="product-wizard__section-head"><strong>Unit {index + 1}</strong><button type="button" className="janso-link" disabled={disabled} onClick={() => onChange({ ...sku, units: sku.units.filter((_, at) => at !== index) })}>Remove unit</button></div><div className="product-wizard__fields">
      <TextField label="Binding code" value={row.code} required maxLength={30} error={errors[`${prefix}units.${index}.code`]} disabled={disabled} onChange={event => update(index, { code: event.target.value.toUpperCase() })} />
      <AdvancedProductChoice company={company} resource="units" label="Alternate unit" value={row.unit_id} required disabled={disabled} error={errors[`${prefix}units.${index}.unit_id`]} onChange={id => update(index, { unit_id: id })} />
      <label className="product-wizard__field">Use for<select value={row.role} disabled={disabled} onChange={event => update(index, { role: event.target.value as ProductSkuValues['units'][number]['role'] })}><option value="BOTH">Sale and purchase</option><option value="SALE">Sale</option><option value="PURCHASE">Purchase</option><option value="PACK">Pack</option></select></label>
      {row.role === 'PACK' && <AdvancedProductChoice company={company} resource="pack_types" label="Pack type" value={row.pack_type_id} required disabled={disabled} error={errors[`${prefix}units.${index}.pack_type_id`]} onChange={id => update(index, { pack_type_id: id })} />}
      <TextField label="Base units numerator" inputMode="numeric" value={row.numerator} required disabled={disabled} error={errors[`${prefix}units.${index}.ratio`]} onChange={event => update(index, { numerator: event.target.value })} />
      <TextField label="Base units denominator" inputMode="numeric" value={row.denominator} required disabled={disabled} error={errors[`${prefix}units.${index}.ratio`]} onChange={event => update(index, { denominator: event.target.value })} />
      <TextField label="Quantity decimal places" inputMode="numeric" value={row.quantity_decimal_places} required disabled={disabled} error={errors[`${prefix}units.${index}.grid`]} onChange={event => update(index, { quantity_decimal_places: event.target.value })} />
      <TextField label="Quantity increment" inputMode="decimal" value={row.quantity_increment} required disabled={disabled} error={errors[`${prefix}units.${index}.grid`]} onChange={event => update(index, { quantity_increment: event.target.value })} />
    </div></div>)}
  </section>;
}
