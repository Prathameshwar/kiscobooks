'use client';
import { useState } from 'react';
import { Notice, TextField } from '@janso/ui';
import type { AdvancedOptions, AdvancedWork, ProductSkuValues } from '../lib/advanced-product-draft';
import { newSku } from '../lib/advanced-product-draft';
import { masterRequest } from '../lib/catalog-master-api';
import { requestFailure } from '../lib/service-call';
import { AdvancedProductChoice } from './AdvancedProductChoice';
import { AdvancedSkuUnits } from './AdvancedSkuUnits';
import { ProductCatalogCustomFields } from './ProductCatalogCustomFields';

export function AdvancedSkuStep({ company, work, options, onChange, errors, disabled }: { company: string; work: AdvancedWork; options: AdvancedOptions; onChange: (value: AdvancedWork) => void; errors: Record<string, string>; disabled: boolean }) {
  const [selected, setSelected] = useState(0);
  const [unitLabels, setUnitLabels] = useState<Record<string, string>>({});
  const [axisFailure, setAxisFailure] = useState('');
  const sku = work.skus[selected] ?? work.skus[0]!;
  const fields = options.sku_fields.fields;
  const field = (key: string) => fields.find(row => row.key === key);
  const shown = (key: string) => field(key)?.visible === true;
  const blocked = (key: string) => disabled || !field(key)?.writable || !!field(key)?.conditional_access;
  const canVariant = options.selected_type?.allow_variants === true && options.defaults.configuration.options.variants_mode !== 'DISABLED';
  const update = (index: number, next: ProductSkuValues) => onChange({ ...work, skus: work.skus.map((row, at) => at === index ? next : row) });
  const change = (key: keyof ProductSkuValues, next: string | boolean) => update(selected, { ...sku, [key]: next });
  const add = () => { if (!canVariant || !work.axes.length || work.skus.length >= (options.max_skus_per_draft ?? 64)) return; onChange({ ...work, skus: [...work.skus, newSku()] }); setSelected(work.skus.length); };
  return <div className="product-wizard__sections">
    <section className="product-wizard__section" aria-labelledby="variant-heading"><h3 id="variant-heading">Variant structure</h3><p>Declare the choices that distinguish your SKUs. Add only combinations you intend to sell or purchase.</p>
      {canVariant ? <><div className="product-wizard__axis-list">{work.axes.map((axis, index) => <div key={axis.key} className="product-wizard__axis"><AdvancedProductChoice company={company} resource="attribute_definitions" label={`Variant axis ${index + 1}`} value={axis.definition_id} selected={axis.label} disabled={disabled} onChange={(id, label) => { if (!id) return; setAxisFailure(''); void masterRequest<{ id: string; company_id: string; is_variant_capable?: boolean; value_type?: ProductSkuValues['attributes'][number]['value_type'] }>({ path: `/v1/companies/${company}/attribute-definitions/${id}` }).then(definition => { if (definition.id !== id || definition.company_id !== company || !definition.is_variant_capable || !definition.value_type) throw { status: 422, message: 'Choose an active variant-capable attribute.' }; onChange({ ...work, axes: work.axes.map((row, at) => at === index ? { ...row, definition_id: id, label, value_type: definition.value_type!, options: [] } : row), skus: work.skus.map(row => ({ ...row, attributes: row.attributes.filter(entry => entry.definition_id !== axis.definition_id) })) }); }).catch(error => setAxisFailure(requestFailure(error).message)); }} /><button className="janso-link" type="button" disabled={disabled} onClick={() => onChange({ ...work, axes: work.axes.filter((_, at) => at !== index), skus: work.skus.map(row => ({ ...row, attributes: row.attributes.filter(entry => entry.definition_id !== axis.definition_id) })) })}>Remove axis</button></div>)}<button type="button" className="janso-btn janso-btn--secondary" disabled={disabled || work.axes.length >= 8} onClick={() => onChange({ ...work, axes: [...work.axes, { key: crypto.randomUUID(), definition_id: '', label: '', value_type: 'TEXT', options: [] }] })}>Add variant axis</button></div>
        {axisFailure && <Notice tone="warning">{axisFailure}</Notice>}
        {work.axes.some(axis => !axis.definition_id) && <Notice>Choose a published attribute definition for every axis.</Notice>}</> : <p>One SKU is available for this Product Type and configuration.</p>}
    </section>
    <section className="product-wizard__section" aria-labelledby="sku-heading"><div className="product-wizard__section-head"><div><h3 id="sku-heading">SKUs and units</h3><p>{work.skus.length} explicit SKU{work.skus.length === 1 ? '' : 's'} in this Profile.</p></div>{canVariant && <button type="button" className="janso-btn janso-btn--secondary" onClick={add} disabled={disabled || !work.axes.length || work.skus.length >= (options.max_skus_per_draft ?? 64)}>Add SKU</button>}</div>
      {errors.skus && <Notice tone="danger">{errors.skus}</Notice>}
      <div className="product-wizard__sku-layout"><div className="product-wizard__sku-list" role="tablist" aria-label="SKUs">{work.skus.map((row, index) => <button key={row.key} type="button" role="tab" aria-selected={selected === index} className="product-wizard__sku-tab" onClick={() => setSelected(index)}>{index === 0 ? 'Default SKU' : `SKU ${index + 1}`}<strong>{row.sku || 'Needs code'}</strong><span>{row.name || 'Needs details'}</span></button>)}</div>
        <div className="product-wizard__sku-editor" role="tabpanel" aria-label={`SKU ${selected + 1} details`}><div className="product-wizard__section-head"><h4>{selected === 0 ? 'Default SKU' : `SKU ${selected + 1}`}</h4>{selected > 0 && <button type="button" className="janso-link" disabled={disabled} onClick={() => { onChange({ ...work, skus: work.skus.filter((_, at) => at !== selected) }); setSelected(Math.max(0, selected - 1)); }}>Remove SKU</button>}</div>
          <div className="product-wizard__fields">
            {shown('sku') && <TextField label={field('sku')?.label ?? 'SKU code'} value={sku.sku} required maxLength={30} error={errors[`skus.${selected}.sku`]} disabled={blocked('sku')} onChange={event => change('sku', event.target.value.toUpperCase())} />}
            {shown('name') && <TextField label={field('name')?.label ?? 'SKU name'} value={sku.name} required maxLength={100} error={errors[`skus.${selected}.name`]} disabled={blocked('name')} onChange={event => change('name', event.target.value)} />}
            {shown('base_unit_id') && <AdvancedProductChoice company={company} resource="units" label={field('base_unit_id')?.label ?? 'Base unit'} value={sku.base_unit_id} selected={unitLabels[sku.base_unit_id]} required error={errors[`skus.${selected}.base_unit_id`]} disabled={blocked('base_unit_id')} onChange={(id, label) => { setUnitLabels(previous => ({ ...previous, [id]: label })); change('base_unit_id', id); }} />}
            {shown('min_sale_quantity') && sku.sellable && <TextField label={field('min_sale_quantity')?.label ?? 'Minimum sale quantity'} inputMode="decimal" value={sku.min_sale_quantity} error={errors[`skus.${selected}.min_sale_quantity`]} disabled={blocked('min_sale_quantity')} onChange={event => change('min_sale_quantity', event.target.value)} />}
          </div><fieldset className="product-wizard__directions"><legend>Trade direction</legend>{shown('sellable') && <label><input type="checkbox" checked={sku.sellable} disabled={blocked('sellable')} onChange={event => change('sellable', event.target.checked)} /> Sellable</label>}{shown('purchasable') && <label><input type="checkbox" checked={sku.purchasable} disabled={blocked('purchasable')} onChange={event => change('purchasable', event.target.checked)} /> Purchasable</label>}{errors[`skus.${selected}.sellable`] && <span role="alert">{errors[`skus.${selected}.sellable`]}</span>}</fieldset>
          {work.axes.map(axis => <AdvancedProductChoice key={axis.key} company={company} resource="attribute_options" parent={axis.definition_id} label={axis.label || 'Variant option'} value={sku.attributes.find(entry => entry.definition_id === axis.definition_id)?.option_id ?? ''} selected={axis.options.find(option => option.id === sku.attributes.find(entry => entry.definition_id === axis.definition_id)?.option_id)?.label} required disabled={disabled || !axis.definition_id} error={errors[`skus.${selected}.${axis.definition_id}`]} onChange={(id, label) => { const attributes = sku.attributes.filter(entry => entry.definition_id !== axis.definition_id); onChange({ ...work, axes: work.axes.map(row => row.key === axis.key && id && !row.options.some(option => option.id === id) ? { ...row, options: [...row.options, { id, label }] } : row), skus: work.skus.map((row, index) => index === selected ? { ...row, attributes: id ? [...attributes, { definition_id: axis.definition_id, value_type: axis.value_type, option_id: id }] : attributes } : row) }); }} />)}
          {errors[`skus.${selected}.variants`] && <Notice tone="danger">{errors[`skus.${selected}.variants`]}</Notice>}
          <AdvancedSkuUnits company={company} sku={sku} onChange={next => update(selected, next)} disabled={disabled} errors={errors} prefix={`skus.${selected}.`} mode={options.defaults.configuration.options.alternate_units_mode} />
          <ProductCatalogCustomFields company={company} fields={fields} values={{ ...sku, custom_fields: sku.custom_fields }} creating disabled={disabled} errors={errors} onChange={custom_fields => update(selected, { ...sku, custom_fields })} />
        </div></div>
    </section>
  </div>;
}
