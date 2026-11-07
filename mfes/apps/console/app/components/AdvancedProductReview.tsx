'use client';
import { useFormatters } from '@janso/ui';
import type { AdvancedOptions, AdvancedWork, ProductSkuValues } from '../lib/advanced-product-draft';
import { businessSku } from '../lib/advanced-product-business';
import { openingSku } from '../lib/advanced-product-opening';
import { useAdvancedReference } from '../lib/advanced-product-reference';

export function AdvancedReferenceText({ company, resource, value, parent, empty = 'Not provided', selected }: {
  company: string; resource: string; value?: string | null; parent?: string; empty?: string; selected?: string;
}) {
  const reference = useAdvancedReference(company, resource, value ?? '', parent, selected);
  return <span>{value ? reference.label : empty}</span>;
}

export function AdvancedPolicyFacts({ company, options, kind }: { company: string; options: AdvancedOptions; kind: string }) {
  const profiles = options.defaults.configuration.profiles;
  const policies = [
    ['Inventory profile', 'inventory-template-revisions', profiles.inventory_template_revision_id, kind === 'SERVICE'],
    ['Identifier profile', 'identifier-profiles', profiles.identifier_profile_id, kind === 'SERVICE'],
    ['Warranty policy', 'warranty-revisions', profiles.warranty_revision_id, false],
    ['Return policy', 'return-policy-revisions', profiles.return_policy_revision_id, false],
    ['Handling profile', 'handling-revisions', profiles.handling_revision_id, false],
  ] as const;
  return <dl className="product-wizard__facts">{policies.map(([label, resource, value, inapplicable]) => <div key={resource}><dt>{label}</dt><dd>{inapplicable ? 'Not applicable' : <AdvancedReferenceText company={company} resource={resource} value={value} empty="Not configured" />}</dd></div>)}</dl>;
}

function AttributeValue({ company, value, work, options }: { company: string; value: ProductSkuValues['attributes'][number]; work: AdvancedWork; options: AdvancedOptions }) {
  const format = useFormatters();
  const axis = work.axes.find(row => row.definition_id === value.definition_id);
  const member = options.attribute_members?.find(row => row.definition_id === value.definition_id);
  const name = member?.name || axis?.label || 'Attribute';
  const scalar = value.value_boolean != null ? value.value_boolean ? 'Yes' : 'No'
    : value.value_date ? format.date(value.value_date) : value.value_text ?? value.value_integer ?? value.value_decimal ?? 'Not provided';
  return <span>{name}: {value.option_id ? <AdvancedReferenceText company={company} resource="attribute_options" value={value.option_id} parent={value.definition_id} selected={axis?.options.find(option => option.id === value.option_id)?.label} /> : scalar}{value.unit_id && <> <AdvancedReferenceText company={company} resource="units" value={value.unit_id} /></>}</span>;
}

export function AdvancedProductReview({ company, work, options, onEdit, disabled }: { company: string; work: AdvancedWork; options: AdvancedOptions; onEdit: (step: number) => void; disabled: boolean }) {
  const format = useFormatters();
  const money = (amount: string) => amount ? `${options.currency} ${format.money(amount, { display: 'none', precision: 4 })}` : 'Not provided';
  const shown = (key: string) => options.family_fields?.fields.some(field => field.key === key && field.visible);
  return <div className="product-wizard__review">
    <div><h4>Product Profile</h4>
      <p>{work.profile.kind === 'GOODS' ? 'Goods' : 'Service'}{shown('name') && <> · {work.profile.name || 'Not provided'}</>}{shown('code') && <> · {work.profile.code || 'No code'}</>}</p>
      <p>Product Type: <AdvancedReferenceText company={company} resource="product-type-revisions" value={work.profile.product_type_revision_id} empty="Not selected" /></p>
      <p>Group: <AdvancedReferenceText company={company} resource="item_groups" value={work.profile.group_id} empty="Not selected" /></p>
      {shown('brand_id') && <p>Brand: <AdvancedReferenceText company={company} resource="brands" value={work.profile.brand_id} />{shown('series_id') && <> · Series: <AdvancedReferenceText company={company} resource="brand_series" value={work.profile.series_id} parent={work.profile.brand_id} /></>}</p>}
      {shown('model_code') && <p>Model: {work.profile.model_code || 'Not provided'}</p>}
      {shown('description') && <p>Description: {work.profile.description || 'Not provided'}</p>}
      <p>Manufacturer: <AdvancedReferenceText company={company} resource="manufacturers" value={work.profile.manufacturer_id} /> · Site: <AdvancedReferenceText company={company} resource="manufacturer_sites" value={work.profile.manufacturer_site_id} parent={work.profile.manufacturer_id} /></p>
      {work.profile.categories.length > 0 && <ul>{work.profile.categories.map(row => <li key={row.key}><AdvancedReferenceText company={company} resource="category_schemes" value={row.scheme_id} />: <AdvancedReferenceText company={company} resource="item_categories" value={row.category_id} parent={row.scheme_id} /></li>)}</ul>}
      <button type="button" className="janso-link" disabled={disabled} onClick={() => onEdit(1)}>Edit Profile setup</button>
    </div>
    <div><h4>SKUs and units</h4><ul>{work.skus.map(row => <li key={row.key}>
      <strong>{row.sku || 'No code'}</strong> · {row.name || 'Needs details'} · {[row.sellable && 'Sale', row.purchasable && 'Purchase'].filter(Boolean).join(' and ')}
      {options.sku_fields?.fields.some(field => field.key === 'base_unit_id' && field.visible) && <p>Base unit: <AdvancedReferenceText company={company} resource="units" value={row.base_unit_id} /></p>}
      {row.units.length > 0 && <ul>{row.units.map(unit => <li key={unit.key}>{unit.code}: <AdvancedReferenceText company={company} resource="units" value={unit.unit_id} /> · {unit.numerator}/{unit.denominator} base units</li>)}</ul>}
      <p>Barcode: {row.barcode || 'Not provided'}</p>
      {row.attributes.length > 0 && <ul>{row.attributes.map(value => <li key={value.definition_id}><AttributeValue company={company} value={value} work={work} options={options} /></li>)}</ul>}
    </li>)}</ul><button type="button" className="janso-link" disabled={disabled} onClick={() => onEdit(2)}>Edit remaining SKU setup</button></div>
    <div><h4>Business setup</h4><AdvancedPolicyFacts company={company} options={options} kind={work.profile.kind} />
      <ul>{work.skus.map(row => { const data = businessSku(work, row); return <li key={row.key}><strong>{row.sku || 'SKU'}</strong>
        {options.gst_enabled && <p>Tax classification: <AdvancedReferenceText company={company} resource="tax_classifications" value={data.classification_id} /> · Treatment: <AdvancedReferenceText company={company} resource="tax_rules" value={data.rule_id} /></p>}
        <p>Batch: {(data.batch_enabled ?? options.batch?.required) ? 'Enabled' : 'Off'}</p>
        {Object.entries(data.sale_prices).filter(([, amount]) => amount).map(([plan, amount]) => { const level = options.sale_price_levels?.find(value => value.plan_id === plan); return <p key={plan}>{level?.name || 'Selling price'}: {money(amount)}{level && ` (${level.tax_basis === 'INCLUSIVE' ? 'includes' : 'excludes'} tax)`}</p>; })}
        <p>Purchase reference: {money(data.purchase_amount)}{data.purchase_amount && <> · Source: {data.purchase_source || 'Not provided'}</>}</p>
        <p>MRP: {money(data.mrp_amount)}{data.mrp_amount && <> · Jurisdiction: {data.mrp_jurisdiction || 'Not provided'} · Source: {data.mrp_source || 'Not provided'}</>}</p>
      </li>; })}</ul><button type="button" className="janso-link" disabled={disabled} onClick={() => onEdit(3)}>Edit remaining business setup</button>
    </div>
    <div><h4>Opening decisions</h4><ul>{work.skus.map((row, index) => { const opening = openingSku(work, row); return <li key={row.key}><strong>{row.sku || `SKU ${index + 1}`}</strong>
      {opening.decision === 'SKIP' ? <p>No opening stock</p> : <>
        <p>Open on {format.date(opening.opening_date)} · Warehouse: <AdvancedReferenceText company={company} resource="warehouses" value={opening.warehouse_id} empty="Company default" /></p>
        {opening.batches.length ? <ul>{opening.batches.map(batch => <li key={batch.key}><strong>{batch.code || 'Unnamed batch'}</strong>
          <p>Opening quantity: {format.quantity(batch.opening_quantity)} · Opening unit cost: {money(batch.purchase_price)}</p>
          <p>Purchase reference: {money(batch.purchase_reference ?? '')}</p>
          {Object.entries(batch.sale_prices).filter(([, amount]) => amount).map(([id, amount]) => { const level = options.sale_price_levels?.find(value => value.price_level_id === id); return <p key={id}>{level?.name || 'Batch selling price'}: {money(amount)}{level && ` (${level.tax_basis === 'INCLUSIVE' ? 'includes' : 'excludes'} tax)`}</p>; })}
          <p>Physical MRP: {money(batch.mrp)}</p>
          {batch.manufactured_on && <p>Manufactured: {format.date(batch.manufactured_on)}</p>}{batch.expires_on && <p>Expires: {format.date(batch.expires_on)}</p>}
        </li>)}</ul> : <p>Opening quantity: {format.quantity(opening.opening_quantity)} · Opening unit cost: {money(opening.purchase_price)}</p>}
        {options.serial?.enabled && <ul aria-label={`Serial identifiers for ${row.sku || `SKU ${index + 1}`}`}>{[...opening.serials.map((unit, i) => ({ unit, label: `Unit ${i + 1}` })), ...opening.batches.flatMap(batch => batch.serials.map((unit, i) => ({ unit, label: `Batch ${batch.code}, unit ${i + 1}` })))].map(({ unit, label }) => <li key={unit.key}>{label}: {unit.identifiers.filter(item => item.value.trim()).map(item => `${item.identifier_type} ${item.slot ?? 1}: ${item.value}`).join('; ') || 'Missing identifiers'}</li>)}</ul>}
      </>}
    </li>; })}</ul><button type="button" className="janso-link" disabled={disabled} onClick={() => onEdit(4)}>Edit opening decisions</button></div>
  </div>;
}
